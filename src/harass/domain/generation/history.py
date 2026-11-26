"""What the generator has learned so far about one target model.

The history is the cell grid holding every generated prompt with the target's
answer to it, plus the library of abstract lessons distilled from finished
rounds. Lessons carry use and success counts and are drawn by an
upper-confidence rule, so a lesson that stops working fades: the archive of
Rainbow Teaming (arXiv 2402.16822) with the strategy library of AutoDAN-Turbo
(arXiv 2410.05295). Pure rules: loading and appending live behind a port.
"""

import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field

from harass.domain.taxonomy import ResponseCategory

CELL_SCOPE = "cell"
GROUP_SCOPE = "risk_mechanism"
# Lessons distilled from a target's scored dataset prompts carry this scope
# and target, which keeps them apart from lessons learned in a round.
SEED_SCOPE = "risk"
SEED_TARGET = "seed"
UCB_EXPLORATION = 1.4
# A cell needs this many scored outcomes before its own lessons outweigh the
# broader risk-and-mechanism pool, so a fresh cell still learns in round one.
CELL_EVIDENCE_MIN = 4
REFUSALS = frozenset({ResponseCategory.PARTIAL_REFUSAL, ResponseCategory.FULL_REFUSAL})


@dataclass(frozen=True)
class GeneratedPrompt:
    """One prompt the generator wrote, with the gates it passed.

    ``written_text`` is the clear draft the writer produced and ``sent_text``
    is what the target receives after localization, so a report shows both.
    """

    prompt_id: str
    case_id: str
    cell_key: str
    mechanism: str
    card_id: str
    round_index: int
    written_text: str
    sent_text: str
    reviewer_passed: bool
    intent_safe: bool
    reviewer_notes: Mapping[str, str] = field(default_factory=dict)
    attempts: int = 1

    @property
    def is_valid(self) -> bool:
        """Return whether the prompt passed both gates and may be sent."""
        return self.reviewer_passed and self.intent_safe


@dataclass(frozen=True)
class PromptOutcome:
    """How one target answered one generated prompt."""

    prompt_id: str
    target_model: str
    response_category: ResponseCategory

    @property
    def refused(self) -> bool | None:
        """Return the refusal verdict, or None when the reply was unclear.

        An unclear reply carries no verdict, so it stays out of every rate
        denominator instead of counting as compliance.
        """
        if self.response_category is ResponseCategory.UNCLEAR:
            return None
        return self.response_category in REFUSALS


@dataclass(frozen=True)
class Lesson:
    """An abstract lesson contrasting a refused prompt with an answered one.

    ``scope`` is ``cell`` for one domain-risk-variety cell, ``risk_mechanism``
    for the broader pool, or ``risk`` for a seed lesson; ``scope_key`` is the
    cell key, ``<risk>-<mechanism>`` or the risk code respectively.
    """

    lesson_id: str
    scope: str
    scope_key: str
    text: str
    target_model: str
    uses: int = 0
    successes: int = 0


@dataclass(frozen=True)
class GenerationHistory:
    """Stored prompts, their outcomes on one target, and the lessons.

    A history belongs to one target model, so every outcome in it came from
    that target and the rates below need no further filtering.
    """

    target_model: str
    prompts: tuple[GeneratedPrompt, ...] = ()
    outcomes: Mapping[str, PromptOutcome] = field(default_factory=dict)
    lessons: tuple[Lesson, ...] = ()

    def refused_cells(self) -> Counter[str]:
        """Count refusals per cell, the seams the planner should revisit."""
        return Counter(prompt.cell_key for prompt in self.prompts if self._refusal(prompt) is True)

    def accepted_cells(self) -> list[str]:
        """Return the cell of every prompt that passed review and the gate."""
        return [prompt.cell_key for prompt in self.prompts if prompt.is_valid]

    def card_uses(self) -> Counter[str]:
        """Count the stored prompts written from each card."""
        return Counter(prompt.card_id for prompt in self.prompts if prompt.card_id)

    def card_results(self) -> dict[str, tuple[int, int]]:
        """Return (refused, scored) per card on this target. O(n) in prompts."""
        results: dict[str, list[int]] = {}
        for prompt in self.prompts:
            refused = self._refusal(prompt)
            if not prompt.card_id or refused is None:
                continue
            counts = results.setdefault(prompt.card_id, [0, 0])
            counts[0] += refused
            counts[1] += 1
        return {card_id: (refused, scored) for card_id, (refused, scored) in results.items()}

    def seen_texts(self) -> list[str]:
        """Return every stored prompt text, for the novelty gate."""
        return [prompt.sent_text for prompt in self.prompts]

    def scored_in_cell(self, cell_key: str) -> int:
        """Count the prompts of one cell that carry a refusal verdict."""
        return sum(
            1
            for prompt in self.prompts
            if prompt.cell_key == cell_key and self._refusal(prompt) is not None
        )

    def best_lessons(self, cell_key: str, risk: str, mechanism: str, count: int) -> list[str]:
        """Return the top lessons for a cell, by the scope its evidence earns.

        A cell with enough scored outcomes draws on its own lessons. Before
        that it draws on the broader risk-and-mechanism pool learned against
        this target, plus the risk's seed lessons, so a fresh cell learns from
        the first round. Ranking is by upper confidence bound, whose
        exploration term shrinks with use. O(n) in lessons.
        """
        if self.scored_in_cell(cell_key) >= CELL_EVIDENCE_MIN:
            pool = [
                lesson
                for lesson in self.lessons
                if lesson.scope == CELL_SCOPE
                and lesson.scope_key == cell_key
                and lesson.target_model == self.target_model
            ]
        else:
            pool = [
                lesson for lesson in self.lessons if self._is_broad_lesson(lesson, risk, mechanism)
            ]
        total = sum(lesson.uses for lesson in pool) + 1
        ranked = sorted(pool, key=lambda lesson: _ucb(lesson, total), reverse=True)
        return [lesson.text for lesson in ranked[:count]]

    def _is_broad_lesson(self, lesson: Lesson, risk: str, mechanism: str) -> bool:
        """Return whether a lesson belongs to a fresh cell's broader pool."""
        learned_here = (
            lesson.scope == GROUP_SCOPE
            and lesson.scope_key == f"{risk}-{mechanism}"
            and lesson.target_model == self.target_model
        )
        seeded = (
            lesson.scope == SEED_SCOPE
            and lesson.scope_key == risk
            and lesson.target_model == SEED_TARGET
        )
        return learned_here or seeded

    def _refusal(self, prompt: GeneratedPrompt) -> bool | None:
        """Return one prompt's refusal verdict on this target, if it has one."""
        outcome = self.outcomes.get(prompt.prompt_id)
        return outcome.refused if outcome else None


def _ucb(lesson: Lesson, total_uses: int) -> float:
    """Return the upper-confidence score of one lesson; untried is infinite."""
    if lesson.uses == 0:
        return math.inf
    mean = lesson.successes / lesson.uses
    return mean + UCB_EXPLORATION * math.sqrt(math.log(total_uses + 1) / lesson.uses)
