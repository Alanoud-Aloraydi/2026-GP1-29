"""Create accounts, authenticate credentials, and revoke sessions."""

import hashlib
import re
from collections.abc import Collection
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from harass.application.errors import ApplicationError
from harass.application.ports.authentication import AuthenticationSecurity, AuthenticationStore
from harass.domain.authentication import AuthenticatedLogin, AuthenticationSession, User


class AuthenticationError(ApplicationError):
    """Raised when credentials or a session cannot be authenticated."""


class RegistrationError(ApplicationError):
    """Raised when account details cannot be registered."""


class PasswordRejectedError(RegistrationError):
    """A password matched the configured blocklist or a repeated-character pattern."""


class ManageAuthentication:
    """Authentication independent of HTTP and cryptographic libraries."""

    def __init__(
        self,
        store: AuthenticationStore,
        security: AuthenticationSecurity,
        session_seconds: int = 3600,
        *,
        blocked_password_hashes: Collection[str] = (),
    ) -> None:
        """Bind the account store, crypto adapter, and positive session lifetime."""
        if not 60 <= session_seconds <= 86400:
            raise ValueError("Authentication session lifetime must be 60-86400 seconds.")
        self._store = store
        self._security = security
        self.session_seconds = session_seconds
        self._blocked_passwords = frozenset(blocked_password_hashes)
        # Unknown users follow the same expensive password verification path.
        self._dummy_hash = security.hash_password(uuid4().hex)

    def signup(self, full_name: str, email: str, password: str) -> AuthenticatedLogin:
        """Register validated details and begin a session."""
        name = full_name.strip()
        canonical_email = email.strip().lower()
        if not 2 <= len(name) <= 100 or any(ord(character) < 32 for character in name):
            raise RegistrationError("Full name must contain 2-100 printable characters.")
        if (
            len(canonical_email) > 254
            or any(not c.isprintable() for c in canonical_email)
            or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", canonical_email)
        ):
            raise RegistrationError("A valid email address is required.")
        if not 15 <= len(password) <= 128:
            raise RegistrationError("Password must contain 15-128 characters.")
        if len(set(password)) == 1 or any(
            hashlib.sha256(value.encode()).hexdigest() in self._blocked_passwords
            for value in (password, password.casefold())
        ):
            raise PasswordRejectedError("Choose a password that is not common or compromised.")
        user = User(str(uuid4()), name, canonical_email, self._security.hash_password(password))
        session = self._session(user)
        token = self._security.encode_session(session)
        if not self._store.register(user, session):
            raise RegistrationError("Unable to create an account with these details.")
        return AuthenticatedLogin(user, token)

    def login(self, email: str, password: str) -> AuthenticatedLogin:
        """Authenticate with a generic error that does not reveal account existence."""
        user = self._store.find_user(email.strip().lower())
        stored_hash = self._dummy_hash if user is None else user.password_hash
        valid = self._security.verify_password(password, stored_hash)
        if user is None or not valid:
            raise AuthenticationError("Email or password is incorrect.")
        return self._login(user)

    def authenticate(self, token: str) -> User:
        """Require a signed, unexpired token and its matching live server session."""
        decoded = self._security.decode_session(token)
        session = self._store.get_session(decoded.session_id)
        if session is None or session.user_id != decoded.user_id:
            raise AuthenticationError("Session is invalid or expired.")
        if session.expires_at <= datetime.now(UTC):
            self._store.revoke_session(session.session_id)
            raise AuthenticationError("Session is invalid or expired.")
        user = self._store.get_user(session.user_id)
        if user is None:
            raise AuthenticationError("Session is invalid or expired.")
        return user

    def logout(self, token: str) -> None:
        """Revoke a valid session; expired or malformed tokens are already unauthenticated."""
        try:
            session = self._security.decode_session(token)
        except AuthenticationError:
            return
        self._store.revoke_session(session.session_id)

    def _login(self, user: User) -> AuthenticatedLogin:
        session = self._session(user)
        self._store.add_session(session)
        return AuthenticatedLogin(user, self._security.encode_session(session))

    def _session(self, user: User) -> AuthenticationSession:
        return AuthenticationSession(
            str(uuid4()), user.user_id, datetime.now(UTC) + timedelta(seconds=self.session_seconds)
        )
