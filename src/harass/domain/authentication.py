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


@dataclass(frozen=True)
class AuthenticationSession:
    """A server-side session that can be revoked before its token expires."""

    session_id: str
    user_id: str
    expires_at: datetime


@dataclass(frozen=True)
class AuthenticatedLogin:
    """Account and cookie token returned only to the HTTP adapter."""

    user: User
    token: str = field(repr=False)
