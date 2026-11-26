"""Tests for the generator's history: verdicts, counts and lesson choice."""

from harass.domain.generation.history import (
    CELL_EVIDENCE_MIN,
    CELL_SCOPE,
    GROUP_SCOPE,
    SEED_SCOPE,
    SEED_TARGET,
    GeneratedPrompt,
    GenerationHistory,
    Lesson,
    PromptOutcome,
)
from harass.domain.taxonomy import ResponseCategory

TARGET = "target-model"
CELL = "OR-DIN-VIO-MSA"


def prompt(
    prompt_id: str,
    cell_key: str = CELL,
    card_id: str = "C-1",
    *,
    reviewer_passed: bool = True,
    intent_safe: bool = True,
) -> GeneratedPrompt:
    """Return a stored prompt with the given gates."""
    return GeneratedPrompt(
        prompt_id=prompt_id,
        case_id="OR-DIN-VIO-MSA-00001",
        cell_key=cell_key,
        mechanism="homonym",
        card_id=card_id,
        round_index=0,
        written_text="written",
        sent_text=f"sent-{prompt_id}",
        reviewer_passed=reviewer_passed,
        intent_safe=intent_safe,
    )


def outcome(prompt_id: str, category: ResponseCategory) -> PromptOutcome:
    """Return one target outcome for a stored prompt."""
    return PromptOutcome(prompt_id, TARGET, category)


def history(
    prompts: tuple[GeneratedPrompt, ...] = (),
    outcomes: tuple[PromptOutcome, ...] = (),
    lessons: tuple[Lesson, ...] = (),
) -> GenerationHistory:
    """Return a history of one target from its parts."""
    return GenerationHistory(
        target_model=TARGET,
        prompts=prompts,
        outcomes={item.prompt_id: item for item in outcomes},
        lessons=lessons,
    )


def test_an_unclear_reply_carries_no_refusal_verdict() -> None:
    """Verify an unclear reply stays out of the refusal verdicts."""
    assert outcome("p1", ResponseCategory.FULL_REFUSAL).refused is True
    assert outcome("p1", ResponseCategory.PARTIAL_REFUSAL).refused is True
    assert outcome("p1", ResponseCategory.FULL_COMPLIANCE).refused is False
    assert outcome("p1", ResponseCategory.UNCLEAR).refused is None


def test_only_prompts_past_both_gates_are_valid() -> None:
    """Verify a prompt needs the review and the safety gate to be sent."""
    assert prompt("p1").is_valid
    assert not prompt("p2", reviewer_passed=False).is_valid
    assert not prompt("p3", intent_safe=False).is_valid


def test_counts_separate_refusals_from_unscored_prompts() -> None:
    """Verify refusals, accepted cells and card results count correctly."""
    other = "OR-TBB-HAT-NAJ"
    stored = history(
        prompts=(
            prompt("p1"),
            prompt("p2", cell_key=other, card_id="C-2"),
            prompt("p3", intent_safe=False),
            prompt("p4"),
        ),
        outcomes=(
            outcome("p1", ResponseCategory.FULL_REFUSAL),
            outcome("p2", ResponseCategory.FULL_COMPLIANCE),
            outcome("p4", ResponseCategory.UNCLEAR),
        ),
    )
    assert stored.refused_cells() == {CELL: 1}
    assert sorted(stored.accepted_cells()) == [CELL, CELL, other]
    assert stored.card_uses() == {"C-1": 3, "C-2": 1}
    assert stored.card_results() == {"C-1": (1, 1), "C-2": (0, 1)}
    assert stored.scored_in_cell(CELL) == 1
    assert stored.seen_texts() == ["sent-p1", "sent-p2", "sent-p3", "sent-p4"]


def lesson(lesson_id: str, scope: str, key: str, target: str, uses: int, wins: int) -> Lesson:
    """Return a lesson with a use record."""
    return Lesson(
        lesson_id=lesson_id,
        scope=scope,
        scope_key=key,
        text=lesson_id,
        target_model=target,
        uses=uses,
        successes=wins,
    )


def test_a_fresh_cell_reads_the_broad_and_seeded_lessons() -> None:
    """Verify a cell without evidence draws on the risk-level pools only."""
    stored = history(
        lessons=(
            lesson("cell", CELL_SCOPE, CELL, TARGET, 5, 5),
            lesson("broad", GROUP_SCOPE, "VIO-homonym", TARGET, 4, 2),
            lesson("seed", SEED_SCOPE, "VIO", SEED_TARGET, 4, 1),
            lesson("other-target", GROUP_SCOPE, "VIO-homonym", "elsewhere", 4, 4),
        )
    )
    chosen = stored.best_lessons(CELL, "VIO", "homonym", count=3)
    assert chosen == ["broad", "seed"]


def test_an_evidenced_cell_reads_its_own_lessons_best_first() -> None:
    """Verify a cell with enough outcomes ranks its own lessons by success."""
    scored = tuple(prompt(f"p{index}") for index in range(CELL_EVIDENCE_MIN))
    verdicts = tuple(
        outcome(f"p{index}", ResponseCategory.FULL_COMPLIANCE) for index in range(CELL_EVIDENCE_MIN)
    )
    stored = history(
        prompts=scored,
        outcomes=verdicts,
        lessons=(
            lesson("weak", CELL_SCOPE, CELL, TARGET, 4, 1),
            lesson("strong", CELL_SCOPE, CELL, TARGET, 4, 3),
            lesson("broad", GROUP_SCOPE, "VIO-homonym", TARGET, 1, 1),
        ),
    )
    assert stored.best_lessons(CELL, "VIO", "homonym", count=2) == ["strong", "weak"]


def test_an_untried_lesson_comes_before_a_proven_one() -> None:
    """Verify the confidence bound puts an unused lesson first."""
    stored = history(
        lessons=(
            lesson("proven", GROUP_SCOPE, "VIO-homonym", TARGET, 9, 9),
            lesson("untried", GROUP_SCOPE, "VIO-homonym", TARGET, 0, 0),
        )
    )
    assert stored.best_lessons(CELL, "VIO", "homonym", count=1) == ["untried"]
