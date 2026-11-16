"""Tests for reading the judge gold set."""

from pathlib import Path

import pytest
from openpyxl import Workbook

from harass.application.errors import GoldSetError
from harass.domain.judge_benchmark import AttackVerdict
from harass.domain.taxonomy import Axis, ResponseCategory
from harass.infrastructure.dataset.gold_set_source import load_gold_cases

COMMON = [
    "Master_Dataset_Code",
    "Dialect",
    "Sent_Prompt",
    "Target_Response",
    "Response_Category",
    "Target_Model",
    "Execution_Status",
]


def write_workbook(
    path: Path,
    over_refusal: list[list[str]],
    attack: list[list[str]] | None = None,
) -> None:
    """Write a gold workbook with the given rows."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Over_Refusal"
    sheet.append(COMMON)
    for row in over_refusal:
        sheet.append(row)
    attack_sheet = workbook.create_sheet("Attack")
    attack_sheet.append([*COMMON, "Criterion", "Attack_Success"])
    for row in attack or []:
        attack_sheet.append(row)
    workbook.save(path)


def over_refusal_row(code: str, dialect: str = "MSA") -> list[str]:
    """Return a valid over-refusal row."""
    return [code, dialect, "q", "a", "REF", "model-x", "COMPLETE"]


def test_cases_carry_gold_labels_and_family(tmp_path: Path) -> None:
    """Dialect variants of one base case share a family."""
    path = tmp_path / "gold.xlsx"
    write_workbook(
        path,
        [
            over_refusal_row("OR-HSB-CRM-MSA-00001"),
            over_refusal_row("OR-HSB-CRM-NAJ-10001", "NAJ"),
        ],
        [
            [
                "AT-HSB-CRM-PER-LLM01-MSA-00007",
                "MSA",
                "q",
                "a",
                "FUL",
                "model-y",
                "TRUNCATED",
                "criterion text",
                "true",
            ]
        ],
    )

    cases = load_gold_cases(path)

    first, second, attack = cases
    assert first.family == second.family == "model-x|0001"
    assert first.key != second.key
    assert first.category is ResponseCategory.FULL_REFUSAL
    assert first.attack_success is None
    assert attack.axis is Axis.ADVERSARIAL
    assert attack.attack_success is AttackVerdict.TRUE
    assert attack.criterion == "criterion text"
    assert attack.truncated


def test_missing_file_and_sheet_are_reported(tmp_path: Path) -> None:
    """A missing workbook or sheet raises a gold set error."""
    with pytest.raises(GoldSetError, match="does not exist"):
        load_gold_cases(tmp_path / "absent.xlsx")
    workbook = Workbook()
    workbook.save(tmp_path / "empty.xlsx")
    with pytest.raises(GoldSetError, match="missing"):
        load_gold_cases(tmp_path / "empty.xlsx")


def test_duplicate_cases_are_rejected(tmp_path: Path) -> None:
    """The same model and code cannot appear twice."""
    path = tmp_path / "gold.xlsx"
    row = over_refusal_row("OR-HSB-CRM-MSA-00001")
    write_workbook(path, [row, row])

    with pytest.raises(GoldSetError, match="twice"):
        load_gold_cases(path)


def test_invalid_label_names_the_row(tmp_path: Path) -> None:
    """An unknown response category identifies its sheet and row."""
    path = tmp_path / "gold.xlsx"
    row = over_refusal_row("OR-HSB-CRM-MSA-00001")
    row[4] = "MAYBE"
    write_workbook(path, [row])

    with pytest.raises(GoldSetError, match="row 2"):
        load_gold_cases(path)


def test_empty_response_is_rejected(tmp_path: Path) -> None:
    """A case without a response cannot be judged."""
    path = tmp_path / "gold.xlsx"
    row = over_refusal_row("OR-HSB-CRM-MSA-00001")
    row[3] = ""
    write_workbook(path, [row])

    with pytest.raises(GoldSetError, match="Target_Response is empty"):
        load_gold_cases(path)
