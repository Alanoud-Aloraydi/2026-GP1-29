"""Tests for the JSON report exporter."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from harass.application.errors import ReportExportError
from harass.application.evaluation.contracts import EvaluationReport
from harass.application.reporting.document import report_document
from harass.domain.case_identifier import CaseIdentifier
from harass.domain.case_outcome import CaseOutcome
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.metrics import compute_metrics
from harass.domain.prompt_variant import (
    AdaptiveSettings,
    EvaluationMode,
    VariantSelection,
)
from harass.domain.taxonomy import ResponseCategory
from harass.infrastructure.reporting.json_report_exporter import (
    JsonReportExporter,
)


def make_report() -> EvaluationReport:
    """Return a report with one successful attack and one unscored outcome."""
    outcomes = (
        CaseOutcome(
            case=EvaluationCase(
                identifier=CaseIdentifier.parse(
                    "AT-HSB-CRM-DIR-LLM01-MSA-00001"
                ),
                prompt_text="p",
                objective="o",
            ),
            variant_name="baseline",
            response_category=ResponseCategory.FULL_COMPLIANCE,
            attack_succeeded=True,
        ),
        CaseOutcome(
            case=EvaluationCase(
                identifier=CaseIdentifier.parse("OR-DIN-VIO-MSA-00001"),
                prompt_text="p",
                objective="o",
            ),
            variant_name="baseline",
            error="No response category score.",
        ),
    )
    return EvaluationReport(
        run_identifier="run",
        target_model="model",
        variant_names=(),
        include_baseline=True,
        outcomes=outcomes,
        metrics=compute_metrics(outcomes),
    )


def test_report_is_readable_utf8_json_with_agreed_labels(
    tmp_path: Path,
) -> None:
    """Verify report is readable utf8 json with agreed labels."""
    destination = tmp_path / "reports" / "run.json"

    JsonReportExporter().export(make_report(), destination)

    raw_text = destination.read_text(encoding="utf-8")
    document = json.loads(raw_text)
    assert "هجوم ناجح" in raw_text
    attack, unscored = document["outcomes"]
    assert attack["response_category"] == "FUL"
    assert attack["response_category_label"] == "امتثال كامل"
    assert attack["attack_outcome_label"] == "هجوم ناجح"
    assert unscored["response_category"] is None
    assert unscored["error"] == "No response category score."
    success = document["metrics"]["adversarial"]["attack_success"]
    assert (success["count"], success["total"], success["rate"]) == (1, 1, 1.0)
    assert success["wilson_95"] == pytest.approx([0.2065, 1.0], abs=1e-4)
    assert document["metrics"]["over_refusal"] is None
    assert document["metrics"]["unscored_outcomes"] == 1
    owasp = document["metrics"]["adversarial_breakdowns"]["owasp_category"]
    assert owasp["LLM01"]["attack_success"]["rate"] == 1


def test_unwritable_destination_is_reported(tmp_path: Path) -> None:
    """A destination that is a directory cannot be overwritten with a file."""
    with pytest.raises(ReportExportError):
        JsonReportExporter().export(make_report(), tmp_path)


def test_agentic_and_control_denominators_remain_separate() -> None:
    """Verify agentic and control denominators remain separate."""
    report = make_report()
    control = report.outcomes[0]
    generated = replace(
        control,
        variant_name="seed+tatweel",
        attempt_number=1,
        attack_succeeded=False,
    )
    outcomes = (control, generated)
    document = report_document(
        replace(
            report,
            outcomes=outcomes,
            metrics=compute_metrics(outcomes),
            adaptive_settings=AdaptiveSettings(EvaluationMode.ADAPTIVE, 8, 0),
            variant_selection=VariantSelection(),
        )
    )
    assert document["run_type"] == "agentic"
    assert (
        document["baseline_metrics"]["adversarial"]["attack_success"]["rate"]
        == 1
    )
    assert (
        document["primary_metrics"]["adversarial"]["attack_success"]["rate"]
        == 0
    )
    assert (
        document["primary_metrics"]["adversarial"]["attack_success"]["total"]
        == 1
    )


def test_baseline_report_scope_and_selection() -> None:
    """Verify baseline report scope and selection."""
    document = report_document(
        replace(make_report(), variant_selection=VariantSelection((), ()))
    )
    assert document["run_type"] == "baseline"
    assert document["adaptive"] is None
    assert document["primary_metrics"] == document["baseline_metrics"]
    assert json.loads(json.dumps(document))["selection"]["varieties"] == []
