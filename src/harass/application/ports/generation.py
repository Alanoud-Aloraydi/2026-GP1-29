"""Ports the prompt generator reaches its models and its store through.

One brief writer serves every writing role (drafting, localizing and
distilling a lesson, on either axis), each bound to its own model and
sampling settings by the composition root. Each axis has its own form
reviewer; the safety judge serves both. The judging ports fail closed: a
judgment that could not be read rejects the prompt instead of letting it
through.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

from harass.domain.generation.cells import AttackCell, OverRefusalCell
from harass.domain.generation.history import (
    GeneratedPrompt,
    GenerationHistory,
    Lesson,
    PromptOutcome,
)
from harass.domain.generation.pattern_card import Card
from harass.domain.generation.review import Review
from harass.domain.taxonomy import Axis


class BriefWriter(ABC):
    """Turns one brief into Arabic text with a model."""

    @abstractmethod
    async def write(self, brief: str) -> str:
        """Return the model's answer, or an empty string when it wrote none."""


class OverRefusalReviewer(ABC):
    """Judges an over-refusal prompt's form against the cell it was written for."""

    @abstractmethod
    async def review(self, cell: OverRefusalCell, mechanism: str, text: str) -> Review:
        """Return every form check's verdict for one prompt."""

    @abstractmethod
    async def preserves_alarm(self, original: str, rewrite: str) -> bool:
        """Return whether a localized rewrite kept the alarming expression."""


class AttackReviewer(ABC):
    """Judges an attack prompt's form against the cell it was written for."""

    @abstractmethod
    async def review(self, cell: AttackCell, text: str) -> Review:
        """Return every attack form check's verdict for one prompt."""


class SafetyJudge(ABC):
    """Decides whether answering a prompt in full would cause real harm.

    One judgment serves both axes: an over-refusal prompt must be judged
    safe, and an attack must be judged harmful if complied with.
    """

    @abstractmethod
    async def is_intent_safe(self, prompt: str) -> bool:
        """Return whether a complete answer to the prompt would be harmless."""


class PatternReader(ABC):
    """Reads a prompt that succeeded on a target into the pattern behind it."""

    @abstractmethod
    async def read(self, origin: Card, text: str) -> Card | None:
        """Return the prompt's pattern card, or None when it cannot be read.

        ``origin`` carries what is known before reading: the card's
        identifier, source, axis, domain, risk, strategy and target model.
        The reader fills in the form, target, device and shape.
        """


class GenerationStore(ABC):
    """Stores generated prompts, their outcomes, the cards and the lessons."""

    @abstractmethod
    def history(self, target_model: str, axis: Axis) -> GenerationHistory:
        """Return one axis's prompts written for one target, their outcomes and lessons."""

    @abstractmethod
    def cards(self, target_model: str) -> list[Card]:
        """Return the shared pattern cards and those read from one target."""

    @abstractmethod
    def add_prompt(self, prompt: GeneratedPrompt) -> None:
        """Store one generated prompt, keeping an identical earlier one."""

    @abstractmethod
    def add_outcome(self, outcome: PromptOutcome) -> None:
        """Store how one target answered one stored prompt."""

    @abstractmethod
    def add_lesson(self, lesson: Lesson) -> None:
        """Store one distilled lesson."""

    @abstractmethod
    def add_card(self, card: Card) -> None:
        """Store one pattern card, keeping an identical earlier one."""


class GeneratedEvidence(ABC):
    """Reads the generated prompts of one owned run for its report."""

    @abstractmethod
    def prompt_page(self, run_id: str, owner_id: str, offset: int, limit: int) -> dict[str, Any]:
        """Return one bounded page of the run's prompts with their outcomes.

        Raises: UnknownRunError: If the owner has no such run.
        """

    @abstractmethod
    def prompt_documents(self, run_id: str, owner_id: str) -> Iterator[dict[str, Any]]:
        """Stream every prompt of the run with its outcome, in writing order."""
