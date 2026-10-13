"""Port for reading human-written evaluation cases."""

from abc import ABC, abstractmethod

from harass.domain.case_selection import CaseSelection
from harass.domain.evaluation_case import EvaluationCase


class SeedSource(ABC):
    """Provides evaluation cases from a seed store."""

    @abstractmethod
    def load_cases(self, selection: CaseSelection) -> list[EvaluationCase]:
        """Return the cases matching the selection, ordered by case identifier.

        Raises:
            SeedSourceError: If the seed data cannot be read or violates the seed schema.
        """
