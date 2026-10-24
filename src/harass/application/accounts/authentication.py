"""Create accounts, authenticate credentials, and revoke sessions."""

import hashlib
import re
import secrets
from collections.abc import Collection
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from harass.application.accounts.errors import (
    AuthenticationError,
    RegistrationError,
)
from harass.application.accounts.password_policy import PasswordPolicy
from harass.application.ports.authentication import (
    AuthenticationSecurity,
    AuthenticationStore,
)
from harass.domain.authentication import (
    AuthenticatedLogin,
    AuthenticationSession,
    User,
)


class ManageAuthentication:
    """Authentication independent of HTTP and cryptographic libraries."""

    def __init__(
        self,
        store: AuthenticationStore,
        security: AuthenticationSecurity,
        session_seconds: int = 900,
        *,
        blocked_password_hashes: Collection[str] = (),
        refresh_seconds: int = 28800,
    ) -> None:
        """Configure authentication storage, cryptography and lifetimes."""
        if not 60 <= session_seconds <= 86400:
            raise ValueError(
                "Authentication session lifetime must be 60-86400 seconds."
            )
        if not session_seconds <= refresh_seconds <= 604800:
            raise ValueError(
                "Refresh lifetime must cover access expiry and remain bounded."
            )
        self.refresh_seconds = refresh_seconds
        self._store = store
        self._security = security
        self.session_seconds = session_seconds
        self._passwords = PasswordPolicy(blocked_password_hashes)
        # Unknown users follow the same expensive password verification path.
        self._dummy_hash = security.hash_password(uuid4().hex)

    def signup(
        self, full_name: str, email: str, password: str
    ) -> AuthenticatedLogin:
        """Register validated details and begin a session."""
        name = full_name.strip()
        canonical_email = email.strip().lower()
        if not 2 <= len(name) <= 100 or any(
            ord(character) < 32 for character in name
        ):
            raise RegistrationError(
                "Full name must contain 2-100 printable characters."
            )
        if (
            len(canonical_email) > 254
            or any(not c.isprintable() for c in canonical_email)
            or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", canonical_email)
        ):
            raise RegistrationError("A valid email address is required.")
        self._passwords.validate(password)
        user = User(
            str(uuid4()),
            name,
            canonical_email,
            self._security.hash_password(password),
        )
        session, refresh = self._session(user)
        token = self._security.encode_session(session)
        if not self._store.register(user, session):
            raise RegistrationError(
                "Unable to create an account with these details."
            )
        return AuthenticatedLogin(
            user, token, refresh, session.refresh_expires_at
        )

    def login(self, email: str, password: str) -> AuthenticatedLogin:
        """Authenticate without revealing whether an account exists."""
        user = self._store.find_user(email.strip().lower())
        stored_hash = self._dummy_hash if user is None else user.password_hash
        valid = self._security.verify_password(password, stored_hash)
        if user is None or not valid:
            raise AuthenticationError("Email or password is incorrect.")
        return self._login(user)

    def authenticate(self, token: str) -> User:
        """Validate a signed access token and its live server session."""
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
        """Revoke the session identified by a valid access token."""
        try:
            session = self._security.decode_session(token)
        except AuthenticationError:
            return
        self._store.revoke_session(session.session_id)

    def refresh(self, token: str) -> AuthenticatedLogin:
        """Rotate refresh credentials within their absolute lifetime."""
        identifier, digest = refresh_identity(token)
        secret = secrets.token_urlsafe(32)
        session = self._store.rotate_session(
            identifier,
            digest,
            hashlib.sha256(secret.encode()).hexdigest(),
            datetime.now(UTC) + timedelta(seconds=self.session_seconds),
        )
        if session is None:
            raise AuthenticationError("Session is invalid or expired.")
        user = self._store.get_user(session.user_id)
        if user is None:
            raise AuthenticationError("Session is invalid or expired.")
        return AuthenticatedLogin(
            user,
            self._security.encode_session(session),
            identifier + "." + secret,
            session.refresh_expires_at,
        )

    def session_identifier(self, token: str) -> str:
        """Resolve the session identifier from a valid access token."""
        return self._security.decode_session(token).session_id

    def sessions(self, token: str) -> list[AuthenticationSession]:
        """List sessions only after authenticating their account owner."""
        return self._store.list_sessions(self.authenticate(token).user_id)

    def revoke_sessions(
        self, token: str, session_id: str | None = None
    ) -> None:
        """Revoke an owned session or sign the account out everywhere."""
        user = self.authenticate(token)
        if session_id is not None:
            try:
                session_id = str(UUID(session_id))
            except ValueError as error:
                raise AuthenticationError("Session is invalid.") from error
        self._store.revoke_user_sessions(user.user_id, session_id)

    def change_password(
        self, token: str, current: str, new: str
    ) -> AuthenticatedLogin:
        """Reauthenticate and replace the password and existing sessions."""
        user = self.authenticate(token)
        if not self._security.verify_password(current, user.password_hash):
            raise AuthenticationError("Current password is incorrect.")
        self._passwords.validate(new)
        if current == new:
            raise RegistrationError("Choose a different password.")
        updated = replace(
            user, password_hash=self._security.hash_password(new)
        )
        session, refresh = self._session(updated)
        if not self._store.change_password(
            user, updated.password_hash, session
        ):
            raise AuthenticationError("Credentials changed; sign in again.")
        return AuthenticatedLogin(
            updated,
            self._security.encode_session(session),
            refresh,
            session.refresh_expires_at,
        )

    def logout_refresh(self, token: str) -> None:
        """Revoke a refresh family even when its access token has expired."""
        try:
            identifier, digest = refresh_identity(token)
        except AuthenticationError:
            return
        session = self._store.get_session(identifier)
        if session and (
            session.refresh_hash == digest
            or digest in session.used_refresh_hashes
        ):
            self._store.revoke_session(identifier)

    def _login(self, user: User) -> AuthenticatedLogin:
        """Persist fresh credentials after password authentication."""
        session, refresh = self._session(user)
        if not self._store.add_session(session, user.password_hash):
            raise AuthenticationError("Credentials changed; sign in again.")
        return AuthenticatedLogin(
            user,
            self._security.encode_session(session),
            refresh,
            session.refresh_expires_at,
        )

    def _session(self, user: User) -> tuple[AuthenticationSession, str]:
        """Create a short access session and a hashed opaque refresh secret."""
        now = datetime.now(UTC)
        identifier, secret = str(uuid4()), secrets.token_urlsafe(32)
        return AuthenticationSession(
            identifier,
            user.user_id,
            now + timedelta(seconds=self.session_seconds),
            now,
            now + timedelta(seconds=self.refresh_seconds),
            hashlib.sha256(secret.encode()).hexdigest(),
        ), identifier + "." + secret


def refresh_identity(token: str) -> tuple[str, str]:
    """Validate an opaque refresh credential without returning its secret."""
    try:
        identifier, secret = token.split(".")
        identifier = str(UUID(identifier))
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", secret):
            raise ValueError("Malformed credential.")
    except (ValueError, AttributeError) as error:
        raise AuthenticationError("Session is invalid or expired.") from error
    return identifier, hashlib.sha256(secret.encode()).hexdigest()
