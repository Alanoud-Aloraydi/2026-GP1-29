"""Authenticated evaluation catalogue metadata."""

from typing import Any

from fastapi import Depends, FastAPI

from harass.application.evaluation.contracts import MAX_PROMPTS_PER_ROUND, MAX_ROUNDS
from harass.domain.generation.attack_briefs import ATTACK_DEVICES
from harass.domain.generation.transforms import TRANSFORMS
from harass.domain.taxonomy import (
    ArabicVariety,
    BypassStrategy,
    OwaspCategory,
    RiskCategory,
    SubjectDomain,
)
from harass.interfaces.api.accounts.dependencies import authenticated_owner
from harass.interfaces.api.evaluations.labels import (
    AXES,
    DIALECTS,
    LABELS,
    MECHANISM_LABELS,
    TRANSFORM_LABELS,
)

# Attack device codes are unique across strategies, so one mapping names
# every pattern a generated prompt can carry, on either axis.
DEVICE_LABELS = {
    **MECHANISM_LABELS,
    **{code: label for devices in ATTACK_DEVICES.values() for code, label in devices.items()},
}


def install_catalogue_routes(app: FastAPI) -> None:
    """Register the endpoint that lists the dataset's classifications."""

    @app.get("/evaluation-options")
    def evaluation_options(owner: str = Depends(authenticated_owner)) -> dict[str, Any]:
        """Return the supported classifications and their labels."""
        return {
            "dialects": DIALECTS,
            "axes": AXES,
            "labels": LABELS,
            "devices": DEVICE_LABELS,
            "varieties": [member.value for member in ArabicVariety],
            "subject_domains": [member.value for member in SubjectDomain],
            "risk_categories": [member.value for member in RiskCategory],
            "strategies": [member.value for member in BypassStrategy],
            "owasp_categories": [member.value for member in OwaspCategory],
            "agentic": {
                "max_rounds": MAX_ROUNDS,
                "max_prompts_per_round": MAX_PROMPTS_PER_ROUND,
                "transforms": [
                    {
                        "name": transform.name,
                        "label": TRANSFORM_LABELS[transform.name],
                        "attack_only": not transform.safe_for_over_refusal,
                    }
                    for transform in sorted(
                        TRANSFORMS, key=lambda item: list(TRANSFORM_LABELS).index(item.name)
                    )
                ],
            },
        }
