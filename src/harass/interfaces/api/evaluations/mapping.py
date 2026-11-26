"""Map validated HTTP inputs to domain evaluation parameters."""

from harass.application.evaluation.contracts import RunParameters
from harass.domain.case_selection import CaseSelection
from harass.domain.prompt_variant import AdaptiveSettings, EvaluationMode, VariantSelection
from harass.interfaces.api.evaluations.schemas import RunRequest


def run_parameters(body: RunRequest) -> RunParameters:
    """Translate a run request into domain run parameters.

    The product's two run types use fixed protocols with the default attempt
    budget; requests without a run type choose every parameter themselves.
    """
    if body.run_type is not None:
        baseline = body.run_type == "baseline"
        return RunParameters(
            selection=CaseSelection(
                axis=body.selection.axis, varieties=frozenset(body.selection.varieties)
            ),
            variant_selection=VariantSelection((), ()) if baseline else VariantSelection(),
            adaptive_settings=AdaptiveSettings(
                EvaluationMode.STATIC if baseline else EvaluationMode.ADAPTIVE
            ),
        )
    return RunParameters(
        selection=CaseSelection.from_codes(**body.selection.model_dump()),
        include_baseline=body.include_baseline,
        max_base_cases_per_axis=body.max_base_cases_per_axis,
        sampling_seed=body.sampling_seed,
        variant_selection=VariantSelection(
            None if body.template_names is None else tuple(body.template_names),
            None if body.transform_names is None else tuple(body.transform_names),
        ),
        adaptive_settings=AdaptiveSettings(
            body.evaluation_mode, body.attempt_budget, body.sampling_seed
        ),
    )
