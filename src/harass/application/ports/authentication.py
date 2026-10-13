"""Persistence and cryptographic contracts for authentication."""

from abc import ABC, abstractmethod

from harass.domain.authentication import AuthenticationSession, User


class AuthenticationStore(ABC):
    """Persist unique users and revocable sessions."""

    @abstractmethod
    def register(self, user: User, session: AuthenticationSession) -> bool:
        """Insert the account and first session atomically; reject duplicate email."""

    @abstractmethod
    def find_user(self, email: str) -> User | None:
        """Find the account with the canonical email."""

    @abstractmethod
    def get_user(self, user_id: str) -> User | None:
        """Find an account by its immutable identifier."""

    @abstractmethod
    def add_session(self, session: AuthenticationSession) -> None:
        """Persist a new session."""

    @abstractmethod
    def get_session(self, session_id: str) -> AuthenticationSession | None:
        """Return a session only while it exists."""

    @abstractmethod
    def revoke_session(self, session_id: str) -> None:
        """Remove the session, idempotently."""


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
