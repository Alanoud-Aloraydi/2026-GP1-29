"""Persist accounts and revocable sessions transactionally."""

import hmac
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from harass.application.ports.authentication import AuthenticationStore
from harass.domain.authentication import AuthenticationSession, User
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
        result = None
        with self._sessions() as database, database.begin():
            row = database.get(
                AuthenticationSessionRow, session_id, with_for_update=True
            )
            session = _session(row)
            if row is None or session is None:
                return None
            expired = (
                session.refresh_expires_at is None
                or session.refresh_expires_at <= datetime.now(UTC)
            )
            replay = any(
                hmac.compare_digest(digest, old)
                for old in session.used_refresh_hashes
            )
            if expired or replay or len(session.used_refresh_hashes) >= 64:
                database.delete(row)
            elif row.refresh_hash and hmac.compare_digest(
                row.refresh_hash, digest
            ):
                changed = database.scalar(
                    update(AuthenticationSessionRow)
                    .where(
                        AuthenticationSessionRow.session_id == session_id,
                        AuthenticationSessionRow.refresh_hash == digest,
                    )
                    .values(
                        refresh_hash=replacement,
                        expires_at=min(
                            expires_at,
                            session.refresh_expires_at or expires_at,
                        ),
                        used_refresh_hashes=[
                            *session.used_refresh_hashes,
                            digest,
                        ],
                    )
                    .returning(AuthenticationSessionRow.session_id)
                )
                if changed:
                    database.refresh(row)
                    result = _session(row)
        return result

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

    def change_password(
        self, user: User, new_hash: str, session: AuthenticationSession
    ) -> bool:
        """Replace an expected password and revoke every previous session."""
        with self._sessions() as database, database.begin():
            changed = database.scalar(
                update(UserRow)
                .where(
                    UserRow.user_id == user.user_id,
                    UserRow.password_hash == user.password_hash,
                )
                .values(password_hash=new_hash)
                .returning(UserRow.user_id)
            )
            if changed is None:
                return False
            database.execute(
                delete(AuthenticationSessionRow).where(
                    AuthenticationSessionRow.user_id == user.user_id
                )
            )
            database.add(_session_row(session))
        return True


def _user(row: UserRow | None) -> User | None:
    """Reconstruct account identity without exposing password hashes."""
    return (
        User(
            row.user_id,
            row.full_name,
            row.email,
            row.password_hash,
            row.email_verified,
        )
        if row
        else None
    )


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
