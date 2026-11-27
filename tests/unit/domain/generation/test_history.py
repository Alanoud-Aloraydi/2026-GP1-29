"""Tests for the generator's history: verdicts, counts and lesson choice."""

from harass.domain.generation.history import (
    CELL_EVIDENCE_MIN,
    CELL_SCOPE,
    GROUP_SCOPE,
    GeneratedPrompt,
    GenerationHistory,
    Lesson,
    PromptOutcome,
    group_key,
)
from harass.domain.taxonomy import Axis, ResponseCategory

TARGET = "target-model"
CELL = "OR-DIN-VIO-MSA"
ATTACK_CELL = "AT-HSB-CRM-ROL-LLM01-NAJ"
GROUP = "VIO-homonym"


def prompt(
    prompt_id: str,
    cell_key: str = CELL,
    card_id: str = "C-1",
    *,
    reviewer_passed: bool = True,
    intent_safe: bool = True,
    lesson_ids: tuple[str, ...] = (),
) -> GeneratedPrompt:
    """Return a stored prompt with the given gates and the lessons it read."""
    return GeneratedPrompt(
        prompt_id=prompt_id,
        case_id="OR-DIN-VIO-MSA-00001",
        axis=Axis.OVER_REFUSAL,
        cell_key=cell_key,
        device="homonym",
        card_id=card_id,
        round_index=0,
        written_text="written",
        localized_text=f"sent-{prompt_id}",
        sent_text=f"sent-{prompt_id}",
        reviewer_passed=reviewer_passed,
        intent_safe=intent_safe,
        lesson_ids=lesson_ids,
    )


def outcome(prompt_id: str, category: ResponseCategory) -> PromptOutcome:
    """Return one target outcome for a stored prompt."""
    return PromptOutcome(prompt_id, TARGET, category)


def history(
    prompts: tuple[GeneratedPrompt, ...] = (),
    outcomes: tuple[PromptOutcome, ...] = (),
    lessons: tuple[Lesson, ...] = (),
) -> GenerationHistory:
    """Return an over-refusal history of one target from its parts."""
    return GenerationHistory(
        target_model=TARGET,
        prompts=prompts,
        outcomes={item.prompt_id: item for item in outcomes},
        lessons=lessons,
    )


def lesson(lesson_id: str, scope: str = GROUP_SCOPE, key: str = GROUP) -> Lesson:
    """Return a lesson of one scope whose text is its identifier."""
    return Lesson(lesson_id, scope, key, lesson_id, TARGET)


def cited(
    lesson_id: str, wins: int, scored: int
) -> tuple[list[GeneratedPrompt], list[PromptOutcome]]:
    """Return prompts that read one lesson, ``wins`` of ``scored`` refused."""
    prompts = [prompt(f"{lesson_id}-{index}", lesson_ids=(lesson_id,)) for index in range(scored)]
    outcomes = [
        outcome(
            item.prompt_id,
            ResponseCategory.FULL_REFUSAL if index < wins else ResponseCategory.FULL_COMPLIANCE,
        )
        for index, item in enumerate(prompts)
    ]
    return prompts, outcomes


def test_an_unclear_reply_carries_no_verdict_on_either_axis() -> None:
    """Verify an unclear reply stays out of the refusal verdicts."""
    assert outcome("p1", ResponseCategory.FULL_REFUSAL).refused is True
    assert outcome("p1", ResponseCategory.PARTIAL_REFUSAL).refused is True
    assert outcome("p1", ResponseCategory.FULL_COMPLIANCE).refused is False
    assert outcome("p1", ResponseCategory.UNCLEAR).succeeded(Axis.OVER_REFUSAL) is None
    attack = PromptOutcome("p2", TARGET, ResponseCategory.FULL_COMPLIANCE, attack_succeeded=True)
    assert attack.succeeded(Axis.ADVERSARIAL) is True
    assert outcome("p3", ResponseCategory.FULL_REFUSAL).succeeded(Axis.ADVERSARIAL) is None


def test_only_prompts_past_both_gates_are_valid() -> None:
    """Verify a prompt needs the review and the safety gate to be sent."""
    assert prompt("p1").is_valid
    assert not prompt("p2", reviewer_passed=False).is_valid
    assert not prompt("p3", intent_safe=False).is_valid


def test_a_group_is_the_risk_with_its_device_or_strategy() -> None:
    """Verify over-refusal groups by device and attacks by strategy."""
    assert group_key(CELL, "homonym") == GROUP
    assert group_key(ATTACK_CELL, "persona") == "CRM-ROL"
    assert group_key(ATTACK_CELL, None) == "CRM-ROL"


def test_counts_separate_successes_from_unscored_prompts() -> None:
    """Verify successes, accepted cells and card results count correctly."""
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
    assert stored.successful_cells() == {CELL: 1}
    assert sorted(stored.accepted_cells()) == [CELL, CELL, other]
    assert stored.card_uses() == {"C-1": 3, "C-2": 1}
    assert stored.card_results() == {"C-1": (1, 1), "C-2": (0, 1)}
    assert stored.scored_in_cell(CELL) == 1
    assert stored.seen_texts() == ["sent-p1", "sent-p2", "sent-p3", "sent-p4"]


def test_a_lesson_s_record_is_read_from_the_prompts_that_cite_it() -> None:
    """Verify a lesson's successes come from the outcomes of prompts that read it."""
    prompts, outcomes = cited("L-1", wins=2, scored=3)
    stored = history(prompts=tuple(prompts), outcomes=tuple(outcomes))
    assert stored.lesson_results() == {"L-1": (2, 3)}


def test_a_fresh_cell_reads_its_group_s_lessons() -> None:
    """Verify a cell without evidence draws on its group, not on other cells."""
    stored = history(
        lessons=(
            lesson("cell", CELL_SCOPE, CELL),
            lesson("group"),
            lesson("other-group", GROUP_SCOPE, "VIO-public_info"),
        )
    )
    chosen = stored.best_lessons(CELL, GROUP, count=3)
    assert [item.lesson_id for item in chosen] == ["group"]


def test_an_evidenced_cell_reads_its_own_lessons_best_first() -> None:
    """Verify a cell with enough outcomes ranks its own lessons by success."""
    weak_prompts, weak_outcomes = cited("weak", wins=1, scored=CELL_EVIDENCE_MIN)
    strong_prompts, strong_outcomes = cited("strong", wins=3, scored=CELL_EVIDENCE_MIN)
    stored = history(
        prompts=(*weak_prompts, *strong_prompts),
        outcomes=(*weak_outcomes, *strong_outcomes),
        lessons=(lesson("weak", CELL_SCOPE, CELL), lesson("strong", CELL_SCOPE, CELL), lesson("g")),
    )
    chosen = stored.best_lessons(CELL, GROUP, count=2)
    assert [item.lesson_id for item in chosen] == ["strong", "weak"]


def test_an_untried_lesson_comes_before_a_proven_one() -> None:
    """Verify the confidence bound puts an unused lesson first."""
    prompts, outcomes = cited("proven", wins=3, scored=3)
    stored = history(
        prompts=tuple(prompts),
        outcomes=tuple(outcomes),
        lessons=(lesson("proven"), lesson("untried")),
    )
    assert [item.lesson_id for item in stored.best_lessons(CELL, GROUP, count=1)] == ["untried"]
