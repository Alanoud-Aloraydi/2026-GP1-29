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
from harass.domain.adaptive_metrics import adaptive_summary
from harass.domain.case_outcome import BASELINE_VARIANT_NAME, CaseOutcome
from harass.domain.metrics import (
    AdversarialSummary,
    EvaluationMetrics,
    OverRefusalSummary,
    PairedDifference,
    Proportion,
    compute_metrics,
)
from harass.domain.prompt_variant import EvaluationMode
from harass.domain.taxonomy import ResponseCategory

REPORT_FORMAT_VERSION = 3


def report_document(report: EvaluationReport, *, include_outcomes: bool = True) -> dict[str, Any]:
    """Return the JSON-compatible representation of a report."""
    selection = report.variant_selection
    baseline_only = selection is not None and (
        selection.template_names == selection.transform_names == ()
    )
    adaptive = report.adaptive_settings.mode is EvaluationMode.ADAPTIVE
    baseline_outcomes: list[CaseOutcome] = []
    generated_outcomes: list[CaseOutcome] = []
    for outcome in report.outcomes:
        is_baseline = outcome.variant_name == BASELINE_VARIANT_NAME
        (baseline_outcomes if is_baseline else generated_outcomes).append(outcome)
    baseline = compute_metrics(baseline_outcomes)
    primary_outcomes = baseline_outcomes if baseline_only else generated_outcomes
    primary = baseline if baseline_only else compute_metrics(primary_outcomes)
    run_type = "baseline" if baseline_only else "static"
    if adaptive and not baseline_only:
        run_type = "agentic"
    return {
        "format_version": REPORT_FORMAT_VERSION,
        "run_identifier": report.run_identifier,
        "target_model": report.target_model,
        "variants": list(report.variant_names),
        "include_baseline": report.include_baseline,
        "evaluation_mode": report.adaptive_settings.mode.value,
        "run_type": run_type,
        "selection": {
            "axis": report.selection.axis.value if report.selection.axis else None,
            "varieties": sorted(report.selection.varieties),
            "subject_domains": sorted(report.selection.subject_domains),
            "risk_categories": sorted(report.selection.risk_categories),
            "strategies": sorted(report.selection.strategies),
        },
        "attempt_budget": report.adaptive_settings.attempt_budget,
        "controller_seed": report.adaptive_settings.random_seed,
        "metric_scope": "observed_attempts_policy_conditioned",
        "baseline_metrics": _metrics_document(baseline),
        "primary_metrics": _metrics_document(primary),
        "primary_metric_scope": "original_requests"
        if baseline_only
        else "generated_attempts_policy_conditioned",
        "strategy_breakdown_scope": ("original_seed_strategy_not_isolated_effect"),
        "variant_selection": asdict(selection) if selection else None,
        "adaptive": adaptive_summary(report.outcomes, report.adaptive_settings.attempt_budget)
        if adaptive
        else None,
        "metric_labels": METRIC_LABELS,
        "metrics": _metrics_document(report.metrics),
        "outcomes_count": len(report.outcomes),
        "coverage": _coverage(primary_outcomes),
        "response_categories": _response_categories(primary_outcomes),
        "coverage_count_scope": "recorded_logical_attempts",
        "outcomes": [
            outcome_document(outcome) for outcome in sorted(report.outcomes, key=_outcome_order)
        ]
        if include_outcomes
        else [],
    }


def _outcome_order(outcome: CaseOutcome) -> tuple[str, int, str]:
    """Order outcomes by case, then attempt, then recipe."""
    return (str(outcome.case.identifier), outcome.attempt_number, outcome.variant_name)


def _metrics_document(metrics: EvaluationMetrics) -> dict[str, Any]:
    """Serialize one explicitly separated cohort of observed attempts."""
    risk_gaps = metrics.discrimination_gap_by_risk_category
    return {
        "adversarial": _summary(metrics.adversarial),
        "adversarial_breakdowns": _breakdowns(metrics.adversarial_breakdowns),
        "over_refusal": _summary(metrics.over_refusal),
        "over_refusal_breakdowns": _breakdowns(metrics.over_refusal_breakdowns),
        "discrimination_gap_by_variant": metrics.discrimination_gap_by_variant,
        "discrimination_gap_by_risk_category": risk_gaps,
        "adversarial_variety_vs_msa": _paired(metrics.adversarial_variety_vs_msa),
        "over_refusal_variety_vs_msa": _paired(metrics.over_refusal_variety_vs_msa),
        "unscored_outcomes": metrics.unscored_outcomes,
    }


def _coverage(outcomes: list[CaseOutcome]) -> dict[str, dict[str, int]]:
    """Count recorded, unscored, unclear and rule-suspected attempts."""
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
    """Return the original request, recipe, scenario evidence and verdicts."""
    category = outcome.response_category
    return {
        "case_id": str(outcome.case.identifier),
        "original_prompt": outcome.case.prompt_text,
        "objective": outcome.case.objective,
        "classification": asdict(outcome.case.identifier),
        "axis": outcome.case.axis.value,
        "variant_name": outcome.variant_name,
        "variant": asdict(outcome.variant) if outcome.variant else None,
        "attempt_number": outcome.attempt_number,
        "stop_reason": outcome.stop_reason,
        "posterior_before": outcome.posterior_before,
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
