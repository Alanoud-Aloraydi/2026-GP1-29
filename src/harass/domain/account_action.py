"""Expiring, single-use account actions with purpose-bound credentials."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class AccountActionPurpose(StrEnum):
    """Keep verification tokens separate from password-reset tokens."""

    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"


@dataclass(frozen=True)
class AccountAction:
    """Bind a hashed token to its account, purpose and credential snapshot."""

    action_id: str
    user_id: str
    purpose: AccountActionPurpose
    token_hash: str = field(repr=False)
    credential_hash: str = field(repr=False)
    expires_at: datetime
