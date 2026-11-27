"""Tests for the agentic run: seeding from the baseline, durable rounds and its report."""

from collections.abc import Iterator
from dataclasses import replace
from typing import Any
from unittest.mock import Mock

import pytest
from test_generation_round import TARGET, FakeStore, RecordingPatternReader

from harass.application.evaluation.contracts import AgenticParameters
from harass.application.generation.agentic_run import RunAgenticEvaluation
from harass.application.generation.contracts import GenerationRequest, RoundReport
from harass.application.generation.generation_service import GenerateRound
from harass.application.generation.seeding import SEEDS_PER_GROUP, SeedFromBaseline
from harass.application.ports.evaluation import EvaluationJournal
from harass.application.ports.runs import (
    EvaluationSuspendedError,
    EvaluationYieldedError,
    RunAdmission,
    RunStore,
)
from harass.domain.case_outcome import CaseOutcome
from harass.domain.generation.history import GeneratedPrompt, Lesson, PromptOutcome
from harass.domain.taxonomy import Axis, ResponseCategory

OWNER = "owner-1"
RUN = "run-1"
BASELINE = "base-1"
BOTH_AXES = (Axis.OVER_REFUSAL, Axis.ADVERSARIAL)


def document(case_id: str, **fields: object) -> dict[str, object]:
    """Return one stored baseline outcome document with a verdict."""
    axis = case_id[:2]
    return {
        "case_id": case_id,
        "original_prompt": f"نص {case_id}",
        "axis": axis,
        "error": None,
        "submission_uncertain": False,
        "response_category": "REF" if axis == "OR" else "FUL",
        "attack_succeeded": True if axis == "AT" else None,
        **fields,
    }


def evidence(*documents: dict[str, object]) -> Mock:
    """Return baseline evidence that streams the given documents."""
    source = Mock(spec=RunAdmission)
    source.outcome_documents.side_effect = lambda run_id, owner_id: iter(documents)
    return source


async def test_seeds_are_read_from_refusals_and_fulfilled_attacks() -> None:
    """Verify each axis seeds from the target's failures on the dataset only."""
    store = FakeStore([])
    reader = RecordingPatternReader()
    baseline = evidence(
        document("OR-DIN-VIO-MSA-00001"),
        document("OR-DIN-VIO-MSA-00002", response_category="FUL"),
        document("OR-DIN-VIO-MSA-00003", response_category="UNC"),
        document("AT-HSB-CRM-ROL-LLM01-MSA-00001"),
        document("AT-HSB-CRM-ROL-LLM01-MSA-00002", attack_succeeded=False),
        document("AT-HSB-CRM-PER-NAP-MSA-00001", error="timeout"),
    )
    seeded = await SeedFromBaseline(store, reader, baseline).seed(
        TARGET.model_name, OWNER, BASELINE, BOTH_AXES
    )
    assert seeded == 2
    assert reader.texts == ["نص OR-DIN-VIO-MSA-00001", "نص AT-HSB-CRM-ROL-LLM01-MSA-00001"]
    attack = next(card for card in store.stored_cards if card.axis is Axis.ADVERSARIAL)
    assert (attack.strategy, attack.risk, attack.source) == ("ROL", "CRM", "baseline")
    assert {card.target_model for card in store.stored_cards} == {TARGET.model_name}
    baseline.outcome_documents.assert_called_once_with(BASELINE, OWNER)


async def test_seeding_reads_only_the_chosen_axis() -> None:
    """Verify a run on one axis reads no card from the other axis's successes."""
    store = FakeStore([])
    reader = RecordingPatternReader()
    baseline = evidence(
        document("OR-DIN-VIO-MSA-00001"), document("AT-HSB-CRM-ROL-LLM01-MSA-00001")
    )
    seeded = await SeedFromBaseline(store, reader, baseline).seed(
        TARGET.model_name, OWNER, BASELINE, (Axis.ADVERSARIAL,)
    )
    assert seeded == 1
    assert reader.texts == ["نص AT-HSB-CRM-ROL-LLM01-MSA-00001"]


async def test_seeding_keeps_a_few_cards_per_group_and_never_reads_one_twice() -> None:
    """Verify one group cannot crowd out the others, and seeding again adds nothing."""
    store = FakeStore([])
    reader = RecordingPatternReader()
    refusals = [document(f"OR-DIN-VIO-MSA-{index:05d}") for index in range(1, 9)]
    baseline = evidence(*refusals, document("OR-DIN-FRD-MSA-00001"))
    service = SeedFromBaseline(store, reader, baseline)
    assert await service.seed(TARGET.model_name, OWNER, BASELINE, BOTH_AXES) == SEEDS_PER_GROUP + 1
    assert await service.seed(TARGET.model_name, OWNER, BASELINE, BOTH_AXES) == 0
    assert len(reader.texts) == SEEDS_PER_GROUP + 1


class FakeJournal(EvaluationJournal):
    """Keep the run's checkpoint in memory."""

    def __init__(self) -> None:
        """Start without a checkpoint."""
        self.checkpoint: dict[str, Any] = {}
        self.units = 0

    def initialize(self, fingerprint: str, total_cases: int) -> dict[str, Any]:
        """Return the saved checkpoint and remember the unit count."""
        self.units = total_cases
        return dict(self.checkpoint)

    def reserve(self, checkpoint: dict[str, Any]) -> None:
        """Save the checkpoint."""
        self.checkpoint = dict(checkpoint)

    def commit(self, outcome: CaseOutcome, checkpoint: dict[str, Any]) -> None:
        """Never used by an agentic run."""
        raise AssertionError("An agentic run stores no case outcome.")

    def outcomes(self, *, lightweight: bool = False) -> Iterator[CaseOutcome]:
        """Never used by an agentic run."""
        raise AssertionError("An agentic run reads no case outcome.")


class RecordingRounds(GenerateRound):
    """Play rounds by storing one scored prompt each, recording the requests."""

    def __init__(self, store: FakeStore, *, scored: bool = True) -> None:
        """Bind the store the report reads."""
        self.requests: list[GenerationRequest] = []
        self._store = store
        self._scored = scored

    async def execute(self, request: GenerationRequest) -> RoundReport:
        """Store one prompt of the request's axis and its verdict."""
        self.requests.append(request)
        prompt = GeneratedPrompt(
            prompt_id=f"p-{len(self.requests)}",
            case_id="case",
            axis=request.axis,
            cell_key="cell",
            round_index=request.round_index,
            written_text="w",
            localized_text="l",
            sent_text="s",
            reviewer_passed=True,
            intent_safe=request.axis is Axis.OVER_REFUSAL,
            target_model=TARGET.model_name,
            run_id=request.run_identifier,
        )
        self._store.add_prompt(prompt)
        outcomes: tuple[PromptOutcome, ...] = ()
        if self._scored:
            outcome = PromptOutcome(
                prompt.prompt_id,
                TARGET.model_name,
                ResponseCategory.FULL_REFUSAL,
                attack_succeeded=False if request.axis is Axis.ADVERSARIAL else None,
            )
            self._store.add_outcome(outcome)
            outcomes = (outcome,)
        lesson = Lesson(f"L-{len(self.requests)}", "group", "g", "t", TARGET.model_name)
        return RoundReport(
            request.axis,
            request.round_index,
            TARGET.model_name,
            (prompt,),
            outcomes,
            lessons=(lesson,),
        )


def agentic(store: FakeStore, rounds: GenerateRound) -> tuple[RunAgenticEvaluation, Mock, Mock]:
    """Assemble the run with fake rounds, seeding and baseline report."""
    seeding = Mock(spec=SeedFromBaseline)
    seeding.seed.return_value = 3
    runs = Mock(spec=RunStore)
    runs.get_report.return_value = {
        "metrics": {
            "over_refusal": {"over_refusal": {"count": 2, "total": 10, "rate": 0.2}},
            "adversarial": None,
        }
    }
    return RunAgenticEvaluation(rounds, seeding, store, runs), seeding, runs


PARAMETERS = AgenticParameters(
    BASELINE, rounds=2, prompts_per_round=4, transform_names=("arabizi",)
)


async def play(
    service: RunAgenticEvaluation, journal: FakeJournal, parameters: AgenticParameters = PARAMETERS
) -> dict[str, Any]:
    """Call the run until it reports, as the worker does across its yields."""
    while True:
        try:
            return await service.execute(TARGET, parameters, RUN, OWNER, journal)
        except EvaluationYieldedError:
            continue


async def test_a_run_seeds_then_plays_every_round_on_both_axes() -> None:
    """Verify the unit order, the per-axis adapter and the final report."""
    store = FakeStore([])
    rounds = RecordingRounds(store)
    service, seeding, _ = agentic(store, rounds)
    journal = FakeJournal()
    report = await play(service, journal)
    assert journal.units == 4
    seeding.seed.assert_called_once_with(TARGET.model_name, OWNER, BASELINE, BOTH_AXES)
    assert [(r.round_index, r.axis) for r in rounds.requests] == [
        (0, Axis.OVER_REFUSAL),
        (0, Axis.ADVERSARIAL),
        (1, Axis.OVER_REFUSAL),
        (1, Axis.ADVERSARIAL),
    ]
    assert {r.count for r in rounds.requests} == {4}
    assert {r.run_identifier for r in rounds.requests} == {RUN}
    assert rounds.requests[0].transform_names == ()
    assert rounds.requests[1].transform_names == ("arabizi",)
    assert report["kind"] == "agentic"
    assert report["seeded_cards"] == 3
    assert report["prompts_count"] == 4
    assert [(entry["round"], entry["axis"]) for entry in report["rounds"]] == [
        (0, "OR"),
        (0, "AT"),
        (1, "OR"),
        (1, "AT"),
    ]
    assert report["rounds"][0]["phase"] == "measurement"
    assert report["rounds"][0]["lessons"] == 1
    assert report["axes"]["OR"]["measurement"]["rate"] == 1.0
    assert report["axes"]["AT"]["discovery"]["rate"] == 0.0
    assert report["axes"]["OR"]["baseline"]["rate"] == 0.2
    assert report["axes"]["AT"]["baseline"] is None


async def test_a_run_on_one_axis_plays_and_reports_only_that_axis() -> None:
    """Verify the chosen axis alone is seeded, played and reported."""
    store = FakeStore([])
    rounds = RecordingRounds(store)
    service, seeding, _ = agentic(store, rounds)
    journal = FakeJournal()
    parameters = replace(PARAMETERS, axes=(Axis.ADVERSARIAL,))
    report = await play(service, journal, parameters)
    assert journal.units == 2
    seeding.seed.assert_called_once_with(TARGET.model_name, OWNER, BASELINE, (Axis.ADVERSARIAL,))
    assert [(r.round_index, r.axis) for r in rounds.requests] == [
        (0, Axis.ADVERSARIAL),
        (1, Axis.ADVERSARIAL),
    ]
    assert set(report["axes"]) == {"AT"}
    assert {entry["axis"] for entry in report["rounds"]} == {"AT"}


async def test_a_round_interrupted_mid_way_is_not_played_again() -> None:
    """Verify a unit reserved before a crash is skipped and marked interrupted."""
    store = FakeStore([])
    rounds = RecordingRounds(store)
    service, _, _ = agentic(store, rounds)
    journal = FakeJournal()
    journal.checkpoint = {
        "case_index": 1,
        "seeded_cards": 0,
        "pending": True,
        "silent_rounds": 0,
        "learned": [{"axis": "OR", "round": 0, "lessons": 0, "cards": 0, "interrupted": False}],
    }
    report = await play(service, journal)
    assert [(r.round_index, r.axis) for r in rounds.requests] == [
        (1, Axis.OVER_REFUSAL),
        (1, Axis.ADVERSARIAL),
    ]
    assert [entry["interrupted"] for entry in report["rounds"]] == [False, True, False, False]


async def test_rounds_that_reach_no_verdict_suspend_the_run() -> None:
    """Verify an unreachable target suspends the run instead of burning rounds."""
    store = FakeStore([])
    rounds = RecordingRounds(store, scored=False)
    service, _, _ = agentic(store, rounds)
    journal = FakeJournal()
    with pytest.raises(EvaluationSuspendedError):
        await play(service, journal)
    assert len(rounds.requests) == 2
    assert journal.checkpoint["case_index"] == 2
