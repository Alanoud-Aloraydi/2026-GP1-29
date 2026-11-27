"""Serialize evaluation reports into JSON-compatible documents."""

from collections import Counter, defaultdict
from dataclasses import asdict, fields
from typing import Any

from harass.application.evaluation.contracts import EvaluationReport
from harass.application.reporting.labels import (
    ATTACK_OUTCOME_LABELS,
    METRIC_LABELS,
    RESPONSE_CATEGORY_LABELS,
)
from harass.domain.case_outcome import CaseOutcome
from harass.domain.metrics import (
    AdversarialSummary,
    EvaluationMetrics,
    OverRefusalSummary,
    PairedDifference,
    Proportion,
)
from harass.domain.taxonomy import ResponseCategory

REPORT_FORMAT_VERSION = 4


def report_document(report: EvaluationReport, *, include_outcomes: bool = True) -> dict[str, Any]:
    """Return the JSON-compatible representation of a report."""
    outcomes = list(report.outcomes)
    return {
        "format_version": REPORT_FORMAT_VERSION,
        "run_identifier": report.run_identifier,
        "target_model": report.target_model,
        "selection": {
            "axis": report.selection.axis.value if report.selection.axis else None,
            "varieties": sorted(report.selection.varieties),
            "subject_domains": sorted(report.selection.subject_domains),
            "risk_categories": sorted(report.selection.risk_categories),
            "strategies": sorted(report.selection.strategies),
        },
        "metric_labels": METRIC_LABELS,
        "metrics": _metrics_document(report.metrics),
        "outcomes_count": len(outcomes),
        "coverage": _coverage(outcomes),
        "response_categories": _response_categories(outcomes),
        "outcomes": [
            outcome_document(outcome)
            for outcome in sorted(outcomes, key=lambda outcome: str(outcome.case.identifier))
        ]
        if include_outcomes
        else [],
    }


def _metrics_document(metrics: EvaluationMetrics) -> dict[str, Any]:
    """Serialize overall and per-dimension metrics with their intervals."""
    risk_gaps = metrics.discrimination_gap_by_risk_category
    return {
        "adversarial": _summary(metrics.adversarial),
        "adversarial_breakdowns": _breakdowns(metrics.adversarial_breakdowns),
        "over_refusal": _summary(metrics.over_refusal),
        "over_refusal_breakdowns": _breakdowns(metrics.over_refusal_breakdowns),
        "discrimination_gap_by_risk_category": risk_gaps,
        "adversarial_variety_vs_msa": _paired(metrics.adversarial_variety_vs_msa),
        "over_refusal_variety_vs_msa": _paired(metrics.over_refusal_variety_vs_msa),
        "unscored_outcomes": metrics.unscored_outcomes,
    }


def _coverage(outcomes: list[CaseOutcome]) -> dict[str, dict[str, int]]:
    """Count sent, unscored, unclear and rule-suspected attempts per axis."""
    result: dict[str, dict[str, int]] = {}
    for outcome in outcomes:
        counts = result.setdefault(
            outcome.case.axis.value,
            {"submitted": 0, "unscored": 0, "unclear": 0, "suspected_unclear": 0},
        )
        counts["submitted"] += 1
        counts["unscored"] += not outcome.is_scored
        counts["unclear"] += (
            outcome.error is None and outcome.response_category is ResponseCategory.UNCLEAR
        )
        counts["suspected_unclear"] += outcome.comprehension_signal is not None
    return result


def _response_categories(outcomes: list[CaseOutcome]) -> dict[str, dict[str, int]]:
    """Count scored responses by category for each safety axis."""
    counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for outcome in outcomes:
        if outcome.is_scored and outcome.response_category is not None:
            counts[outcome.case.axis.value][outcome.response_category.value] += 1
    return {axis: dict(categories) for axis, categories in counts.items()}


def _proportion(proportion: Proportion) -> dict[str, Any]:
    """Serialize counts, rates and confidence intervals."""
    interval = proportion.wilson_interval()
    clustered = proportion.clustered_interval()
    return {
        "count": proportion.count,
        "total": proportion.total,
        "rate": proportion.rate,
        "wilson_95": list(interval) if interval else None,
        "clustered_standard_error": proportion.clustered_standard_error,
        "clustered_95": list(clustered) if clustered else None,
    }


def _paired(differences: dict[str, PairedDifference]) -> dict[str, dict[str, Any]]:
    """Serialize paired differences from MSA and their intervals."""
    return {
        variety: {
            "pairs": difference.pairs,
            "mean_difference": difference.mean,
            "standard_error": difference.standard_error,
            "interval_95": list(interval) if (interval := difference.interval()) else None,
        }
        for variety, difference in differences.items()
    }


def _summary(summary: AdversarialSummary | OverRefusalSummary | None) -> dict[str, Any] | None:
    """Return every proportion of a summary keyed by metric name."""
    if summary is None:
        return None
    return {field.name: _proportion(getattr(summary, field.name)) for field in fields(summary)}


def _breakdowns(
    breakdowns: dict[str, dict[str, AdversarialSummary]] | dict[str, dict[str, OverRefusalSummary]],
) -> dict[str, dict[str, Any]]:
    """Return the summaries of every dimension value."""
    return {
        dimension: {value: _summary(summary) for value, summary in groups.items()}
        for dimension, groups in breakdowns.items()
    }


def outcome_document(outcome: CaseOutcome) -> dict[str, Any]:
    """Return the original request, scenario evidence and verdicts."""
    category = outcome.response_category
    return {
        "case_id": str(outcome.case.identifier),
        "original_prompt": outcome.case.prompt_text,
        "objective": outcome.case.objective,
        "classification": asdict(outcome.case.identifier),
        "axis": outcome.case.axis.value,
        "scenario": outcome.scenario_name,
        "leak_exact_match": outcome.leak_exact_match,
        "leak_rouge_l": outcome.leak_rouge_l,
        "submission_uncertain": outcome.submission_uncertain,
        "technical_error": outcome.technical_error,
        "judge_requests": outcome.judge_requests,
        "elapsed_seconds": outcome.elapsed_seconds,
        "comprehension_signal": outcome.comprehension_signal,
        "response_category": category.value if category else None,
        "response_category_label": RESPONSE_CATEGORY_LABELS[category] if category else None,
        "attack_outcome_label": (
            None
            if outcome.attack_succeeded is None
            else ATTACK_OUTCOME_LABELS[outcome.attack_succeeded]
        ),
        "attack_succeeded": outcome.attack_succeeded,
        "error": outcome.error,
        "transcript": asdict(outcome.transcript) if outcome.transcript else None,
    }
