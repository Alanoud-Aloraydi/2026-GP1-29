"""Durable attempt reservations, checkpoints and outcome iteration."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

from harass.domain.case_outcome import CaseOutcome


class EvaluationJournal(ABC):
    """Commit feedback and progress together before another request can be submitted."""

    @abstractmethod
    def initialize(self, fingerprint: str, total_cases: int) -> dict[str, Any]:
        """Return the checkpoint, rejecting a changed evaluation plan."""

    @abstractmethod
    def reserve(self, checkpoint: dict[str, Any]) -> None:
        """Persist the next submission before making its external request."""

    @abstractmethod
    def commit(self, outcome: CaseOutcome, checkpoint: dict[str, Any]) -> None:
        """Atomically persist an outcome and its resulting controller state."""

    @abstractmethod
    def outcomes(self, *, lightweight: bool = False) -> Iterator[CaseOutcome]:
        """Iterate stored outcomes in bounded pages, optionally omitting transcript text."""
