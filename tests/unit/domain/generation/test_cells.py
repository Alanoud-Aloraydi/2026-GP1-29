"""Tests for the over-refusal cell grid and round planner."""

from collections import Counter

import pytest

from harass.domain.generation.cells import Cell, every_cell, plan_round
from harass.domain.taxonomy import ArabicVariety, RiskCategory, SubjectDomain


def _risk(cells: list[Cell]) -> Counter[str]:
    """Count the planned cells by their risk code."""
    return Counter(str(cell.risk) for cell in cells)


def test_grid_covers_every_domain_risk_variety_once() -> None:
    """The grid is 150 unique cells spanning all five domains."""
    cells = every_cell()
    assert len(cells) == 150
    assert len({cell.key for cell in cells}) == 150
    assert {str(cell.domain) for cell in cells} == {str(d) for d in SubjectDomain}


def test_cell_key_follows_the_identifier_order() -> None:
    """A cell key reads OR-<domain>-<risk>-<variety>."""
    cell = Cell(SubjectDomain.RELIGION_AND_LAW, RiskCategory.VIOLENCE_AND_HARM, ArabicVariety.NAJDI)
    assert cell.key == "OR-DIN-VIO-NAJ"


def test_measurement_round_is_balanced_across_risks() -> None:
    """A measurement round spreads evenly, five cells per risk."""
    plan = plan_round(0, 30, [], Counter())
    assert len(plan) == 30
    assert len(set(plan)) == 30
    assert set(_risk(plan).values()) == {5}


def test_discovery_round_concentrates_on_the_refused_risk() -> None:
    """A discovery round sends most cells to the over-refused risk."""
    refused = Counter({"OR-DIN-PRV-MSA": 3, "OR-TBB-PRV-NAJ": 2})
    plan = plan_round(1, 30, [], refused, exploit=True)
    assert _risk(plan)["PRV"] >= 20


def test_a_full_sweep_reaches_every_cell() -> None:
    """Five measurement rounds of 30 reach all 150 cells."""
    accepted: list[str] = []
    seen: set[str] = set()
    for index in range(5):
        for cell in plan_round(index, 30, accepted, Counter()):
            accepted.append(cell.key)
            seen.add(cell.key)
    assert len(seen) == 150


def test_a_cell_key_parses_back_into_its_cell() -> None:
    """Every key the grid produces reads back as the same cell."""
    assert all(Cell.parse(cell.key) == cell for cell in every_cell())


def test_a_key_of_another_axis_or_shape_is_refused() -> None:
    """A key that is not an over-refusal cell key raises instead of guessing."""
    for key in ("AT-DIN-VIO-MSA", "OR-DIN-VIO", "OR-XXX-VIO-MSA"):
        with pytest.raises(ValueError):
            Cell.parse(key)
