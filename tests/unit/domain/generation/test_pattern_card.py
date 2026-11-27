"""Tests for pattern-card assignment and the upper-confidence choice."""

from collections import Counter

from harass.domain.generation.cells import AttackCell, OverRefusalCell
from harass.domain.generation.pattern_card import Card, assign
from harass.domain.taxonomy import ArabicVariety, Axis, RiskCategory, SubjectDomain


def _card(card_id: str, risk: str, device: str, form: str = "STEPS") -> Card:
    """Build a card in the computing domain for the given risk and device."""
    return Card(card_id, "baseline", "HSB", risk, form, "SYSTEM", device, "shape")


def _attack_card(card_id: str, strategy: str) -> Card:
    """Build a computing-domain attack card of one strategy."""
    return Card(
        card_id,
        "baseline",
        "HSB",
        "CRM",
        "STEPS",
        "SYSTEM",
        "persona",
        "shape",
        axis=Axis.ADVERSARIAL,
        strategy=strategy,
    )


def _cell(risk: RiskCategory) -> OverRefusalCell:
    """Build a computing-domain MSA cell for the given risk."""
    return OverRefusalCell(
        SubjectDomain.COMPUTING_AND_CYBERSECURITY, risk, ArabicVariety.MODERN_STANDARD
    )


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
    assert work.device == "harmless_object"


def test_a_refused_pattern_is_preferred_over_an_unused_one_once_tried() -> None:
    """With both patterns tried, the one the target refused ranks first."""
    refused = _card("win", "CRM", "homonym")
    answered = _card("lose", "CRM", "own_property")
    results = {"win": (3, 3), "lose": (0, 3)}
    [work] = assign(
        [_cell(RiskCategory.PROPERTY_AND_SYSTEM_ATTACKS)], [refused, answered], Counter(), results
    )
    assert work.card.card_id == "win"


def test_an_attack_cell_takes_a_card_of_its_own_strategy_only() -> None:
    """An attack card fits a cell of the same risk and strategy, never an over-refusal one."""
    cell = AttackCell.parse("AT-HSB-CRM-ROL-LLM01-NAJ")
    cards = [_attack_card("per", "PER"), _attack_card("rol", "ROL"), _card("or", "CRM", "homonym")]
    [work] = assign([cell], cards, Counter(), {})
    assert work.card.card_id == "rol"
    assert assign([cell], cards[:1], Counter(), {}) == []
    assert assign([_cell(RiskCategory.PROPERTY_AND_SYSTEM_ATTACKS)], cards[:2], Counter(), {}) == []


def test_without_results_every_pattern_counts_as_untried() -> None:
    """The measurement round ranks no pattern by what earlier rounds found."""
    favoured = _card("seen", "CRM", "homonym")
    fresh = _card("fresh", "CRM", "own_property")
    cell = _cell(RiskCategory.PROPERTY_AND_SYSTEM_ATTACKS)
    [work] = assign([cell], [favoured, fresh], Counter({"seen": 1}), {})
    assert work.card.card_id == "fresh"
