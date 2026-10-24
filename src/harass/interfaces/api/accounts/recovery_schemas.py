"""Bound recovery inputs without exposing action tokens in diagnostics."""

from pydantic import BaseModel, ConfigDict, Field


class RecoveryEmailRequest(BaseModel):
    """Accept an email without revealing registration status."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    email: str = Field(min_length=1, max_length=254)


class AccountTokenRequest(BaseModel):
    """Accept only the opaque account-action credential format."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$", repr=False)


class PasswordResetRequest(AccountTokenRequest):
    """Validate a replacement password independently of login credentials."""

    new_password: str = Field(min_length=15, max_length=128, repr=False)
