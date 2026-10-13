"""Errors raised when domain invariants are violated."""


class DomainError(Exception):
    """Base class for all domain invariant violations."""


class InvalidCaseIdentifierError(DomainError):
    """Raised when a case identifier violates the coding system."""


class InvalidEvaluationCaseError(DomainError):
    """Raised when an evaluation case is incomplete or inconsistent."""


class InvalidCaseSelectionError(DomainError):
    """Raised when selection criteria contradict each other."""


class InvalidTargetConnectionError(DomainError):
    """Raised when target connection details are incomplete or malformed."""


class InvalidEvaluationPlanError(DomainError):
    """Raised when an evaluation plan cannot be executed."""
