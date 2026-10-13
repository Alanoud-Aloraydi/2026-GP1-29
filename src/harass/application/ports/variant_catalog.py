"""Port for an extensible authored template and rule-based transform library."""

from abc import ABC, abstractmethod

from harass.domain.evaluation_case import EvaluationCase
from harass.domain.prompt_variant import (
    PromptTemplate,
    PromptVariant,
    TransformDefinition,
    VariantSelection,
)


class VariantCatalog(ABC):
    """Resolve library selections into eligible, deduplicated requests."""

    @abstractmethod
    def templates(self) -> tuple[PromptTemplate, ...]:
        """Return all authored template definitions."""

    @abstractmethod
    def transforms(self) -> tuple[TransformDefinition, ...]:
        """Return all available transform definitions."""

    @abstractmethod
    def variants(self, case: EvaluationCase, selection: VariantSelection) -> list[PromptVariant]:
        """Return compatible variants, excluding the unchanged baseline."""
