"""Errors that are part of the application port contracts."""


class ApplicationError(Exception):
    """Base class for errors raised through application ports."""


class ConflictError(ApplicationError):
    """A concurrent change or active operation prevents this mutation."""


class ActiveRunError(ConflictError):
    """An owner already has an evaluation that must finish or be cancelled."""

    def __init__(self, run_id: str) -> None:
        """Retain only the current owner's run identifier."""
        super().__init__("Finish or cancel the current evaluation before starting another.")
        self.run_id = run_id


class SeedSourceError(ApplicationError):
    """Raised when seed data cannot be read or violates the seed schema."""


class NoMatchingCasesError(ApplicationError):
    """Raised when no evaluation case satisfies the selection."""


class ReportExportError(ApplicationError):
    """Raised when an evaluation report cannot be written."""


class EvaluationEngineError(ApplicationError):
    """Raised when the evaluation engine cannot complete a run."""


class SecretCipherError(ApplicationError):
    """Raised when a stored secret cannot be decrypted."""


class UnknownConnectionError(ApplicationError):
    """Raised when a connection does not exist for the requesting owner."""


class ConnectionNotReadyError(ApplicationError):
    """Raised when an evaluation is requested on a connection that has not passed its test."""


class UnknownRunError(ApplicationError):
    """Raised when an evaluation run does not exist for the requesting owner."""
