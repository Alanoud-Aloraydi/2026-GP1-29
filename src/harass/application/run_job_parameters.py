"""Decode persisted execution parameters without depending on HTTP schemas."""

from typing import Any

from harass.application.use_cases.manage_runs import RunParameters
from harass.domain.case_selection import CaseSelection
from harass.domain.prompt_variant import AdaptiveSettings, EvaluationMode, VariantSelection
from harass.domain.taxonomy import ArabicVariety, Axis, BypassStrategy, RiskCategory, SubjectDomain


def read_run_parameters(document: dict[str, Any]) -> RunParameters:
    """Restore validated enum values and paired-case selection from a job document."""
    selection, variants, adaptive = (
        document["selection"],
        document["variant_selection"],
        document["adaptive_settings"],
    )
    return RunParameters(
        selection=CaseSelection(
            axis=Axis(selection["axis"]) if selection["axis"] else None,
            subject_domains=frozenset(map(SubjectDomain, selection["subject_domains"])),
            risk_categories=frozenset(map(RiskCategory, selection["risk_categories"])),
            varieties=frozenset(map(ArabicVariety, selection["varieties"])),
            strategies=frozenset(map(BypassStrategy, selection["strategies"])),
        ),
        include_baseline=document["include_baseline"],
        max_base_cases_per_axis=document["max_base_cases_per_axis"],
        sampling_seed=document["sampling_seed"],
        variant_selection=VariantSelection(
            tuple(variants["template_names"]) if variants["template_names"] is not None else None,
            tuple(variants["transform_names"])
            if variants["transform_names"] is not None
            else None,
        ),
        adaptive_settings=AdaptiveSettings(
            EvaluationMode(adaptive["mode"]), adaptive["attempt_budget"], adaptive["random_seed"]
        ),
    )
