"""Compose account authentication and optional mail delivery at startup."""

import os

from harass.application.accounts.authentication import ManageAuthentication
from harass.application.accounts.password_policy import PasswordPolicy
from harass.application.accounts.recovery import AccountRecovery
from harass.infrastructure.mail.settings import SmtpSettings
from harass.infrastructure.mail.smtp_mailer import SmtpAccountMailer
from harass.infrastructure.persistence.session_factory import SessionFactory
from harass.infrastructure.persistence.sqlalchemy_account_actions import (
    SqlAlchemyAccountActionStore,
)
from harass.infrastructure.persistence.sqlalchemy_authentication import (
    SqlAlchemyAuthenticationStore,
)
from harass.infrastructure.security.jwt_authentication import (
    JwtAuthenticationSecurity,
)
from harass.infrastructure.security.password_blocklist import password_hashes
from harass.infrastructure.settings import BackendSettings


def build_accounts(
    factory: SessionFactory, backend: BackendSettings
) -> tuple[ManageAuthentication, AccountRecovery | None]:
    """Construct mail delivery only when its feature flag is enabled."""
    store = SqlAlchemyAuthenticationStore(factory)
    security = JwtAuthenticationSecurity(
        backend.jwt_secret, previous_keys=backend.previous_jwt_secrets
    )
    blocked = password_hashes(os.environ.get("HARASS_PASSWORD_BLOCKLIST_PATH"))
    authentication = ManageAuthentication(
        store,
        security,
        backend.session_seconds,
        refresh_seconds=backend.refresh_seconds,
        blocked_password_hashes=blocked,
    )
    recovery = None
    if backend.account_email_enabled:
        settings = SmtpSettings.from_environment(os.environ)
        recovery = AccountRecovery(
            store,
            SqlAlchemyAccountActionStore(factory),
            security,
            SmtpAccountMailer(settings),
            PasswordPolicy(blocked),
            settings.public_url,
        )
    return authentication, recovery
