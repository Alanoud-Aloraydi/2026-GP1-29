"""Transactional SQLAlchemy persistence of accounts and authentication sessions."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from harass.application.ports.authentication import AuthenticationStore
from harass.domain.authentication import AuthenticationSession, User
from harass.infrastructure.persistence.tables import AuthenticationSessionRow, UserRow


class SqlAlchemyAuthenticationStore(AuthenticationStore):
    """Persist account uniqueness and revocable sessions across application restarts."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """Bind a database-session factory."""
        self._sessions = session_factory

    def register(self, user: User, authentication_session: AuthenticationSession) -> bool:
        """Commit the account and its first session together with enforced email uniqueness."""
        try:
            with self._sessions.begin() as session:
                session.add(
                    UserRow(
                        user_id=user.user_id,
                        full_name=user.full_name,
                        email=user.email,
                        password_hash=user.password_hash,
                        created_at=datetime.now(UTC),
                    )
                )
                session.flush()
                session.add(
                    AuthenticationSessionRow(
                        session_id=authentication_session.session_id,
                        user_id=authentication_session.user_id,
                        expires_at=authentication_session.expires_at,
                    )
                )
        except IntegrityError:
            return False
        return True

    def find_user(self, email: str) -> User | None:
        """Read an account by canonical email."""
        with self._sessions() as session:
            row = session.scalar(select(UserRow).where(UserRow.email == email))
            return self._user(row)

    def get_user(self, user_id: str) -> User | None:
        """Read an account by immutable ID."""
        with self._sessions() as session:
            return self._user(session.get(UserRow, user_id))

    def add_session(self, session: AuthenticationSession) -> None:
        """Write a newly authenticated session."""
        with self._sessions.begin() as database:
            database.execute(
                delete(AuthenticationSessionRow).where(
                    AuthenticationSessionRow.expires_at <= datetime.now(UTC)
                )
            )
            database.add(
                AuthenticationSessionRow(
                    session_id=session.session_id,
                    user_id=session.user_id,
                    expires_at=session.expires_at,
                )
            )

    def get_session(self, session_id: str) -> AuthenticationSession | None:
        """Return a stored session with an aware UTC expiry, including on SQLite."""
        with self._sessions() as database:
            row = database.get(AuthenticationSessionRow, session_id)
            if row is None:
                return None
            expiry = row.expires_at
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            return AuthenticationSession(row.session_id, row.user_id, expiry)

    def revoke_session(self, session_id: str) -> None:
        """Delete a session atomically and idempotently."""
        with self._sessions.begin() as database:
            database.execute(
                delete(AuthenticationSessionRow).where(
                    AuthenticationSessionRow.session_id == session_id
                )
            )

    @staticmethod
    def _user(row: UserRow | None) -> User | None:
        if row is None:
            return None
        return User(row.user_id, row.full_name, row.email, row.password_hash)
