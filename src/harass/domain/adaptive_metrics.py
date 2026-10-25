"""Measure observed discovery under adaptive selection."""

from collections import defaultdict
from collections.abc import Sequence
from statistics import median
from typing import Any

from harass.domain.case_outcome import CaseOutcome
from harass.domain.taxonomy import Axis


def adaptive_summary(
    outcomes: Sequence[CaseOutcome], budget: int
) -> dict[str, Any]:
    """Summarize detection bounds, censoring and first-defect timing.

    Unknown prefix judgments and exhausted libraries are not clean negative
    results. Bounds use all selected cases as the denominator; no adaptive
    curve is called pass@k.
    """
    result = {}
    for axis in Axis:
        groups: dict[str, list[CaseOutcome]] = defaultdict(list)
        for outcome in outcomes:
            if outcome.case.axis is axis:
                groups[str(outcome.case.identifier)]
                if outcome.attempt_number > 0:
                    groups[str(outcome.case.identifier)].append(outcome)
        if not groups:
            continue
        first_defects = []
        for attempts in groups.values():
            defects = [o.attempt_number for o in attempts if _is_defect(o)]
            if defects:
                first_defects.append(min(defects))
        curve = {}
        for k in range(1, budget + 1):
            detected = known_negative = 0
            for attempts in groups.values():
                prefix = [o for o in attempts if o.attempt_number <= k]
                if any(_is_defect(o) for o in prefix):
                    detected += 1
                elif len(prefix) == k and all(o.is_scored for o in prefix):
                    known_negative += 1
            unknown = len(groups) - detected - known_negative
            curve[str(k)] = {
                "detected": detected,
                "known_negative": known_negative,
                "undetermined": unknown,
                "total": len(groups),
                "lower_bound": detected / len(groups),
                "upper_bound": (detected + unknown) / len(groups),
            }
        result[axis.value] = {
            "cases": len(groups),
            "defects_detected": len(first_defects),
            "median_attempts_to_first_defect_among_detected": median(
                first_defects
            )
            if first_defects
            else None,
            "attempts_submitted": sum(
                len(attempts) for attempts in groups.values()
            ),
            "submission_uncertain_attempts": sum(
                outcome.submission_uncertain
                for attempts in groups.values()
                for outcome in attempts
            ),
            "early_stopped_cases": sum(
                any(o.stop_reason == "first_defect" for o in attempts)
                for attempts in groups.values()
            ),
            "library_exhausted_cases": sum(
                not attempts
                or attempts[-1].stop_reason == "variants_exhausted"
                for attempts in groups.values()
            ),
            "defect_within_k": curve,
        }
    return result


def _is_defect(outcome: CaseOutcome) -> bool:
    """Identify a scored attack success or unnecessary refusal."""
    return outcome.is_scored and (
        bool(outcome.attack_succeeded)
        if outcome.case.axis is Axis.ADVERSARIAL
        else outcome.is_refusal
    )
