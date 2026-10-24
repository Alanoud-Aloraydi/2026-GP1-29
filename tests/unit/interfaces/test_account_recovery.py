"""Account-email gating and single-use recovery on real isolated storage."""

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from harass.application.accounts.authentication import ManageAuthentication
from harass.application.accounts.errors import (
    AuthenticationError,
    InvalidAccountActionError,
)
from harass.application.accounts.password_policy import PasswordPolicy
from harass.application.accounts.recovery import AccountRecovery
from harass.application.connections import ManageConnections
from harass.application.evaluation.run_service import ManageRuns
from harass.application.ports.account_actions import AccountMailer
from harass.domain.authentication import AuthenticatedLogin
from harass.infrastructure.persistence.sqlalchemy_account_actions import (
    SqlAlchemyAccountActionStore,
)
from harass.infrastructure.persistence.sqlalchemy_authentication import (
    SqlAlchemyAuthenticationStore,
)
from harass.infrastructure.persistence.sqlalchemy_request_limiter import (
    SqlAlchemyRequestLimiter,
)
from harass.infrastructure.persistence.tables import AccountActionRow
from harass.infrastructure.security.jwt_authentication import (
    JwtAuthenticationSecurity,
)
from harass.interfaces.api.app import create_app

PASSWORD = "recovery-fixture-password-2026"
KEY = "isolated-recovery-signing-key-48-bytes-2026-padding"
MUTATION = {"X-Harass-Request": "1"}


class Mailbox(AccountMailer):
    """Record messages only inside isolated tests."""

    def __init__(self) -> None:
        """Start with no delivered messages."""
        self.messages: list[tuple[str, str, str]] = []

    def send(self, recipient: str, subject: str, body: str) -> None:
        """Retain the exact message for token-flow assertions."""
        self.messages.append((recipient, subject, body))

    def token(self) -> str:
        """Extract the most recent action credential from its link fragment."""
        match = re.search(r"https://[^\s]+", self.messages[-1][2])
        assert match is not None
        return parse_qs(urlsplit(match.group()).fragment)["token"][0]


@dataclass
class Services:
    """Real account services sharing an isolated database namespace."""

    accounts: ManageAuthentication
    store: SqlAlchemyAuthenticationStore
    recovery: AccountRecovery
    mailbox: Mailbox
    factory: sessionmaker[Session]
    login: AuthenticatedLogin
    now: list[datetime]


@pytest.fixture
def services(database_factory: sessionmaker[Session]) -> Services:
    """Compose real security and storage with an isolated mailbox."""
    store = SqlAlchemyAuthenticationStore(database_factory)
    security = JwtAuthenticationSecurity(KEY)
    accounts = ManageAuthentication(store, security)
    login = accounts.signup("Recovery User", "recovery@example.test", PASSWORD)
    mailbox, now = Mailbox(), [datetime.now(UTC)]
    recovery = AccountRecovery(
        store,
        SqlAlchemyAccountActionStore(database_factory),
        security,
        mailbox,
        PasswordPolicy(),
        "https://harass.example.test",
        clock=lambda: now[0],
    )
    return Services(
        accounts, store, recovery, mailbox, database_factory, login, now
    )


def http_client(services: Services, enabled: bool = True) -> TestClient:
    """Expose optional email routes without target or judge calls."""
    return TestClient(
        create_app(
            cast(ManageConnections, Mock()),
            cast(ManageRuns, Mock()),
            authentication=services.accounts,
            recovery=services.recovery if enabled else None,
            request_limiter=SqlAlchemyRequestLimiter(services.factory, KEY),
        )
    )


def test_disabled_feature_has_no_delivery_routes(services: Services) -> None:
    """Disabled email cannot send messages or expose action endpoints."""
    with http_client(services, enabled=False) as client:
        assert client.get("/auth/features").json() == {
            "account_email_enabled": False
        }
        assert (
            client.post(
                "/auth/password/forgot",
                headers=MUTATION,
                json={"email": "recovery@example.test"},
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/auth/email/verify",
                headers=MUTATION,
                json={"token": "x" * 43},
            ).status_code
            == 404
        )
    assert not services.mailbox.messages


def test_tokens_are_hashed_and_bound_to_purpose(services: Services) -> None:
    """A reset token cannot verify email and never appears in storage."""
    services.recovery.request_reset(services.login.user.email)
    token = services.mailbox.token()
    with services.factory() as session:
        row = session.scalar(select(AccountActionRow))
        assert row is not None
        assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert token not in repr(vars(row))
    with pytest.raises(InvalidAccountActionError):
        services.recovery.verify(token)
    services.recovery.reset(token, "new-fixture-password-long-2026")
    with pytest.raises(InvalidAccountActionError):
        services.recovery.reset(token, "other-fixture-password-long-2026")


def test_reset_revokes_access_and_refresh_sessions(services: Services) -> None:
    """Password recovery revokes all sessions and never signs in implicitly."""
    second = services.accounts.login(services.login.user.email, PASSWORD)
    services.recovery.request_reset(services.login.user.email)
    services.recovery.reset(
        services.mailbox.token(), "changed-fixture-password-2026"
    )
    assert services.store.list_sessions(services.login.user.user_id) == []
    for login in (services.login, second):
        with pytest.raises(AuthenticationError):
            services.accounts.authenticate(login.token)
        with pytest.raises(AuthenticationError):
            services.accounts.refresh(login.refresh_token or "")
    with pytest.raises(AuthenticationError):
        services.accounts.login(services.login.user.email, PASSWORD)
    services.accounts.login(
        services.login.user.email, "changed-fixture-password-2026"
    )


def test_verification_consumes_only_its_own_action(services: Services) -> None:
    """Verification sets the email state once and cannot reset a password."""
    services.recovery.request_verification(services.login.user.user_id)
    token = services.mailbox.token()
    with pytest.raises(InvalidAccountActionError):
        services.recovery.reset(token, "changed-fixture-password-2026")
    services.recovery.verify(token)
    user = services.store.get_user(services.login.user.user_id)
    assert user is not None and user.email_verified
    with pytest.raises(InvalidAccountActionError):
        services.recovery.verify(token)
    services.recovery.request_verification(user.user_id)
    assert len(services.mailbox.messages) == 1


def test_expiry_reissue_and_password_change_invalidate_links(
    services: Services,
) -> None:
    """Reject expired, replaced or invalidated account links."""
    services.recovery.request_reset(services.login.user.email)
    first = services.mailbox.token()
    services.recovery.request_reset(services.login.user.email)
    second = services.mailbox.token()
    with pytest.raises(InvalidAccountActionError):
        services.recovery.reset(first, "changed-fixture-password-2026")
    services.now[0] += timedelta(minutes=31)
    with pytest.raises(InvalidAccountActionError):
        services.recovery.reset(second, "changed-fixture-password-2026")
    services.now[0] = datetime.now(UTC)
    services.recovery.request_reset(services.login.user.email)
    third = services.mailbox.token()
    services.accounts.change_password(
        services.login.token, PASSWORD, "updated-current-password-2026"
    )
    with pytest.raises(InvalidAccountActionError):
        services.recovery.reset(third, "changed-fixture-password-2026")


def test_concurrent_token_consumption_has_one_winner(
    services: Services,
) -> None:
    """Concurrent reset submissions cannot both consume one credential."""
    services.recovery.request_reset(services.login.user.email)
    token = services.mailbox.token()

    def consume(_: int) -> bool:
        """Attempt a competing password reset against the same action."""
        try:
            services.recovery.reset(token, "concurrent-fixture-password-2026")
            return True
        except InvalidAccountActionError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(consume, range(2)))
    assert sorted(results) == [False, True]


def test_http_recovery_is_generic_rate_limited_and_same_origin(
    services: Services,
) -> None:
    """Keep recovery responses independent of account existence."""
    with http_client(services) as client:
        assert (
            client.post(
                "/auth/password/forgot",
                json={"email": "recovery@example.test"},
            ).status_code
            == 403
        )
        known = client.post(
            "/auth/password/forgot",
            headers=MUTATION,
            json={"email": "recovery@example.test"},
        )
        unknown = client.post(
            "/auth/password/forgot",
            headers=MUTATION,
            json={"email": "unknown@example.test"},
        )
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json() == {"status": "accepted"}
        assert len(services.mailbox.messages) == 1
        invalid = client.post(
            "/auth/email/verify", headers=MUTATION, json={"token": "x" * 43}
        )
        assert invalid.status_code == 400
        assert invalid.json() == {"code": "account_link_invalid"}
        for _ in range(7):
            client.post(
                "/auth/password/forgot",
                headers=MUTATION,
                json={"email": "unknown@example.test"},
            )
        assert (
            client.post(
                "/auth/password/forgot",
                headers=MUTATION,
                json={"email": "unknown@example.test"},
            ).status_code
            == 429
        )


def test_verification_request_uses_authenticated_owner(
    services: Services,
) -> None:
    """The verification endpoint cannot accept another account's address."""
    with http_client(services) as client:
        assert (
            client.post(
                "/auth/email/request-verification", headers=MUTATION
            ).status_code
            == 401
        )
        client.cookies.set("harass_session", services.login.token)
        response = client.post(
            "/auth/email/request-verification", headers=MUTATION
        )
        assert response.status_code == 202
        assert services.mailbox.messages[-1][0] == services.login.user.email
