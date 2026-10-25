"""Map validated HTTP inputs to domain evaluation parameters."""

from uuid import UUID

from harass.application.errors import (
    ApplicationError,
)
from harass.application.evaluation.parameters import RunParameters
from harass.domain.case_selection import CaseSelection
from harass.domain.prompt_variant import (
    AdaptiveSettings,
    EvaluationMode,
    VariantSelection,
)
from harass.domain.taxonomy import (
    ArabicVariety,
    Axis,
    BypassStrategy,
    RiskCategory,
    SubjectDomain,
)
from harass.interfaces.api.evaluations.schemas import (
    RunRequest,
    SelectionModel,
)


def run_parameters(body: RunRequest) -> RunParameters:
    """Translate a run request into domain run parameters."""
    if body.run_type is not None:
        # Product run types use fixed protocols; advanced requests omit them.
        selection = CaseSelection(
            axis=body.selection.axis,
            varieties=frozenset(body.selection.varieties),
        )
        return RunParameters(
            selection=selection,
            include_baseline=True,
            variant_selection=VariantSelection((), ())
            if body.run_type == "baseline"
            else VariantSelection(),
            adaptive_settings=AdaptiveSettings(
                EvaluationMode.STATIC
                if body.run_type == "baseline"
                else EvaluationMode.ADAPTIVE,
                8,
                0,
            ),
        )
    return RunParameters(
        selection=_selection(body.selection),
        include_baseline=body.include_baseline,
        max_base_cases_per_axis=body.max_base_cases_per_axis,
        sampling_seed=body.sampling_seed,
        variant_selection=VariantSelection(
            tuple(body.template_names)
            if body.template_names is not None
            else None,
            tuple(body.transform_names)
            if body.transform_names is not None
            else None,
        ),
        adaptive_settings=AdaptiveSettings(
            body.evaluation_mode, body.attempt_budget, body.sampling_seed
        ),
    )


def validated_identifier(
    value: str, error_type: type[ApplicationError]
) -> str:
    """Reject malformed entity IDs before PostgreSQL attempts to cast them."""
    try:
        return str(UUID(value))
    except ValueError as error:
        raise error_type("Record not found.") from error


def _selection(model: SelectionModel) -> CaseSelection:
    """Translate the selection model into the domain selection."""
    return CaseSelection(
        axis=Axis(model.axis) if model.axis else None,
        subject_domains=frozenset(map(SubjectDomain, model.subject_domains)),
        risk_categories=frozenset(map(RiskCategory, model.risk_categories)),
        varieties=frozenset(map(ArabicVariety, model.varieties)),
        strategies=frozenset(map(BypassStrategy, model.strategies)),
    )
