"""Issue and consume purpose-bound account verification and reset links."""

import hashlib
import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import uuid4

from harass.application.accounts.errors import InvalidAccountActionError
from harass.application.accounts.password_policy import PasswordPolicy
from harass.application.ports.account_actions import (
    AccountActionStore,
    AccountMailer,
)
from harass.application.ports.authentication import (
    AuthenticationSecurity,
    AuthenticationStore,
)
from harass.domain.account_action import AccountAction, AccountActionPurpose
from harass.domain.authentication import User


class AccountRecovery:
    """Coordinate account actions independently of HTTP and SMTP."""

    def __init__(
        self,
        accounts: AuthenticationStore,
        actions: AccountActionStore,
        security: AuthenticationSecurity,
        mailer: AccountMailer,
        passwords: PasswordPolicy,
        public_url: str,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Bind storage, delivery, password rules and the trusted site URL."""
        self._accounts, self._actions = accounts, actions
        self._security, self._mailer = security, mailer
        self._passwords, self._public_url = passwords, public_url.rstrip("/")
        self._clock = clock

    def request_reset(self, email: str) -> None:
        """Send a reset link only for a registered canonical email."""
        user = self._accounts.find_user(email.strip().lower())
        if user is not None:
            self._issue(user, AccountActionPurpose.RESET_PASSWORD)

    def request_verification(self, user_id: str) -> None:
        """Send a verification link for an unverified account."""
        user = self._accounts.get_user(user_id)
        if user is not None and not user.email_verified:
            self._issue(user, AccountActionPurpose.VERIFY_EMAIL)

    def verify(self, token: str) -> None:
        """Mark an email verified through a valid single-use action."""
        if not self._actions.verify_email(_digest(token), self._clock()):
            raise InvalidAccountActionError("Invalid or expired account link.")

    def reset(self, token: str, password: str) -> None:
        """Set a validated password without signing the account in."""
        digest = _digest(token)
        self._passwords.validate(password)
        password_hash = self._security.hash_password(password)
        if not self._actions.reset_password(
            digest, password_hash, self._clock()
        ):
            raise InvalidAccountActionError("Invalid or expired account link.")

    def _issue(self, user: User, purpose: AccountActionPurpose) -> None:
        """Persist a hash and deliver its secret only to the account email."""
        token = secrets.token_urlsafe(32)
        action = AccountAction(
            str(uuid4()),
            user.user_id,
            purpose,
            _digest(token),
            hashlib.sha256(user.password_hash.encode()).hexdigest(),
            self._clock() + timedelta(minutes=30),
        )
        if not self._actions.issue(action):
            return
        reset = purpose is AccountActionPurpose.RESET_PASSWORD
        page = "reset-password.html" if reset else "verify-email.html"
        subject = (
            "Reset your HARASS password" if reset else "Verify your email"
        )
        link = (
            self._public_url + "/" + page + "#" + urlencode({"token": token})
        )
        self._mailer.send(
            user.email,
            subject,
            f"{subject}:\n\n{link}\n\n"
            "This link expires in 30 minutes and can be used once.\n"
            "If you did not request it, ignore this message.",
        )


def _digest(token: str) -> str:
    """Hash a well-formed opaque credential without accepting JWTs."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise InvalidAccountActionError("Invalid or expired account link.")
    return hashlib.sha256(token.encode()).hexdigest()
