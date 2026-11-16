"""Persist accounts and revocable sessions transactionally."""

import hmac
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from harass.application.ports.authentication import AuthenticationStore
from harass.domain.authentication import (
    AuthenticationSession,
    User,
    UserRole,
)
from harass.infrastructure.persistence.row_mapping import utc_timestamp
from harass.infrastructure.persistence.session_factory import SessionFactory
from harass.infrastructure.persistence.tables import (
    AuthenticationSessionRow,
    UserRow,
)


class SqlAlchemyAuthenticationStore(AuthenticationStore):
    """Enforce unique accounts and atomic refresh-token rotation."""

    def __init__(self, session_factory: SessionFactory) -> None:
        """Bind the database-session factory."""
        self._sessions = session_factory

    def register(self, user: User, session: AuthenticationSession) -> bool:
        """Commit a unique account and its first session atomically."""
        try:
            with self._sessions() as database, database.begin():
                database.add(
                    UserRow(
                        user_id=user.user_id,
                        full_name=user.full_name,
                        email=user.email,
                        password_hash=user.password_hash,
                        created_at=datetime.now(UTC),
                    )
                )
                database.flush()
                database.add(_session_row(session))
        except IntegrityError:
            return False
        return True

    def find_user(self, email: str) -> User | None:
        """Read an account by canonical email."""
        with self._sessions() as database:
            return _user(
                database.scalar(select(UserRow).where(UserRow.email == email))
            )

    def get_user(self, user_id: str) -> User | None:
        """Read an account by immutable identity."""
        with self._sessions() as database:
            return _user(database.get(UserRow, user_id))

    def set_role(self, user_id: str, role: UserRole) -> bool:
        """Change an account's role, reporting whether the account exists."""
        with self._sessions() as database, database.begin():
            changed = database.scalar(
                update(UserRow)
                .where(UserRow.user_id == user_id)
                .values(role=role.value)
                .returning(UserRow.user_id)
            )
        return changed is not None

    def rename_user(self, user_id: str, full_name: str) -> bool:
        """Change an account's display name; false when it is missing."""
        with self._sessions() as database, database.begin():
            changed = database.scalar(
                update(UserRow)
                .where(UserRow.user_id == user_id)
                .values(full_name=full_name)
                .returning(UserRow.user_id)
            )
        return changed is not None

    def set_password(self, user_id: str, new_hash: str) -> bool:
        """Replace a password and revoke every session of the account."""
        with self._sessions() as database, database.begin():
            changed = database.scalar(
                update(UserRow)
                .where(UserRow.user_id == user_id)
                .values(password_hash=new_hash)
                .returning(UserRow.user_id)
            )
            if changed is None:
                return False
            database.execute(
                delete(AuthenticationSessionRow).where(
                    AuthenticationSessionRow.user_id == user_id
                )
            )
        return True

    def add_session(
        self, session: AuthenticationSession, password_hash: str
    ) -> bool:
        """Insert a session if the authenticated password is unchanged."""
        with self._sessions() as database, database.begin():
            user = database.get(UserRow, session.user_id, with_for_update=True)
            if user is None or user.password_hash != password_hash:
                return False
            database.execute(
                delete(AuthenticationSessionRow).where(
                    func.coalesce(
                        AuthenticationSessionRow.refresh_expires_at,
                        AuthenticationSessionRow.expires_at,
                    )
                    <= datetime.now(UTC)
                )
            )
            database.add(_session_row(session))
        return True

    def get_session(self, session_id: str) -> AuthenticationSession | None:
        """Read a session with explicit UTC timestamps."""
        with self._sessions() as database:
            return _session(database.get(AuthenticationSessionRow, session_id))

    def revoke_session(self, session_id: str) -> None:
        """Remove a session idempotently."""
        with self._sessions() as database, database.begin():
            database.execute(
                delete(AuthenticationSessionRow).where(
                    AuthenticationSessionRow.session_id == session_id
                )
            )

    def rotate_session(
        self,
        session_id: str,
        digest: str,
        replacement: str,
        expires_at: datetime,
    ) -> AuthenticationSession | None:
        """Rotate by compare-and-swap; known replay revokes the session."""
        with self._sessions() as database, database.begin():
            row = database.get(
                AuthenticationSessionRow, session_id, with_for_update=True
            )
            session = _session(row)
            if row is None or session is None:
                return None
            if _must_revoke(session, digest):
                database.delete(row)
                return None
            current = row.refresh_hash
            if not current or not hmac.compare_digest(current, digest):
                return None
            changed = database.scalar(
                update(AuthenticationSessionRow)
                .where(
                    AuthenticationSessionRow.session_id == session_id,
                    AuthenticationSessionRow.refresh_hash == digest,
                )
                .values(
                    refresh_hash=replacement,
                    expires_at=min(
                        expires_at, session.refresh_expires_at or expires_at
                    ),
                    used_refresh_hashes=[*session.used_refresh_hashes, digest],
                )
                .returning(AuthenticationSessionRow.session_id)
            )
            if not changed:
                return None
            database.refresh(row)
            return _session(row)

    def list_sessions(self, user_id: str) -> list[AuthenticationSession]:
        """List unexpired account sessions in creation order."""
        with self._sessions() as database:
            rows = database.scalars(
                select(AuthenticationSessionRow)
                .where(
                    AuthenticationSessionRow.user_id == user_id,
                    func.coalesce(
                        AuthenticationSessionRow.refresh_expires_at,
                        AuthenticationSessionRow.expires_at,
                    )
                    > datetime.now(UTC),
                )
                .order_by(AuthenticationSessionRow.created_at.desc())
                .limit(100)
            )
            return [
                session
                for row in rows
                if (session := _session(row)) is not None
            ]

    def revoke_user_sessions(
        self, user_id: str, session_id: str | None = None
    ) -> None:
        """Revoke only sessions owned by the authenticated account."""
        with self._sessions() as database, database.begin():
            statement = delete(AuthenticationSessionRow).where(
                AuthenticationSessionRow.user_id == user_id
            )
            if session_id:
                statement = statement.where(
                    AuthenticationSessionRow.session_id == session_id
                )
            database.execute(statement)


def _user(row: UserRow | None) -> User | None:
    """Reconstruct account identity without exposing password hashes."""
    return (
        User(
            row.user_id,
            row.full_name,
            row.email,
            row.password_hash,
            row.email_verified,
            UserRole(row.role),
            utc_timestamp(row.created_at),
        )
        if row
        else None
    )


def _must_revoke(session: AuthenticationSession, digest: str) -> bool:
    """Tell whether a refresh attempt ends the session instead.

    Reusing an old refresh token signals theft, so the whole session ends;
    the history cap bounds the stored hashes.
    """
    expires = session.refresh_expires_at
    if expires is None or expires <= datetime.now(UTC):
        return True
    used = session.used_refresh_hashes
    replay = any(hmac.compare_digest(digest, old) for old in used)
    return replay or len(used) >= 64


def _session_row(session: AuthenticationSession) -> AuthenticationSessionRow:
    """Map session credentials to storage without retaining raw tokens."""
    return AuthenticationSessionRow(
        session_id=session.session_id,
        user_id=session.user_id,
        expires_at=session.expires_at,
        created_at=session.created_at,
        refresh_expires_at=session.refresh_expires_at,
        refresh_hash=session.refresh_hash,
        used_refresh_hashes=list(session.used_refresh_hashes),
    )


def _session(
    row: AuthenticationSessionRow | None,
) -> AuthenticationSession | None:
    """Decode session lifetimes and refresh rotation history."""
    if row is None:
        return None
    expiry = utc_timestamp(row.expires_at)
    assert expiry is not None
    return AuthenticationSession(
        row.session_id,
        row.user_id,
        expiry,
        utc_timestamp(row.created_at),
        utc_timestamp(row.refresh_expires_at),
        row.refresh_hash,
        tuple(row.used_refresh_hashes or ()),
    )
