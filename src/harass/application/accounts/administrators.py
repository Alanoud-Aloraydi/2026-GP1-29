"""Grant and revoke administrator access and reset forgotten passwords."""

from dataclasses import replace

from harass.application.accounts.errors import UnknownAccountError
from harass.application.accounts.password_policy import PasswordPolicy
from harass.application.ports.authentication import (
    AuthenticationSecurity,
    AuthenticationStore,
)
from harass.domain.authentication import User, UserRole


class ManageAdministrators:
    """Change account roles and passwords for operators.

    The role is read from the database on every request, so a revocation
    takes effect immediately without ending the account's sessions.
    """

    def __init__(
        self,
        store: AuthenticationStore,
        security: AuthenticationSecurity,
        passwords: PasswordPolicy,
    ) -> None:
        """Bind the account store, the password hasher and the policy."""
        self._store = store
        self._security = security
        self._passwords = passwords

    def grant(self, email: str) -> User:
        """Make an existing account an administrator."""
        return self._change(email, UserRole.ADMINISTRATOR)

    def revoke(self, email: str) -> User:
        """Return an administrator to a plain user."""
        return self._change(email, UserRole.USER)

    def reset_password(self, email: str, password: str) -> User:
        """Set a new password for an account whose owner cannot recover it.

        Every session of the account ends, so a stolen session cannot
        outlive the reset.
        """
        user = self._store.find_user(email.strip().lower())
        if user is None:
            raise UnknownAccountError("No account has this email.")
        self._passwords.validate(password)
        if not self._store.set_password(
            user.user_id, self._security.hash_password(password)
        ):
            raise UnknownAccountError("No account has this email.")
        return user

    def _change(self, email: str, role: UserRole) -> User:
        """Set the role of the account with the canonical email."""
        user = self._store.find_user(email.strip().lower())
        if user is None or not self._store.set_role(user.user_id, role):
            raise UnknownAccountError("No account has this email.")
        return replace(user, role=role)
