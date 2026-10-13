"""Load and sample dataset seeds, evaluate variants and compute auditable reports."""

import asyncio
import logging
import uuid

from harass.application.errors import NoMatchingCasesError
from harass.application.evaluation_report import EvaluationReport, EvaluationRequest
from harass.application.ports.evaluation_engine import EvaluationEngine
from harass.application.ports.evaluation_journal import EvaluationJournal
from harass.application.ports.seed_source import SeedSource
from harass.domain.evaluation_plan import EvaluationPlan, sample_base_cases
from harass.domain.metrics import compute_metrics

logger = logging.getLogger(__name__)


class RunEvaluation:
    """Orchestrate a run through framework-independent dataset and engine ports."""

    def __init__(self, seed_source: SeedSource, engine: EvaluationEngine) -> None:
        """Store the source and engine supplied by the composition root."""
        self._seed_source = seed_source
        self._engine = engine

    async def execute(
        self, request: EvaluationRequest, *, journal: EvaluationJournal | None = None
    ) -> EvaluationReport:
        """Sample paired base cases, run the policy and serialize the actual variant names."""
        cases = sample_base_cases(
            self._seed_source.load_cases(request.selection),
            max_base_cases_per_axis=request.max_base_cases_per_axis,
            random_seed=request.sampling_seed,
        )
        if not cases:
            raise NoMatchingCasesError("No evaluation case matches the selection.")
        plan = EvaluationPlan(
            cases=tuple(cases),
            include_baseline=request.include_baseline,
            variant_selection=request.variant_selection,
            adaptive_settings=request.adaptive_settings,
        )
        run_identifier = request.run_identifier or str(uuid.uuid4())
        logger.info(
            "Run %s: %d cases, mode %s",
            run_identifier,
            len(cases),
            request.adaptive_settings.mode.value,
        )
        outcomes = (
            await self._engine.evaluate(plan, request.target, run_identifier, journal=journal)
            if journal is not None
            else await self._engine.evaluate(plan, request.target, run_identifier)
        )
        metrics = (
            await asyncio.to_thread(compute_metrics, outcomes)
            if journal
            else compute_metrics(outcomes)
        )
        return EvaluationReport(
            run_identifier=run_identifier,
            target_model=request.target.model_name,
            variant_names=tuple(sorted({outcome.variant_name for outcome in outcomes})),
            include_baseline=plan.include_baseline,
            outcomes=tuple(outcomes),
            metrics=metrics,
            adaptive_settings=request.adaptive_settings,
            variant_selection=request.variant_selection,
            selection=request.selection,
        )
