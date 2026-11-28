"""Public account failures without credential or provider details."""

from harass.application.errors import ApplicationError


class AuthenticationError(ApplicationError):
    """Account credentials or a session cannot be authenticated."""


class RegistrationError(ApplicationError):
    """Account details do not satisfy registration requirements."""


class PasswordRejectedError(RegistrationError):
    """The password matches a blocked value or repeated pattern."""


class InvalidEmailError(RegistrationError):
    """The email address is malformed or too long."""


class InvalidNameError(RegistrationError):
    """The display name is too short, too long or holds control characters."""


class EmailRegisteredError(RegistrationError):
    """An account with this email already exists."""


class InvalidAccountActionError(ApplicationError):
    """An account-action token is invalid, expired or already consumed."""


class UnknownAccountError(ApplicationError):
    """No account has the requested email."""
