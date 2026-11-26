"""Tests for pattern-card assignment and the upper-confidence choice."""

from collections import Counter

from harass.domain.generation.cells import Cell
from harass.domain.generation.pattern_card import Card, assign
from harass.domain.taxonomy import ArabicVariety, RiskCategory, SubjectDomain


def _card(card_id: str, risk: str, harmless: str, form: str = "STEPS") -> Card:
    """Build a card in the computing domain for the given risk and device."""
    return Card(card_id, "baseline", "HSB", risk, form, "SYSTEM", harmless, "shape")


def _cell(risk: RiskCategory) -> Cell:
    """Build a computing-domain MSA cell for the given risk."""
    return Cell(SubjectDomain.COMPUTING_AND_CYBERSECURITY, risk, ArabicVariety.MODERN_STANDARD)


def test_a_cell_with_no_card_for_its_risk_is_skipped() -> None:
    """Assign returns no work for a cell whose risk has no card."""
    cards = [_card("c1", "CRM", "harmless_object")]
    plan = assign([_cell(RiskCategory.VIOLENCE_AND_HARM)], cards, Counter(), {})
    assert plan == []


def test_each_assignment_uses_a_card_of_the_cell_risk() -> None:
    """A planned card matches its cell's risk."""
    cards = [_card("c1", "CRM", "harmless_object"), _card("c2", "VIO", "homonym")]
    [work] = assign([_cell(RiskCategory.PROPERTY_AND_SYSTEM_ATTACKS)], cards, Counter(), {})
    assert work.card.card_id == "c1"
    assert work.mechanism == "harmless_object"


def test_a_refused_pattern_is_preferred_over_an_unused_one_once_tried() -> None:
    """With both patterns tried, the one the target refused ranks first."""
    refused = _card("win", "CRM", "homonym")
    answered = _card("lose", "CRM", "own_property")
    results = {"win": (3, 3), "lose": (0, 3)}
    [work] = assign(
        [_cell(RiskCategory.PROPERTY_AND_SYSTEM_ATTACKS)], [refused, answered], Counter(), results
    )
    assert work.card.card_id == "win"
