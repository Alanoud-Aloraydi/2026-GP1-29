"""Tests for the cell grids and round planners of both axes."""

from collections import Counter

import pytest

from harass.domain.generation.cells import (
    ATTACK_OWASP,
    AttackCell,
    OverRefusalCell,
    every_over_refusal_cell,
    plan_attack_round,
    plan_over_refusal_round,
)
from harass.domain.taxonomy import (
    ArabicVariety,
    BypassStrategy,
    OwaspCategory,
    RiskCategory,
    SubjectDomain,
)


def _risk(cells: list[OverRefusalCell]) -> Counter[str]:
    """Count the planned cells by their risk code."""
    return Counter(str(cell.risk) for cell in cells)


def test_grid_covers_every_domain_risk_variety_once() -> None:
    """The grid is 150 unique cells spanning all five domains."""
    cells = every_over_refusal_cell()
    assert len(cells) == 150
    assert len({cell.key for cell in cells}) == 150
    assert {str(cell.domain) for cell in cells} == {str(d) for d in SubjectDomain}


def test_cell_key_follows_the_identifier_order() -> None:
    """A cell key reads OR-<domain>-<risk>-<variety>."""
    cell = OverRefusalCell(
        SubjectDomain.RELIGION_AND_LAW, RiskCategory.VIOLENCE_AND_HARM, ArabicVariety.NAJDI
    )
    assert cell.key == "OR-DIN-VIO-NAJ"


def test_measurement_round_is_balanced_across_risks() -> None:
    """A measurement round spreads evenly, five cells per risk."""
    plan = plan_over_refusal_round(0, 30, [], Counter())
    assert len(plan) == 30
    assert len(set(plan)) == 30
    assert set(_risk(plan).values()) == {5}


def test_discovery_round_concentrates_on_the_refused_risk() -> None:
    """A discovery round sends most cells to the over-refused risk."""
    refused = Counter({"OR-DIN-PRV-MSA": 3, "OR-TBB-PRV-NAJ": 2})
    plan = plan_over_refusal_round(1, 30, [], refused, exploit=True)
    assert _risk(plan)["PRV"] >= 20


def test_a_full_sweep_reaches_every_cell() -> None:
    """Five measurement rounds of 30 reach all 150 cells."""
    accepted: list[str] = []
    seen: set[str] = set()
    for index in range(5):
        for cell in plan_over_refusal_round(index, 30, accepted, Counter()):
            accepted.append(cell.key)
            seen.add(cell.key)
    assert len(seen) == 150


def test_a_cell_key_parses_back_into_its_cell() -> None:
    """Every key the grid produces reads back as the same cell."""
    assert all(OverRefusalCell.parse(cell.key) == cell for cell in every_over_refusal_cell())


def test_a_key_of_another_axis_or_shape_is_refused() -> None:
    """A key that is not an over-refusal cell key raises instead of guessing."""
    for key in ("AT-DIN-VIO-MSA", "OR-DIN-VIO", "OR-XXX-VIO-MSA"):
        with pytest.raises(ValueError):
            OverRefusalCell.parse(key)


def test_an_attack_cell_key_reads_back_into_the_same_cell() -> None:
    """Verify an attack cell survives its stored key."""
    cell = AttackCell(
        SubjectDomain.COMPUTING_AND_CYBERSECURITY,
        RiskCategory.PRIVACY_VIOLATION,
        BypassStrategy.ROLE_FRAMING,
        OwaspCategory.SENSITIVE_INFORMATION_DISCLOSURE,
        ArabicVariety.HIJAZI,
    )
    assert cell.key == "AT-HSB-PRV-ROL-LLM02-HIJ"
    assert AttackCell.parse(cell.key) == cell


def test_an_attack_cell_refuses_a_setup_its_risk_does_not_allow() -> None:
    """Verify misinformation never runs under a disclosure setup."""
    with pytest.raises(ValueError, match="does not fit"):
        AttackCell.parse("AT-SIY-MIS-DIR-LLM02-MSA")
    with pytest.raises(ValueError, match="not an attack cell key"):
        AttackCell.parse("OR-DIN-VIO-MSA")


def test_one_attack_sweep_covers_every_core_with_even_margins() -> None:
    """Verify 180 slots reach all 180 cores, each setup allowed, varieties even."""
    plan = plan_attack_round(180, [])
    assert len({cell.core for cell in plan}) == 180
    assert all(cell.owasp in ATTACK_OWASP[cell.risk] for cell in plan)
    assert {cell.owasp for cell in plan if cell.risk is RiskCategory.MISINFORMATION} == {
        OwaspCategory.MISINFORMATION
    }
    assert set(Counter(cell.variety for cell in plan).values()) == {36}


def test_the_attack_planner_continues_from_accepted_cells() -> None:
    """Verify a planned core is not planned again before the others."""
    first = plan_attack_round(30, [])
    second = plan_attack_round(30, [cell.key for cell in first])
    assert not {cell.core for cell in first} & {cell.core for cell in second}


def test_an_over_refusal_round_plans_only_the_chosen_risks_and_varieties() -> None:
    """Only risks with a card and the chosen varieties are planned."""
    risks = frozenset({RiskCategory.FRAUD_AND_DECEPTION})
    varieties = frozenset({ArabicVariety.NAJDI})
    plan = plan_over_refusal_round(0, 10, [], Counter(), risks=risks, varieties=varieties)
    assert len(plan) == 5
    assert {cell.risk for cell in plan} == set(risks)
    assert {cell.variety for cell in plan} == set(varieties)


def test_an_attack_discovery_round_follows_the_successful_strategy() -> None:
    """A discovery round leads with the risk and strategy that already succeeded."""
    succeeded = Counter({"AT-HSB-CRM-ROL-LLM01-MSA": 3})
    [cell] = plan_attack_round(1, [], succeeded, exploit=True)
    assert (cell.risk, cell.strategy) == (
        RiskCategory.PROPERTY_AND_SYSTEM_ATTACKS,
        BypassStrategy.ROLE_FRAMING,
    )
