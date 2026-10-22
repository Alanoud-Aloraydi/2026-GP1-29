"""Evaluation-use-case checks with a recording engine and paired dataset seeds."""

import pytest

from harass.application.errors import NoMatchingCasesError
from harass.application.evaluation_report import EvaluationRequest
from harass.application.ports.evaluation_engine import EvaluationEngine
from harass.application.ports.evaluation_journal import EvaluationJournal
from harass.application.ports.seed_source import SeedSource
from harass.application.use_cases.run_evaluation import RunEvaluation
from harass.domain.case_identifier import CaseIdentifier
from harass.domain.case_outcome import CaseOutcome
from harass.domain.case_selection import CaseSelection
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.evaluation_plan import EvaluationPlan
from harass.domain.prompt_variant import VariantSelection
from harass.domain.target_connection import TargetConnection
from harass.domain.taxonomy import Axis, ResponseCategory

CONNECTION = TargetConnection("http://target.invalid/v1", "m", "k")


class InMemorySeedSource(SeedSource):
    """Serve two fixed seeds and apply the supplied selection."""

    def load_cases(self, selection: CaseSelection) -> list[EvaluationCase]:
        """Return the matching fixed cases."""
        cases = [
            EvaluationCase(CaseIdentifier.parse(f"OR-DIN-VIO-MSA-0000{n}"), "p", "o")
            for n in (1, 2)
        ]
        return [case for case in cases if selection.matches(case)]


class RecordingEngine(EvaluationEngine):
    """Record plans and return one refusal per selected seed."""

    def __init__(self) -> None:
        """Start without recorded plans."""
        self.plans: list[EvaluationPlan] = []

    async def evaluate(
        self,
        plan: EvaluationPlan,
        target: TargetConnection,
        run_identifier: str,
        *,
        journal: EvaluationJournal | None = None,
    ) -> list[CaseOutcome]:
        """Record the plan and supply scored outcomes."""
        self.plans.append(plan)
        return [
            CaseOutcome(case, "baseline", ResponseCategory.FULL_REFUSAL) for case in plan.cases
        ]


async def test_filters_and_sampling_reach_the_engine() -> None:
    """Template/transform selections and paired sampling survive orchestration."""
    engine = RecordingEngine()
    report = await RunEvaluation(InMemorySeedSource(), engine).execute(
        EvaluationRequest(
            CONNECTION,
            variant_selection=VariantSelection(("or_plain",), ("tatweel",)),
            max_base_cases_per_axis=1,
        )
    )
    assert engine.plans[0].variant_selection == VariantSelection(("or_plain",), ("tatweel",))
    assert len(engine.plans[0].cases) == 1
    assert report.variant_names == ("baseline",)


async def test_empty_selection_stops_before_engine_execution() -> None:
    """An empty filtered dataset cannot submit requests."""
    engine = RecordingEngine()
    with pytest.raises(NoMatchingCasesError):
        await RunEvaluation(InMemorySeedSource(), engine).execute(
            EvaluationRequest(
                CONNECTION,
                selection=CaseSelection(axis=Axis.ADVERSARIAL),
            )
        )
    assert not engine.plans
async def test_execution_settings_are_exported() -> None:
    """Preserve execution and sampling settings in the JSON report."""
    import json

    from harass.application.report_document import report_document

    settings = {
        "target_generation": {
            "temperature": 0.0,
            "max_completion_tokens": 4096,
        },
        "judge": {
            "provider": "typesafe",
            "model": "jev-1.13.0",
            "min_confidence": 0.8,
        },
        "dataset_sha256": "test-dataset-fingerprint",
    }

    report = await RunEvaluation(
        InMemorySeedSource(),
        RecordingEngine(),
        execution_settings=settings,
    ).execute(
        EvaluationRequest(
            CONNECTION,
            sampling_seed=42,
            max_base_cases_per_axis=1,
        )
    )

    document = json.loads(json.dumps(report_document(report)))

    assert document["execution_settings"] == {
        **settings,
        "sampling_seed": 42,
        "max_base_cases_per_axis": 1,
    }
    assert "sampling_seed" not in settings