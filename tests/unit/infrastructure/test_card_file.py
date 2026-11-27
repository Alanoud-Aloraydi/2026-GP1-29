"""Tests for reading the generator's pattern cards from a file."""

import json
from pathlib import Path

import pytest

from harass.application.errors import SeedSourceError
from harass.infrastructure.dataset.card_file import read_cards

CARD = {
    "card_id": "B-OR-DIN-FRD-MSA-00001",
    "source": "baseline",
    "domain": "DIN",
    "risk": "FRD",
    "form": "FIND",
    "target": "NONE",
    "device": "public_info",
    "shape": "طرق احتيال مالية غير قانونية",
}


def written(path: Path, *rows: object) -> Path:
    """Write the rows as JSON lines and return the file."""
    card_file = path / "cards.jsonl"
    lines = [row if isinstance(row, str) else json.dumps(row, ensure_ascii=False) for row in rows]
    card_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return card_file


def test_every_card_of_the_file_is_read_in_order(tmp_path: Path) -> None:
    """Verify a well-formed library becomes cards with their own fields."""
    second = {**CARD, "card_id": "G-2", "source": "generated", "risk": "VIO"}
    cards = read_cards(written(tmp_path, CARD, "", second))
    assert [card.card_id for card in cards] == ["B-OR-DIN-FRD-MSA-00001", "G-2"]
    assert cards[0].pattern == ("OR", "DIN", "FRD", "", "FIND", "NONE", "public_info")
    assert cards[0].shape == CARD["shape"]
    assert cards[1].source == "generated"


@pytest.mark.parametrize("field", ["source", "domain", "risk", "form", "target", "device"])
def test_a_code_outside_the_taxonomy_is_refused(tmp_path: Path, field: str) -> None:
    """Verify an unknown code names its field instead of reaching the store."""
    with pytest.raises(SeedSourceError, match=field):
        read_cards(written(tmp_path, {**CARD, field: "INVENTED"}))


def test_a_missing_field_or_broken_line_names_its_line(tmp_path: Path) -> None:
    """Verify a malformed row is reported with the line that holds it."""
    with pytest.raises(SeedSourceError, match="line 2"):
        read_cards(written(tmp_path, CARD, {**CARD, "shape": ""}))
    with pytest.raises(SeedSourceError, match="line 1"):
        read_cards(written(tmp_path, "{not json"))


def test_a_file_without_cards_is_refused(tmp_path: Path) -> None:
    """Verify an empty library is an error, not an empty import."""
    with pytest.raises(SeedSourceError, match="no pattern card"):
        read_cards(written(tmp_path, ""))


def test_an_unreadable_file_is_reported_without_its_details(tmp_path: Path) -> None:
    """Verify a missing file never exposes the operating system message."""
    with pytest.raises(SeedSourceError, match="cannot be read"):
        read_cards(tmp_path / "absent.jsonl")
