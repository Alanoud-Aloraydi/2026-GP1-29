"""Read the reviewed judge gold set from its workbook."""

from collections.abc import Iterator
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from harass.application.errors import GoldSetError
from harass.domain.judge_benchmark import AttackVerdict, GoldCase
from harass.domain.taxonomy import Axis, ResponseCategory

COMMON_COLUMNS = (
    "Master_Dataset_Code",
    "Dialect",
    "Sent_Prompt",
    "Target_Response",
    "Response_Category",
    "Target_Model",
    "Execution_Status",
)
ATTACK_COLUMNS = ("Criterion", "Attack_Success")
SHEET_AXES = {"Over_Refusal": Axis.OVER_REFUSAL, "Attack": Axis.ADVERSARIAL}
FAMILY_DIGITS = 4


def load_gold_cases(workbook_path: Path) -> list[GoldCase]:
    """Load every reviewed case, rejecting duplicate or malformed rows."""
    if not workbook_path.is_file():
        raise GoldSetError(f"Gold set {workbook_path} does not exist.")
    try:
        workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    except Exception as error:
        raise GoldSetError(f"Cannot read {workbook_path}: {error}") from error
    cases: dict[str, GoldCase] = {}
    try:
        for sheet_name, axis in SHEET_AXES.items():
            if sheet_name not in workbook.sheetnames:
                raise GoldSetError(f"Sheet '{sheet_name}' is missing.")
            for case in _read_sheet(workbook[sheet_name], sheet_name, axis):
                if case.key in cases:
                    raise GoldSetError(f"Case {case.key} appears twice.")
                cases[case.key] = case
    finally:
        workbook.close()
    return list(cases.values())


def _read_sheet(
    worksheet: Worksheet, sheet_name: str, axis: Axis
) -> Iterator[GoldCase]:
    """Yield one gold case per filled row of an axis sheet."""
    rows = worksheet.iter_rows(values_only=True)
    header = [_text(cell) for cell in next(rows)]
    required = COMMON_COLUMNS + (
        ATTACK_COLUMNS if axis is Axis.ADVERSARIAL else ()
    )
    missing = [column for column in required if column not in header]
    if missing:
        raise GoldSetError(f"Sheet '{sheet_name}' lacks columns {missing}.")
    for number, row in enumerate(rows, start=2):
        values = {
            column: _text(row[header.index(column)]) for column in required
        }
        if not values["Master_Dataset_Code"]:
            continue
        try:
            yield _case(values, axis)
        except ValueError as error:
            raise GoldSetError(
                f"Sheet '{sheet_name}', row {number}: {error}"
            ) from error


def _case(values: dict[str, str], axis: Axis) -> GoldCase:
    """Build a gold case from the text of one row."""
    model = values["Target_Model"]
    code = values["Master_Dataset_Code"]
    for column in ("Target_Model", "Sent_Prompt", "Target_Response"):
        if not values[column]:
            raise ValueError(f"{column} is empty.")
    attack = (
        AttackVerdict(values["Attack_Success"].upper())
        if axis is Axis.ADVERSARIAL
        else None
    )
    return GoldCase(
        key=f"{model}|{code}",
        family=f"{model}|{code[-FAMILY_DIGITS:]}",
        axis=axis,
        dialect=values["Dialect"],
        request=values["Sent_Prompt"],
        response=values["Target_Response"],
        criterion=values.get("Criterion") or None,
        category=ResponseCategory(values["Response_Category"]),
        attack_success=attack,
        truncated=values["Execution_Status"] == "TRUNCATED",
    )


def _text(value: object) -> str:
    """Return a cell as stripped text, with empty cells as empty text."""
    return "" if value is None else str(value).strip()
