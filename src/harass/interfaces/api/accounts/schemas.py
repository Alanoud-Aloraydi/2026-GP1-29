"""Validated account inputs and public session representations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Bound login inputs with password excluded from representations."""

    model_config = ConfigDict(hide_input_in_errors=True, extra="forbid")
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128, repr=False)


class SignupRequest(LoginRequest):
    """Account creation with a long password rather than composition rules."""

    full_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=15, max_length=128, repr=False)


class UserResponse(BaseModel):
    """Public account details; no password hash or session token."""

    user_id: str
    full_name: str
    email: str
    email_verified: bool = False


class PasswordChangeRequest(BaseModel):
    """Exclude current and replacement credentials from diagnostics."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    current_password: str = Field(min_length=1, max_length=128, repr=False)
    new_password: str = Field(min_length=15, max_length=128, repr=False)


class SessionResponse(BaseModel):
    """Account-visible session metadata without credential hashes."""

    session_id: str
    created_at: datetime | None
    expires_at: datetime
    current: bool
