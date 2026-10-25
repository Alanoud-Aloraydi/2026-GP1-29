"""User identities and revocable authentication sessions."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class User:
    """An account with a private password hash."""

    user_id: str
    full_name: str
    email: str
    password_hash: str = field(repr=False)
    email_verified: bool = False


@dataclass(frozen=True)
class AuthenticationSession:
    """A server-side session that can be revoked before its token expires."""

    session_id: str
    user_id: str
    expires_at: datetime
    created_at: datetime | None = None
    refresh_expires_at: datetime | None = None
    refresh_hash: str | None = field(default=None, repr=False)
    used_refresh_hashes: tuple[str, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class AuthenticatedLogin:
    """Account and cookie token returned only to the HTTP adapter."""

    user: User
    token: str = field(repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    refresh_expires_at: datetime | None = None
