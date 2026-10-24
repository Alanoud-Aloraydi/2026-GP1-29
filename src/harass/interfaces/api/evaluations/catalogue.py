"""Authenticated evaluation catalogue metadata."""

from dataclasses import asdict
from typing import Any

from fastapi import Depends, FastAPI

from harass.application.ports.variant_catalog import VariantCatalog
from harass.domain.taxonomy import (
    ArabicVariety,
    BypassStrategy,
    RiskCategory,
    SubjectDomain,
)
from harass.interfaces.api.accounts.dependencies import authenticated_owner
from harass.interfaces.api.evaluations.labels import AXES, DIALECTS, LABELS


def install_catalogue_routes(
    app: FastAPI, catalog: VariantCatalog | None
) -> None:
    """Register the endpoints with their injected application service."""

    @app.get("/evaluation-options")
    def evaluation_options(
        owner: str = Depends(authenticated_owner),
    ) -> dict[str, Any]:
        """Return supported classifications and authored library metadata."""
        return {
            "dialects": DIALECTS,
            "axes": AXES,
            "labels": LABELS,
            "varieties": [member.value for member in ArabicVariety],
            "subject_domains": [member.value for member in SubjectDomain],
            "risk_categories": [member.value for member in RiskCategory],
            "strategies": [member.value for member in BypassStrategy],
            "templates": [asdict(template) for template in catalog.templates()]
            if catalog
            else [],
            "transforms": [
                asdict(transform) for transform in catalog.transforms()
            ]
            if catalog
            else [],
        }
