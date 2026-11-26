"""Ports the prompt generator reaches its models and its store through.

One brief writer serves the three writing roles (drafting, localizing and
distilling a lesson), each bound to its own model and sampling settings by
the composition root. The judging ports fail closed: a judgment that could
not be read rejects the prompt instead of letting it through.
"""

from abc import ABC, abstractmethod

from harass.domain.generation.cells import Cell
from harass.domain.generation.history import (
    GeneratedPrompt,
    GenerationHistory,
    Lesson,
    PromptOutcome,
)
from harass.domain.generation.pattern_card import Card
from harass.domain.generation.review import Review


class BriefWriter(ABC):
    """Turns one brief into Arabic text with a model."""

    @abstractmethod
    async def write(self, brief: str) -> str:
        """Return the model's answer, or an empty string when it wrote none."""


class FormReviewer(ABC):
    """Judges a prompt's form against the cell it was written for."""

    @abstractmethod
    async def review(self, cell: Cell, mechanism: str, text: str) -> Review:
        """Return every form check's verdict for one prompt."""

    @abstractmethod
    async def preserves_alarm(self, original: str, rewrite: str) -> bool:
        """Return whether a localized rewrite kept the alarming expression."""


class SafetyJudge(ABC):
    """Decides whether answering a prompt in full would cause real harm."""

    @abstractmethod
    async def is_intent_safe(self, prompt: str) -> bool:
        """Return whether a complete answer to the prompt would be harmless."""


class PatternReader(ABC):
    """Reads a refused prompt into the abstract pattern behind it."""

    @abstractmethod
    async def read(
        self, card_id: str, source: str, domain: str, risk: str, text: str
    ) -> Card | None:
        """Return the prompt's pattern card, or None when it cannot be read."""


class GenerationStore(ABC):
    """Stores generated prompts, their outcomes, the cards and the lessons."""

    @abstractmethod
    def history(self, target_model: str) -> GenerationHistory:
        """Return every stored prompt with its outcome on one target."""

    @abstractmethod
    def cards(self) -> list[Card]:
        """Return every stored pattern card."""

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
