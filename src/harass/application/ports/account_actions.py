"""Atomic storage and mail delivery contracts for account actions."""

from abc import ABC, abstractmethod
from datetime import datetime

from harass.domain.account_action import AccountAction


class AccountActionStore(ABC):
    """Store expiring credentials and consume each action atomically."""

    @abstractmethod
    def issue(self, action: AccountAction) -> bool:
        """Replace an older action if the account credentials still match."""

    @abstractmethod
    def verify_email(self, digest: str, now: datetime) -> bool:
        """Consume a verification action and mark its account verified."""

    @abstractmethod
    def reset_password(
        self, digest: str, password_hash: str, now: datetime
    ) -> bool:
        """Consume a reset action and revoke all previous sessions."""


class AccountMailer(ABC):
    """Deliver an account-action link without exposing it in API results."""

    @abstractmethod
    def send(self, recipient: str, subject: str, body: str) -> None:
        """Deliver a message through the configured mail provider."""
