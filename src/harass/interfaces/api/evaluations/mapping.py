"""Map validated HTTP inputs to domain evaluation parameters."""

from harass.application.evaluation.contracts import RunParameters
from harass.domain.case_selection import CaseSelection
from harass.interfaces.api.evaluations.schemas import RunRequest


def run_parameters(body: RunRequest) -> RunParameters:
    """Translate a run request into domain run parameters."""
    return RunParameters(
        selection=CaseSelection.from_codes(**body.selection.model_dump()),
        max_base_cases_per_axis=body.max_base_cases_per_axis,
        sampling_seed=body.sampling_seed,
    )
