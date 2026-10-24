"""SMTP transport security and disabled-feature composition checks."""

from dataclasses import replace
from typing import Any
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session, sessionmaker

from harass.bootstrap.accounts import build_accounts
from harass.infrastructure.mail.settings import SmtpSettings
from harass.infrastructure.mail.smtp_mailer import SmtpAccountMailer
from harass.infrastructure.settings import BackendSettings, SettingsError


def configuration() -> SmtpSettings:
    """Provide isolated credentials for transport contract checks."""
    return SmtpSettings(
        host="smtp.example.test",
        port=587,
        sender="HARASS <accounts@example.test>",
        username="isolated-user",
        password="isolated-password",
        public_url="https://harass.example.test",
    )


@pytest.mark.parametrize("mode", ["starttls", "ssl"])
def test_delivery_requires_verified_tls(mode: str) -> None:
    """Authenticate only after establishing a verified TLS transport."""
    settings = replace(configuration(), tls_mode=mode)
    with (
        patch("smtplib.SMTP") as plain,
        patch("smtplib.SMTP_SSL") as secured,
    ):
        SmtpAccountMailer(settings).send(
            "recipient@example.test", "Account link", "Isolated message."
        )
        transport = secured if mode == "ssl" else plain
        server = transport.return_value.__enter__.return_value
        options = transport.call_args.kwargs
        assert options["timeout"] == 10
        context = (
            options["context"]
            if mode == "ssl"
            else server.starttls.call_args.kwargs["context"]
        )
        assert context.check_hostname
        assert context.verify_mode.name == "CERT_REQUIRED"
        server.login.assert_called_once_with(
            settings.username, settings.password
        )
        if mode == "starttls":
            assert [call[0] for call in server.mock_calls] == [
                "ehlo",
                "starttls",
                "ehlo",
                "login",
                "send_message",
            ]
        else:
            plain.assert_not_called()
        message = server.send_message.call_args.args[0]
        assert message["To"] == "recipient@example.test"
        assert message.get_content().strip() == "Isolated message."


@pytest.mark.parametrize(
    "changes",
    [
        {"tls_mode": "none"},
        {"port": 0},
        {"port": 65536},
        {"password": ""},
        {"sender": "a@example.test\r\nBcc: other@example.test"},
        {"public_url": "http://public.example.test"},
        {"public_url": "https://user:password@example.test"},
        {"public_url": "https://example.test?redirect=elsewhere"},
        {"public_url": "https://example.test#fragment"},
    ],
)
def test_unsafe_delivery_configuration_is_rejected(
    changes: dict[str, Any],
) -> None:
    """Reject insecure transport, injected headers and untrusted links."""
    with pytest.raises(SettingsError):
        replace(configuration(), **changes)


def test_local_http_origin_is_allowed_for_development() -> None:
    """Allow loopback development without accepting public plain HTTP."""
    assert replace(
        configuration(), public_url="http://127.0.0.1:8000"
    ).public_url
    settings = configuration()
    assert settings.username not in repr(settings)
    assert settings.password not in repr(settings)


def test_disabled_email_does_not_load_smtp(
    database_factory: sessionmaker[Session],
) -> None:
    """Construct normal accounts without reading optional SMTP settings."""
    backend = Mock(spec=BackendSettings)
    backend.jwt_secret = "isolated-account-composition-key-2026-padding"
    backend.previous_jwt_secrets = ()
    backend.session_seconds = 900
    backend.refresh_seconds = 28800
    backend.account_email_enabled = False
    with patch.object(SmtpSettings, "from_environment") as load:
        authentication, recovery = build_accounts(database_factory, backend)
    assert authentication is not None
    assert recovery is None
    load.assert_not_called()
