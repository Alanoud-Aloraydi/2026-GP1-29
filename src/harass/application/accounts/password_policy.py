"""Shared password requirements for registration, changes and recovery."""

import hashlib
from collections.abc import Collection

from harass.application.accounts.errors import (
    PasswordRejectedError,
    RegistrationError,
)


class PasswordPolicy:
    """Enforce bounded password length and local compromised-value checks."""

    def __init__(self, blocked_hashes: Collection[str] = ()) -> None:
        """Retain only hashes of blocked passwords."""
        self._blocked = frozenset(blocked_hashes)

    def validate(self, password: str) -> None:
        """Reject invalid length, repeated characters and blocked values."""
        if not 15 <= len(password) <= 128:
            raise RegistrationError("Password must contain 15-128 characters.")
        if len(set(password)) == 1 or any(
            hashlib.sha256(value.encode()).hexdigest() in self._blocked
            for value in (password, password.casefold())
        ):
            raise PasswordRejectedError("Choose a less common password.")
