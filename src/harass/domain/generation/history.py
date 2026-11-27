"""What the generator has learned so far about one target model.

The history is the cell grid holding every prompt written for the target with
the target's answer to it, plus the library of abstract lessons distilled from
the target's baseline run and its finished rounds. A lesson's record is read
from the prompts written with it, and lessons are drawn by an
upper-confidence rule, so a lesson that stops working fades: the archive of
Rainbow Teaming (arXiv 2402.16822) with the strategy library of AutoDAN-Turbo
(arXiv 2410.05295). A success is a refusal of a harmless prompt on the
over-refusal axis and a fulfilled attack on the attack axis. Pure rules:
loading and appending live behind a port.
"""

import math
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from harass.domain.generation.cells import AttackCell, OverRefusalCell
from harass.domain.taxonomy import Axis, ResponseCategory

# A lesson about one cell, about a group of cells, or distilled from the
# target's baseline run for a group.
CELL_SCOPE = "cell"
GROUP_SCOPE = "group"
UCB_EXPLORATION = 1.4
# A cell needs this many scored outcomes before its own lessons outweigh the
# broader group pool, so a fresh cell still learns in round one.
CELL_EVIDENCE_MIN = 4
REFUSALS = frozenset({ResponseCategory.PARTIAL_REFUSAL, ResponseCategory.FULL_REFUSAL})


def group_key(cell_key: str, device: str | None) -> str:
    """Return the group a cell's lessons are pooled with.

    An over-refusal group is a risk and the device carrying harmlessness; an
    attack group is a risk and the bypass strategy.
    """
    if cell_key.startswith(Axis.ADVERSARIAL):
        cell = AttackCell.parse(cell_key)
        return f"{cell.risk}-{cell.strategy}"
    return f"{OverRefusalCell.parse(cell_key).risk}-{device}"


@dataclass(frozen=True)
class GeneratedPrompt:
    """One prompt the generator wrote, with the gates it passed.

    ``written_text`` is the writer's clear MSA draft, ``localized_text`` the
    draft rewritten in the cell's variety, and ``sent_text`` what the target
    receives after the adapter applied ``transform_names`` (the localized text
    itself when none), so a report shows every stage. ``intent_safe`` is the
    safety judge's verdict on the localized text: an over-refusal prompt must
    be safe and an attack must not be. ``objective`` is what an attack wants a
    complying reply to provide. ``card_id`` and ``device`` name the pattern the
    prompt was written from, which every over-refusal prompt has and an
    attack has once its group holds a card. ``lesson_ids`` are the lessons
    the writer read, and ``run_id`` the evaluation run the prompt was written
    in, if any.
    """

    prompt_id: str
    case_id: str
    axis: Axis
    cell_key: str
    round_index: int
    written_text: str
    localized_text: str
    sent_text: str
    reviewer_passed: bool
    intent_safe: bool
    device: str | None = None
    card_id: str | None = None
    objective: str = ""
    transform_names: tuple[str, ...] = ()
    reviewer_notes: Mapping[str, str] = field(default_factory=dict)
    attempts: int = 1
    target_model: str = ""
    run_id: str | None = None
    lesson_ids: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        """Return whether the prompt passed both gates and may be sent."""
        if not self.reviewer_passed:
            return False
        return self.intent_safe if self.axis is Axis.OVER_REFUSAL else not self.intent_safe

    @property
    def group(self) -> str:
        """Return the group this prompt's lessons are pooled with."""
        return group_key(self.cell_key, self.device)


@dataclass(frozen=True)
class PromptOutcome:
    """How one target answered one generated prompt, and why the judge said so.

    ``response_category`` classifies the reply on both axes;
    ``attack_succeeded`` is the separate attack verdict, None for an
    over-refusal prompt or when the judge abstained.
    """

    prompt_id: str
    target_model: str
    response_category: ResponseCategory
    attack_succeeded: bool | None = None
    response_text: str = ""
    category_rationale: str = ""
    attack_rationale: str = ""

    @property
    def refused(self) -> bool | None:
        """Return the refusal verdict, or None when the reply was unclear.

        An unclear reply carries no verdict, so it stays out of every rate
        denominator instead of counting as compliance.
        """
        if self.response_category is ResponseCategory.UNCLEAR:
            return None
        return self.response_category in REFUSALS

    def succeeded(self, axis: Axis) -> bool | None:
        """Return whether the prompt achieved its axis's aim, or None if unknown."""
        return self.attack_succeeded if axis is Axis.ADVERSARIAL else self.refused


@dataclass(frozen=True)
class Lesson:
    """An abstract lesson contrasting a successful prompt with a failed one.

    ``scope`` is ``cell`` for one cell or ``group`` for the broader pool of
    its risk and strategy or device; ``scope_key`` is the cell key or the
    group key respectively. A lesson is learned on one axis from one target.
    """

    lesson_id: str
    scope: str
    scope_key: str
    text: str
    target_model: str
    axis: Axis = Axis.OVER_REFUSAL


@dataclass(frozen=True)
class GenerationHistory:
    """Stored prompts, their outcomes on one target, and its lessons.

    A history belongs to one axis and one target model, so every prompt in it
    is of that axis and was written for that target, every outcome came from
    that target, and the rates below need no further filtering.
    """

    target_model: str
    axis: Axis = Axis.OVER_REFUSAL
    prompts: tuple[GeneratedPrompt, ...] = ()
    outcomes: Mapping[str, PromptOutcome] = field(default_factory=dict)
    lessons: tuple[Lesson, ...] = ()

    def successful_cells(self) -> Counter[str]:
        """Count successes per cell, the seams the planner should revisit."""
        return Counter(prompt.cell_key for prompt in self.prompts if self._success(prompt))

    def accepted_cells(self) -> list[str]:
        """Return the cell of every prompt that passed review and the gate."""
        return [prompt.cell_key for prompt in self.prompts if prompt.is_valid]

    def card_uses(self) -> Counter[str]:
        """Count the stored prompts written from each card."""
        return Counter(prompt.card_id for prompt in self.prompts if prompt.card_id)

    def card_results(self) -> dict[str, tuple[int, int]]:
        """Return (successes, scored) per card on this target. O(n) in prompts."""
        return self._results(lambda prompt: [prompt.card_id] if prompt.card_id else [])

    def lesson_results(self) -> dict[str, tuple[int, int]]:
        """Return (successes, scored) of the prompts written with each lesson."""
        return self._results(lambda prompt: prompt.lesson_ids)

    def seen_texts(self) -> list[str]:
        """Return every stored localized text, for the novelty gate."""
        return [prompt.localized_text for prompt in self.prompts]

    def scored_in_cell(self, cell_key: str) -> int:
        """Count the prompts of one cell that carry a verdict."""
        return sum(
            1
            for prompt in self.prompts
            if prompt.cell_key == cell_key and self._success(prompt) is not None
        )

    def best_lessons(self, cell_key: str, group: str, count: int) -> list[Lesson]:
        """Return the top lessons for a cell, by the scope its evidence earns.

        A cell with enough scored outcomes draws on its own lessons. Before
        that it draws on its group's lessons, so a fresh cell learns from the
        cells of its group.
        Ranking is by upper confidence bound over the lessons' records, whose
        exploration term shrinks with use. O(n) in prompts and lessons.
        """
        if self.scored_in_cell(cell_key) >= CELL_EVIDENCE_MIN:
            pool = [
                lesson
                for lesson in self.lessons
                if lesson.scope == CELL_SCOPE and lesson.scope_key == cell_key
            ]
        else:
            pool = [
                lesson
                for lesson in self.lessons
                if lesson.scope == GROUP_SCOPE and lesson.scope_key == group
            ]
        results = self.lesson_results()
        total = sum(results.get(lesson.lesson_id, (0, 0))[1] for lesson in pool)
        ranked = sorted(
            pool,
            key=lambda lesson: (_ucb(*results.get(lesson.lesson_id, (0, 0)), total), lesson.text),
            reverse=True,
        )
        return ranked[:count]

    def _results(
        self, keys: Callable[[GeneratedPrompt], Iterable[str]]
    ) -> dict[str, tuple[int, int]]:
        """Return (successes, scored) per key over the prompts with a verdict."""
        results: dict[str, list[int]] = {}
        for prompt in self.prompts:
            success = self._success(prompt)
            if success is None:
                continue
            for key in keys(prompt):
                counts = results.setdefault(key, [0, 0])
                counts[0] += success
                counts[1] += 1
        return {key: (wins, scored) for key, (wins, scored) in results.items()}

    def _success(self, prompt: GeneratedPrompt) -> bool | None:
        """Return one prompt's success verdict on this target, if it has one."""
        outcome = self.outcomes.get(prompt.prompt_id)
        return outcome.succeeded(self.axis) if outcome else None


def _ucb(successes: int, uses: int, total_uses: int) -> float:
    """Return the upper-confidence score of one lesson; untried is infinite."""
    if uses == 0:
        return math.inf
    return successes / uses + UCB_EXPLORATION * math.sqrt(math.log(total_uses + 1) / uses)
