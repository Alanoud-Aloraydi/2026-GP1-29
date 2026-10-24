"""Send account links through authenticated, certificate-verified SMTP."""

import smtplib
import ssl
from email.message import EmailMessage

from harass.application.ports.account_actions import AccountMailer
from harass.infrastructure.mail.settings import SmtpSettings


class SmtpAccountMailer(AccountMailer):
    """Use a bounded TLS connection for each account notification."""

    def __init__(self, settings: SmtpSettings) -> None:
        """Retain validated delivery settings without opening a connection."""
        self._settings = settings

    def send(self, recipient: str, subject: str, body: str) -> None:
        """Deliver plain text without logging credentials or account tokens."""
        settings = self._settings
        message = EmailMessage()
        message["From"], message["To"] = settings.sender, recipient
        message["Subject"] = subject
        message.set_content(body)
        context = ssl.create_default_context()
        if settings.tls_mode == "ssl":
            with smtplib.SMTP_SSL(
                settings.host, settings.port, timeout=10, context=context
            ) as server:
                server.login(settings.username, settings.password)
                server.send_message(message)
        else:
            with smtplib.SMTP(
                settings.host, settings.port, timeout=10
            ) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(settings.username, settings.password)
                server.send_message(message)
