"""CSV review preparation and strict review-file parsing; no labels are manufactured."""

import csv
import json
from pathlib import Path
from typing import Any

from harass.domain.case_identifier import CaseIdentifier
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.owasp_scenario import scenario_for
from harass.domain.review import (
    HumanCategory,
    InvalidReviewDataError,
    LeakObservation,
    ReviewCase,
    calibrate_leak,
    review_agreement,
)
from harass.domain.taxonomy import ResponseCategory


def prepare_review(report_path: Path, destination: Path) -> None:
    """Write a blind review CSV, leaving every human category empty."""
    rows = _read_report(report_path)
    with destination.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "case_id",
                "variant_name",
                "original_prompt",
                "sent_prompt",
                "response",
                "human_category",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.case_id,
                    row.variant_name,
                    row.original_prompt,
                    row.sent_prompt,
                    row.response,
                    "",
                ]
            )


def score_review(report_path: Path, label_path: Path) -> dict[str, Any]:
    """Match explicit human labels to report outcomes and compute coverage and agreement."""
    labels = []
    for number, row in enumerate(
        _read_csv(label_path, {"case_id", "variant_name", "human_category"}), start=2
    ):
        raw = row["human_category"].strip()
        try:
            category = ResponseCategory(raw) if raw else None
        except ValueError as error:
            raise InvalidReviewDataError(
                f"CSV row {number}: human_category must be FUL, PRF, REF or UNC."
            ) from error
        labels.append(HumanCategory(row["case_id"].strip(), row["variant_name"].strip(), category))
    return review_agreement(_read_report(report_path), labels)


def prepare_leak_review(report_path: Path, destination: Path) -> None:
    """Export synthetic references and responses with blank leak labels and split assignments."""
    document = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("run_identifier"), str):
        raise InvalidReviewDataError("Leak review requires the report run identifier.")
    cases = _read_report(report_path)
    rows = []
    for row in cases:
        if not row.original_prompt.strip() or not row.response.strip():
            continue
        case = EvaluationCase(
            CaseIdentifier.parse(row.case_id), row.original_prompt, row.original_prompt
        )
        scenario = scenario_for(case, document["run_identifier"])
        if scenario.protected_content and scenario.protected_marker:
            rows.append(
                [
                    row.case_id,
                    row.variant_name,
                    scenario.protected_content,
                    scenario.protected_marker,
                    row.response,
                    "",
                    "",
                    "human",
                ]
            )
    if not rows:
        raise InvalidReviewDataError(
            "No responded LLM02/LLM08 outcomes are available for leak review."
        )
    with destination.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "case_id",
                "variant_name",
                "protected_content",
                "protected_marker",
                "response",
                "leak_label",
                "split",
                "label_source",
            ]
        )
        writer.writerows(rows)


def score_leak_calibration(label_path: Path) -> dict[str, Any]:
    """Evaluate labelled CSV evidence using separate calibration and evaluation sets."""
    required = {
        "protected_content",
        "protected_marker",
        "response",
        "leak_label",
        "split",
        "label_source",
    }
    observations = []
    for number, row in enumerate(_read_csv(label_path, required), start=2):
        label = row["leak_label"].strip().lower()
        if label not in {"yes", "no"}:
            raise InvalidReviewDataError(
                f"CSV row {number}: leak_label must be yes or no; blanks are not labels."
            )
        observations.append(
            LeakObservation(
                row["protected_content"],
                row["protected_marker"],
                row["response"],
                label == "yes",
                row["split"].strip(),
                row["label_source"].strip(),
            )
        )
    return calibrate_leak(observations)


def _read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not required.issubset(set(reader.fieldnames or [])):
            raise InvalidReviewDataError(
                f"CSV {path} lacks required columns: {', '.join(sorted(required))}."
            )
        rows = []
        for row in reader:
            if any(row.get(column) is None for column in required):
                raise InvalidReviewDataError(f"CSV {path} contains an incomplete row.")
            rows.append({column: row[column] for column in required})
        return rows


def _read_report(path: Path) -> list[ReviewCase]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("outcomes"), list):
        raise InvalidReviewDataError(f"Report {path} must contain an outcomes list.")
    cases = []
    try:
        for outcome in document["outcomes"]:
            category = outcome.get("response_category")
            transcript = outcome.get("transcript") or {}
            variant_name = outcome.get("variant_name", outcome.get("chain"))
            if not isinstance(outcome["case_id"], str) or not isinstance(variant_name, str):
                raise ValueError("Outcome identity is missing.")
            cases.append(
                ReviewCase(
                    outcome["case_id"],
                    variant_name,
                    ResponseCategory(category) if category else None,
                    outcome.get("original_prompt", ""),
                    transcript.get("sent_prompt", ""),
                    transcript.get("response", ""),
                )
            )
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise InvalidReviewDataError(
            f"Report {path} has malformed outcome identities or categories."
        ) from error
    return cases
