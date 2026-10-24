"""Public account failures without credential or provider details."""

from harass.application.errors import ApplicationError


class AuthenticationError(ApplicationError):
    """Account credentials or a session cannot be authenticated."""


class RegistrationError(ApplicationError):
    """Account details do not satisfy registration requirements."""


class PasswordRejectedError(RegistrationError):
    """The password matches a blocked value or repeated pattern."""


class InvalidAccountActionError(ApplicationError):
    """An account-action token is invalid, expired or already consumed."""
