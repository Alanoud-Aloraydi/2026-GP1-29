"""Validate SMTP configuration only when account email is enabled."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from email.utils import parseaddr
from urllib.parse import urlsplit

from harass.infrastructure.settings import SettingsError


@dataclass(frozen=True)
class SmtpSettings:
    """Require authenticated TLS and a trusted origin for action links."""

    host: str
    port: int
    sender: str
    username: str = field(repr=False)
    password: str = field(repr=False)
    public_url: str
    tls_mode: str = "starttls"

    def __post_init__(self) -> None:
        """Validate transport security, sender headers and the link origin."""
        parsed = urlsplit(self.public_url)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            self.tls_mode not in {"starttls", "ssl"}
            or not 1 <= self.port <= 65535
            or "\r" in self.sender
            or "\n" in self.sender
            or "@" not in parseaddr(self.sender)[1]
            or not self.host
            or not self.username
            or not self.password
        ):
            raise SettingsError(
                "A valid authenticated TLS SMTP setup is required."
            )
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not (
                parsed.scheme == "https" or (parsed.scheme == "http" and local)
            )
        ):
            raise SettingsError(
                "HARASS_PUBLIC_URL must be a trusted HTTPS URL."
            )

    @classmethod
    def from_environment(cls, values: Mapping[str, str]) -> "SmtpSettings":
        """Load required provider settings without reflecting secret values."""
        names = ("HOST", "FROM", "USERNAME", "PASSWORD")
        settings = {
            name: values.get("HARASS_SMTP_" + name, "") for name in names
        }
        try:
            port = int(values.get("HARASS_SMTP_PORT", "587"))
        except ValueError as error:
            raise SettingsError(
                "HARASS_SMTP_PORT must be an integer."
            ) from error
        return cls(
            settings["HOST"],
            port,
            settings["FROM"],
            settings["USERNAME"],
            settings["PASSWORD"],
            values.get("HARASS_PUBLIC_URL", ""),
            values.get("HARASS_SMTP_TLS", "starttls"),
        )
