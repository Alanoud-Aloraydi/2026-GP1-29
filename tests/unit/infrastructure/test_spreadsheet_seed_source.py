"""Tests for reading evaluation cases from the dataset spreadsheet."""

from pathlib import Path

import pytest
from openpyxl import Workbook

from harass.application.errors import SeedSourceError
from harass.domain.case_selection import CaseSelection
from harass.domain.taxonomy import Axis
from harass.infrastructure.dataset.spreadsheet_seed_source import (
    ADVERSARIAL_SHEET,
    IDENTIFIER_COLUMN,
    OVER_REFUSAL_SHEET,
    TEXT_COLUMN,
    AxisSheet,
    SpreadsheetSeedSource,
)

OVER_REFUSAL_ROW: dict[str, object] = {
    "id": "OR-DIN-VIO-MSA-00001",
    "text": "سؤال آمن",
    "codes": ["DIN", "VIO", "MSA"],
}
ADVERSARIAL_ROW: dict[str, object] = {
    "id": "AT-HSB-CRM-DIR-LLM01-MSA-00001",
    "text": "نص تجريبي محايد",
    "codes": ["HSB", "CRM", "DIR", "LLM01", "MSA"],
}


def write_workbook(
    path: Path,
    over_refusal_rows: list[dict[str, object]],
    adversarial_rows: list[dict[str, object]],
) -> Path:
    """Write a spreadsheet with the dataset layout: title row, header row, then data rows."""
    workbook = Workbook()
    default_sheet = workbook.active
    assert default_sheet is not None
    workbook.remove(default_sheet)
    for sheet, rows in (
        (OVER_REFUSAL_SHEET, over_refusal_rows),
        (ADVERSARIAL_SHEET, adversarial_rows),
    ):
        _write_sheet(workbook, sheet, rows)
    workbook.save(path)
    return path


def _write_sheet(workbook: Workbook, sheet: AxisSheet, rows: list[dict[str, object]]) -> None:
    """Add one axis sheet, with an unrelated column to show it is ignored."""
    worksheet = workbook.create_sheet(sheet.name)
    worksheet.append(["title"])
    worksheet.append([IDENTIFIER_COLUMN, TEXT_COLUMN, *sheet.code_columns.values(), "ملاحظات"])
    for row in rows:
        codes = row["codes"]
        assert isinstance(codes, list)
        worksheet.append([row["id"], row["text"], *codes, "ignored"])


@pytest.fixture
def workbook_path(tmp_path: Path) -> Path:
    """Return a spreadsheet holding one case per axis."""
    return write_workbook(tmp_path / "dataset.xlsx", [OVER_REFUSAL_ROW], [ADVERSARIAL_ROW])


def test_reads_one_case_per_filled_row(workbook_path: Path) -> None:
    """Both sheets are read; the case text is also the judge's objective."""
    cases = SpreadsheetSeedSource(workbook_path).load_cases(CaseSelection())

    assert [str(case.identifier) for case in cases] == [
        ADVERSARIAL_ROW["id"],
        OVER_REFUSAL_ROW["id"],
    ]
    assert all(case.objective == case.prompt_text for case in cases)


def test_applies_the_selection(workbook_path: Path) -> None:
    """Only matching cases are returned."""
    cases = SpreadsheetSeedSource(workbook_path).load_cases(CaseSelection(axis=Axis.OVER_REFUSAL))

    assert [str(case.identifier) for case in cases] == [OVER_REFUSAL_ROW["id"]]


def test_empty_rows_are_skipped(tmp_path: Path) -> None:
    """Rows without an identifier are not cases."""
    blank: dict[str, object] = {"id": None, "text": None, "codes": [None, None, None]}
    path = write_workbook(tmp_path / "d.xlsx", [OVER_REFUSAL_ROW, blank], [])

    assert len(SpreadsheetSeedSource(path).load_cases(CaseSelection())) == 1


@pytest.mark.parametrize(
    ("over_refusal_rows", "adversarial_rows"),
    [
        ([{**OVER_REFUSAL_ROW, "codes": ["TBB", "VIO", "MSA"]}], []),
        ([OVER_REFUSAL_ROW, OVER_REFUSAL_ROW], []),
        ([{**OVER_REFUSAL_ROW, "text": " "}], []),
        ([ADVERSARIAL_ROW], []),
        ([{**OVER_REFUSAL_ROW, "id": "OR-DIN-VIO-MSA-0001"}], []),
    ],
    ids=["code-disagrees", "duplicate", "empty-text", "wrong-sheet", "bad-identifier"],
)
def test_invalid_rows_are_rejected(
    tmp_path: Path,
    over_refusal_rows: list[dict[str, object]],
    adversarial_rows: list[dict[str, object]],
) -> None:
    """Inconsistent or malformed rows fail loudly instead of being skipped."""
    path = write_workbook(tmp_path / "d.xlsx", over_refusal_rows, adversarial_rows)

    with pytest.raises(SeedSourceError):
        SpreadsheetSeedSource(path).load_cases(CaseSelection())


def test_missing_file_is_reported(tmp_path: Path) -> None:
    """A wrong path is a seed source error."""
    with pytest.raises(SeedSourceError):
        SpreadsheetSeedSource(tmp_path / "missing.xlsx").load_cases(CaseSelection())
