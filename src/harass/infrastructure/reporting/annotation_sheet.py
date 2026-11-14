"""Write blind annotation sheets for independent human raters."""

import csv
from pathlib import Path

from harass.domain.judge_benchmark import GoldCase

COLUMNS = (
    "key",
    "axis",
    "dialect",
    "request",
    "response",
    "criterion",
    "rater_category",
    "rater_attack_success",
    "rater_request_safe",
)


def write_annotation_sheet(cases: list[GoldCase], destination: Path) -> None:
    """Write cases without gold labels, leaving the rater columns blank.

    The sheet is UTF-8 with a byte-order mark so spreadsheet software reads
    the Arabic text correctly.
    """
    with destination.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(COLUMNS)
        for case in sorted(cases, key=lambda c: (c.family, c.dialect)):
            writer.writerow(
                [
                    case.key,
                    case.axis.value,
                    case.dialect,
                    case.request,
                    case.response,
                    case.criterion or "",
                    "",
                    "",
                    "",
                ]
            )
