"""Read the generator's pattern cards from a JSON lines file.

Each line is one card: the abstract pattern of a refused prompt, never the
prompt's own text. A card whose codes fall outside the taxonomy is refused
with the line that holds it, so a malformed library never reaches the store.
"""

import json
from pathlib import Path
from typing import Any

from harass.application.errors import SeedSourceError
from harass.domain.generation.briefs import MECHANISMS
from harass.domain.generation.pattern_card import FORMS, TARGETS, Card
from harass.domain.taxonomy import RiskCategory, SubjectDomain

# A card comes from the dataset's refused prompts or from a generated round.
CARD_SOURCES = frozenset({"baseline", "generated"})
CARD_FIELDS = ("card_id", "source", "domain", "risk", "form", "target", "harmless", "shape")


def read_cards(card_file: Path) -> list[Card]:
    """Read every pattern card of the file in its stored order.

    Raises:
        SeedSourceError: If a line is not a card object, a code lies outside
            the taxonomy, or the file holds no card at all.
    """
    try:
        lines = card_file.read_text(encoding="utf-8-sig").splitlines()
    except OSError as error:
        raise SeedSourceError(f"Pattern cards cannot be read: {type(error).__name__}.") from None
    cards = [_card(line, number) for number, line in enumerate(lines, start=1) if line.strip()]
    if not cards:
        raise SeedSourceError(f"{card_file.name} holds no pattern card.")
    return cards


def _card(line: str, number: int) -> Card:
    """Read one line into a card, naming the line of any defect."""
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        raise SeedSourceError(f"Card line {number} is not valid JSON.") from None
    if not isinstance(row, dict) or any(not _text(row.get(field)) for field in CARD_FIELDS):
        raise SeedSourceError(f"Card line {number} must hold the eight card fields as text.")
    _validate(row, number)
    return Card(**{field: str(row[field]).strip() for field in CARD_FIELDS})


def _validate(row: dict[str, Any], number: int) -> None:
    """Reject a card whose codes are not the ones the generator knows."""
    allowed = {
        "source": CARD_SOURCES,
        "domain": {str(domain) for domain in SubjectDomain},
        "risk": {str(risk) for risk in RiskCategory},
        "form": set(FORMS),
        "target": set(TARGETS),
        "harmless": set(MECHANISMS),
    }
    for field, codes in allowed.items():
        if str(row[field]).strip() not in codes:
            raise SeedSourceError(f"Card line {number} has an unknown {field}.")


def _text(value: object) -> bool:
    """Return whether a field holds non-blank text."""
    return isinstance(value, str) and bool(value.strip())
