"""Select paired seeds and compute auditable evaluation reports."""

import asyncio
import logging
import uuid

from harass.application.errors import NoMatchingCasesError
from harass.application.evaluation.contracts import EvaluationReport, EvaluationRequest
from harass.application.ports.evaluation import EvaluationEngine, EvaluationJournal, SeedSource
from harass.domain.evaluation_plan import EvaluationPlan, sample_base_cases
from harass.domain.metrics import compute_metrics

logger = logging.getLogger(__name__)


class RunEvaluation:
    """Coordinate framework-independent evaluation ports."""

    def __init__(self, seed_source: SeedSource, engine: EvaluationEngine) -> None:
        """Store the source and engine supplied by the composition root."""
        self._seed_source = seed_source
        self._engine = engine

    async def execute(
        self, request: EvaluationRequest, *, journal: EvaluationJournal | None = None
    ) -> EvaluationReport:
        """Evaluate selected paired seeds and build the report."""
        parameters = request.parameters
        cases = sample_base_cases(
            self._seed_source.load_cases(parameters.selection),
            max_base_cases_per_axis=parameters.max_base_cases_per_axis,
            random_seed=parameters.sampling_seed,
        )
        if not cases:
            raise NoMatchingCasesError("No evaluation case matches the selection.")
        plan = EvaluationPlan(
            cases=tuple(cases),
            include_baseline=parameters.include_baseline,
            variant_selection=parameters.variant_selection,
            adaptive_settings=parameters.adaptive_settings,
        )
        run_identifier = request.run_identifier or str(uuid.uuid4())
        logger.info(
            "Run %s: %d cases, mode %s",
            run_identifier,
            len(cases),
            parameters.adaptive_settings.mode.value,
        )
        outcomes = await self._engine.evaluate(
            plan, request.target, run_identifier, journal=journal
        )
        # Journaled runs can be large, so their metrics leave the event loop.
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
            adaptive_settings=parameters.adaptive_settings,
            variant_selection=parameters.variant_selection,
            selection=parameters.selection,
        )
