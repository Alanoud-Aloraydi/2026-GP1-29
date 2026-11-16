"""Tests for blind annotation sheets."""

import csv
from pathlib import Path

from harass.domain.judge_benchmark import AttackVerdict, GoldCase
from harass.domain.taxonomy import Axis, ResponseCategory
from harass.infrastructure.reporting.annotation_sheet import (
    COLUMNS,
    write_annotation_sheet,
)


def test_sheet_hides_gold_labels_and_leaves_rater_columns_blank(
    tmp_path: Path,
) -> None:
    """Raters see the request and response but never the gold labels."""
    case = GoldCase(
        key="m|AT-1",
        family="m|0001",
        axis=Axis.ADVERSARIAL,
        dialect="MSA",
        request="نص الطلب",
        response="نص الرد",
        criterion="المعيار",
        category=ResponseCategory.FULL_REFUSAL,
        attack_success=AttackVerdict.FALSE,
        truncated=False,
    )
    destination = tmp_path / "sheet.csv"

    write_annotation_sheet([case], destination)

    with destination.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert list(rows[0]) == list(COLUMNS)
    assert rows[0]["request"] == "نص الطلب"
    assert rows[0]["criterion"] == "المعيار"
    assert rows[0]["rater_category"] == ""
    assert rows[0]["rater_attack_success"] == ""
    assert rows[0]["rater_request_safe"] == ""
    assert "REF" not in destination.read_text(encoding="utf-8-sig")
    assert "FALSE" not in destination.read_text(encoding="utf-8-sig")
