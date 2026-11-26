"""The over-refusal cell grid and the planner that schedules a round.

A cell is subject domain x risk category x linguistic variety (150 in all).
The planner balances covering the grid evenly against revisiting the cells
where a target over-refuses. Pure rules: no model, store or network.
"""

from collections import Counter
from dataclasses import dataclass
from itertools import product

from harass.domain.taxonomy import ArabicVariety, Axis, RiskCategory, SubjectDomain

# 49 is coprime with the 150-cell grid, so stepping by it breaks ties across
# every domain, risk and variety instead of walking one domain's cells first.
TIE_STRIDE = 49


@dataclass(frozen=True)
class Cell:
    """One over-refusal target: a subject domain, a risk theme and a variety."""

    domain: SubjectDomain
    risk: RiskCategory
    variety: ArabicVariety

    @property
    def key(self) -> str:
        """Return the stable code that identifies this cell in the store."""
        return f"OR-{self.domain}-{self.risk}-{self.variety}"

    @classmethod
    def parse(cls, key: str) -> "Cell":
        """Return the cell one stored key names.

        Raises:
            ValueError: If the key is not an over-refusal cell key of three
                taxonomy codes.
        """
        segments = key.split("-")
        if len(segments) != 4 or segments[0] != Axis.OVER_REFUSAL:
            raise ValueError(f"'{key}' is not an over-refusal cell key.")
        _, domain, risk, variety = segments
        return cls(SubjectDomain(domain), RiskCategory(risk), ArabicVariety(variety))


def every_cell() -> list[Cell]:
    """Return all 150 cells, ordered so varieties rotate across the grid."""
    return [
        Cell(domain, risk, variety)
        for domain, risk, variety in product(SubjectDomain, RiskCategory, ArabicVariety)
    ]


def _axes(cell: Cell) -> tuple[str, str, str]:
    """Return the cell's domain, risk and variety as distinct counter keys.

    Each code is prefixed by its axis because a bare code could collide
    across axes, and one counter of axis use is shared by all three.
    """
    return (f"D:{cell.domain}", f"R:{cell.risk}", f"V:{cell.variety}")


def plan_round(
    round_index: int, count: int, accepted: list[str], refused: Counter[str], exploit: bool = False
) -> list[Cell]:
    """Schedule ``count`` cells for one round.

    ``accepted`` holds the cell key of every prompt that passed review and the
    safety gate; ``refused`` counts refusals per cell. In the measurement
    round (``exploit`` False) coverage leads: the least-covered cell first,
    then the least-used domain, risk and variety. In a discovery round
    (``exploit`` True) the most over-refused risk leads, so generation
    concentrates where refusals are found and coverage only breaks ties.
    O(count * c) for c cells.
    """
    cells = every_cell()
    by_key = {cell.key: cell for cell in cells}
    history = [by_key[key] for key in accepted if key in by_key]
    cell_use = Counter(cell.key for cell in history)
    axis_use = Counter(axis for cell in history for axis in _axes(cell))
    # Per-cell refusals are sparse, so a cell inherits its whole risk's pull:
    # a risk that over-refuses draws more generation to all of its cells.
    risk_refused: Counter[str] = Counter()
    for cell in cells:
        risk_refused[str(cell.risk)] += refused[cell.key]
    tie = {
        cell.key: (index * TIE_STRIDE + round_index) % len(cells)
        for index, cell in enumerate(cells)
    }

    def ordering(cell: Cell) -> tuple[int, ...]:
        coverage = (cell_use[cell.key], *(axis_use[axis] for axis in _axes(cell)))
        pull = (-risk_refused[str(cell.risk)], -refused[cell.key])
        leading = (*pull, *coverage) if exploit else (*coverage, *pull)
        return (*leading, tie[cell.key])

    plan: list[Cell] = []
    for _ in range(min(count, len(cells))):
        chosen = min((cell for cell in cells if cell not in plan), key=ordering)
        plan.append(chosen)
        cell_use[chosen.key] += 1
        axis_use.update(_axes(chosen))
    return plan
