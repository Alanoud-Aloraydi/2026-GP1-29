"""Persistence and cryptographic contracts for authentication."""

from abc import ABC, abstractmethod
from datetime import datetime

from harass.domain.authentication import (
    AuthenticationSession,
    User,
    UserRole,
)


class AuthenticationStore(ABC):
    """Persist unique users and revocable sessions."""

    @abstractmethod
    def register(self, user: User, session: AuthenticationSession) -> bool:
        """Register the account and first session atomically."""

    @abstractmethod
    def find_user(self, email: str) -> User | None:
        """Find the account with the canonical email."""

    @abstractmethod
    def get_user(self, user_id: str) -> User | None:
        """Find an account by its immutable identifier."""

    @abstractmethod
    def set_role(self, user_id: str, role: UserRole) -> bool:
        """Change an account's role; false when the account is missing."""

    @abstractmethod
    def rename_user(self, user_id: str, full_name: str) -> bool:
        """Change an account's display name; false when it is missing."""

    @abstractmethod
    def set_password(self, user_id: str, new_hash: str) -> bool:
        """Replace the password and end every session of the account."""

    @abstractmethod
    def add_session(
        self, session: AuthenticationSession, password_hash: str
    ) -> bool:
        """Persist a session if the authenticated password is unchanged."""

    @abstractmethod
    def get_session(self, session_id: str) -> AuthenticationSession | None:
        """Return a session only while it exists."""

    @abstractmethod
    def revoke_session(self, session_id: str) -> None:
        """Remove the session, idempotently."""

    @abstractmethod
    def rotate_session(
        self,
        session_id: str,
        digest: str,
        replacement: str,
        expires_at: datetime,
    ) -> AuthenticationSession | None:
        """Rotate refresh secrets atomically and revoke replayed families."""

    @abstractmethod
    def list_sessions(self, user_id: str) -> list[AuthenticationSession]:
        """Return the account's unexpired sessions without their secrets."""

    @abstractmethod
    def revoke_user_sessions(
        self, user_id: str, session_id: str | None = None
    ) -> None:
        """Revoke one session or all sessions owned by the account."""


class AuthenticationSecurity(ABC):
    """Hash passwords and sign strictly validated session tokens."""

    @abstractmethod
    def hash_password(self, password: str) -> str:
        """Derive a salted password hash."""

    @abstractmethod
    def verify_password(self, password: str, stored_hash: str) -> bool:
        """Compare a password with a stored hash."""

    @abstractmethod
    def encode_session(self, session: AuthenticationSession) -> str:
        """Sign the session identity and expiry."""

    @abstractmethod
    def decode_session(self, token: str) -> AuthenticationSession:
        """Validate signature, claims, algorithm and expiry."""
