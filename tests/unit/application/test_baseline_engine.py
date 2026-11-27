"""Tests for the engine that sends each dataset case once."""

from collections.abc import Iterator
from typing import Any

import pytest

from harass.application.evaluation.baseline_engine import BaselineEngine
from harass.application.evaluation.outcome_codec import read_outcome
from harass.application.ports.evaluation import AttemptExecutor, EvaluationJournal
from harass.application.ports.runs import EvaluationSuspendedError, EvaluationYieldedError
from harass.application.reporting.document import outcome_document
from harass.domain.case_identifier import CaseIdentifier
from harass.domain.case_outcome import CaseOutcome
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.evaluation_plan import EvaluationPlan
from harass.domain.target_connection import TargetConnection
from harass.domain.taxonomy import ResponseCategory

TARGET = TargetConnection("http://target.invalid/v1", "m", "k")
PLAN = EvaluationPlan(
    tuple(
        EvaluationCase(CaseIdentifier.parse(f"OR-DIN-VIO-MSA-0000{n}"), f"prompt {n}", "o")
        for n in (1, 2, 3)
    )
)


class Executor(AttemptExecutor):
    """Record what was sent and fail technically when told to."""

    def __init__(self, *, failing: bool = False) -> None:
        """Start with nothing sent."""
        self.sent: list[str] = []
        self._failing = failing

    async def execute(
        self, case: EvaluationCase, sent_prompt: str, target: TargetConnection, run_identifier: str
    ) -> CaseOutcome:
        """Return a refusal, or a technical failure without a verdict."""
        self.sent.append(sent_prompt)
        if self._failing:
            return CaseOutcome(case, error="Attempt failed.", technical_error="connection")
        return CaseOutcome(case, ResponseCategory.FULL_REFUSAL)


class Journal(EvaluationJournal):
    """Keep the checkpoint and committed outcomes in memory."""

    def __init__(self, checkpoint: dict[str, Any] | None = None) -> None:
        """Start from an optional saved checkpoint."""
        self.checkpoint = checkpoint or {}
        self.reserved: list[dict[str, Any]] = []
        self.committed: list[CaseOutcome] = []

    def initialize(self, fingerprint: str, total_cases: int) -> dict[str, Any]:
        """Return the saved checkpoint."""
        return self.checkpoint

    def reserve(self, checkpoint: dict[str, Any]) -> None:
        """Record the reservation made before a request."""
        self.reserved.append(checkpoint)

    def commit(self, outcome: CaseOutcome, checkpoint: dict[str, Any]) -> None:
        """Record the outcome and advance the checkpoint."""
        self.committed.append(outcome)
        self.checkpoint = checkpoint

    def outcomes(self, *, lightweight: bool = False) -> Iterator[CaseOutcome]:
        """Return the committed outcomes."""
        return iter(self.committed)


async def test_each_case_is_sent_once_as_written() -> None:
    """Verify every case reaches the target once, with its own text."""
    executor = Executor()
    outcomes = await BaselineEngine(executor).evaluate(PLAN, TARGET, "run")
    assert executor.sent == ["prompt 1", "prompt 2", "prompt 3"]
    assert [outcome.case for outcome in outcomes] == list(PLAN.cases)


async def test_an_interrupted_attempt_is_committed_without_resending() -> None:
    """Verify a reserved attempt is recorded as uncertain and never sent twice."""
    pending = CaseOutcome(PLAN.cases[0], error="interrupted", submission_uncertain=True)
    journal = Journal({"case_index": 0, "pending": outcome_document(pending)})
    executor = Executor()
    outcomes = await BaselineEngine(executor).evaluate(PLAN, TARGET, "run", journal=journal)
    assert executor.sent == ["prompt 2", "prompt 3"]
    assert outcomes[0].submission_uncertain
    assert len(journal.reserved) == 2
    assert read_outcome(journal.reserved[0]["pending"]).case == PLAN.cases[1]


async def test_repeated_failures_suspend_and_a_full_quantum_yields() -> None:
    """Verify three technical failures suspend and a full quantum yields."""
    failing = Journal()
    with pytest.raises(EvaluationSuspendedError):
        await BaselineEngine(Executor(failing=True)).evaluate(PLAN, TARGET, "run", journal=failing)
    assert failing.checkpoint["technical_failures"] == 3
    yielding = Journal()
    with pytest.raises(EvaluationYieldedError):
        await BaselineEngine(Executor(), quantum_attempts=2).evaluate(
            PLAN, TARGET, "run", journal=yielding
        )
    assert yielding.checkpoint["case_index"] == 2
