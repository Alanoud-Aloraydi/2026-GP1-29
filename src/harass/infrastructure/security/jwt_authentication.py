"""PyJWT session signing and OWASP-recommended scrypt password hashing."""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from threading import BoundedSemaphore
from typing import cast
from uuid import UUID

import jwt

from harass.application.accounts.errors import AuthenticationError
from harass.application.ports.accounts import AuthenticationSecurity
from harass.domain.authentication import AuthenticationSession

_PASSWORD_WORK = BoundedSemaphore(2)


class JwtAuthenticationSecurity(AuthenticationSecurity):
    """Sign bounded HS256 tokens and hash passwords using scrypt.

    Parameters follow OWASP Password Storage Cheat Sheet; algorithm
    allowlisting and required claims follow PyJWT's usage guidance. The signing
    key is independent of Fernet.
    """

    def __init__(self, signing_key: str, *, previous_keys: tuple[str, ...] = ()) -> None:
        """Require at least 32 UTF-8 bytes of signing-key material."""
        if len(signing_key.encode()) < 32:
            raise ValueError("HARASS_JWT_SECRET must contain at least 32 bytes.")
        self._signing_key = signing_key
        if len(previous_keys) > 2 or any(len(key.encode()) < 32 for key in previous_keys):
            raise ValueError("Use at most two previous JWT keys of at least 32 bytes.")
        self._verification_keys = (signing_key, *previous_keys)

    def hash_password(self, password: str) -> str:
        """Derive a 32-byte hash with a fresh 16-byte salt."""
        salt = secrets.token_bytes(16)
        digest = self._derive(password, salt)
        return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()

    def verify_password(self, password: str, stored_hash: str) -> bool:
        """Verify with constant-time hash comparison."""
        if len(password) > 128:
            return False
        try:
            method, encoded_salt, encoded_hash = stored_hash.split("$")
            if method != "scrypt":
                return False
            salt = base64.b64decode(encoded_salt, validate=True)
            expected = base64.b64decode(encoded_hash, validate=True)
            if len(salt) != 16 or len(expected) != 32:
                return False
            return hmac.compare_digest(self._derive(password, salt), expected)
        except ValueError:
            return False

    def encode_session(self, session: AuthenticationSession) -> str:
        """Encode the immutable user and revocable session identifiers."""
        return jwt.encode(
            {
                "sub": session.user_id,
                "jti": session.session_id,
                "exp": session.expires_at,
                "iat": datetime.now(UTC),
                "nbf": datetime.now(UTC),
                "token_type": "access",
                "iss": "harass",
                "aud": "harass-web",
            },
            self._signing_key,
            algorithm="HS256",
        )

    def decode_session(self, token: str) -> AuthenticationSession:
        """Validate access-token signatures, claims and identity fields."""
        invalid = AuthenticationError("Session is invalid or expired.")
        try:
            claims = self._decode(token)
            if not _valid_claims(claims):
                raise invalid
            session_id, user_id = (str(UUID(str(claims[name]))) for name in ("jti", "sub"))
            expiry = datetime.fromtimestamp(cast(int, claims["exp"]), UTC)
            return AuthenticationSession(session_id, user_id, expiry)
        except (jwt.InvalidTokenError, ValueError, OverflowError, OSError) as error:
            raise invalid from error

    def _decode(self, token: str) -> dict[str, object]:
        """Allow a bounded rotation window while retaining all claim checks."""
        for key in self._verification_keys:
            try:
                return jwt.decode(
                    token,
                    key,
                    algorithms=["HS256"],
                    issuer="harass",
                    audience="harass-web",
                    options={
                        "require": ["sub", "jti", "exp", "iat", "nbf", "iss", "aud", "token_type"]
                    },
                )
            except jwt.InvalidSignatureError:
                continue
        raise jwt.InvalidSignatureError("No configured key verifies this token.")

    @staticmethod
    def _derive(password: str, salt: bytes) -> bytes:
        """Derive a bounded-memory salted password hash using scrypt."""
        with _PASSWORD_WORK:
            return hashlib.scrypt(
                password.encode(), salt=salt, n=131072, r=8, p=1, dklen=32, maxmem=256 * 1024 * 1024
            )


def _valid_claims(claims: dict[str, object]) -> bool:
    """Require non-empty identities, integer times and a bounded access lifetime."""
    identities = all(isinstance(claims[name], str) and claims[name] for name in ("sub", "jti"))
    times = all(type(claims[name]) is int for name in ("exp", "iat", "nbf"))
    if not identities or not times or claims["token_type"] != "access":
        return False
    return 0 < cast(int, claims["exp"]) - cast(int, claims["iat"]) <= 86400
