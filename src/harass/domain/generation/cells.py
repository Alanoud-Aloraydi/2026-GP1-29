"""The cell grids of both axes and the planners that schedule a round.

An over-refusal cell is subject domain x risk category x variety (150). An
attack cell is domain x risk x bypass strategy (180 cores), with the OWASP
setup and the variety balanced at the margins. Pure rules: no model, store
or network.
"""

from collections import Counter
from dataclasses import dataclass
from itertools import product

from harass.domain.taxonomy import (
    ArabicVariety,
    Axis,
    BypassStrategy,
    OwaspCategory,
    RiskCategory,
    SubjectDomain,
)

# 49 is coprime with the 150-cell grid, so stepping by it breaks ties across
# every domain, risk and variety instead of walking one domain's cells first.
TIE_STRIDE = 49


@dataclass(frozen=True)
class OverRefusalCell:
    """One over-refusal target: a subject domain, a risk theme and a variety."""

    domain: SubjectDomain
    risk: RiskCategory
    variety: ArabicVariety

    @property
    def key(self) -> str:
        """Return the stable code that identifies this cell in the store."""
        return f"OR-{self.domain}-{self.risk}-{self.variety}"

    @classmethod
    def parse(cls, key: str) -> "OverRefusalCell":
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


def every_over_refusal_cell() -> list[OverRefusalCell]:
    """Return all 150 cells, ordered so varieties rotate across the grid."""
    return [
        OverRefusalCell(domain, risk, variety)
        for domain, risk, variety in product(SubjectDomain, RiskCategory, ArabicVariety)
    ]


def _axes(cell: OverRefusalCell) -> tuple[str, str, str]:
    """Return the cell's domain, risk and variety as distinct counter keys.

    Each code is prefixed by its axis because a bare code could collide
    across axes, and one counter of axis use is shared by all three.
    """
    return (f"D:{cell.domain}", f"R:{cell.risk}", f"V:{cell.variety}")


def plan_over_refusal_round(
    round_index: int,
    count: int,
    accepted: list[str],
    refused: Counter[str],
    exploit: bool = False,
    varieties: frozenset[ArabicVariety] = frozenset(),
    risks: frozenset[RiskCategory] = frozenset(),
) -> list[OverRefusalCell]:
    """Schedule ``count`` cells for one round.

    ``accepted`` holds the cell key of every prompt that passed review and the
    safety gate; ``refused`` counts refusals per cell. Only cells in the
    chosen ``varieties`` and ``risks`` are planned, every one when none is
    chosen; the generator passes the risks it holds a card for. In
    the measurement round (``exploit`` False) coverage leads: the
    least-covered cell first, then the least-used domain, risk and variety.
    In a discovery round (``exploit`` True) the most over-refused risk leads,
    so generation concentrates where refusals are found and coverage only
    breaks ties. O(count * c) for c cells.
    """
    cells = [
        cell
        for cell in every_over_refusal_cell()
        if (not varieties or cell.variety in varieties) and (not risks or cell.risk in risks)
    ]
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

    def ordering(cell: OverRefusalCell) -> tuple[int, ...]:
        coverage = (cell_use[cell.key], *(axis_use[axis] for axis in _axes(cell)))
        pull = (-risk_refused[str(cell.risk)], -refused[cell.key])
        leading = (*pull, *coverage) if exploit else (*coverage, *pull)
        return (*leading, tie[cell.key])

    plan: list[OverRefusalCell] = []
    for _ in range(min(count, len(cells))):
        chosen = min((cell for cell in cells if cell not in plan), key=ordering)
        plan.append(chosen)
        cell_use[chosen.key] += 1
        axis_use.update(_axes(chosen))
    return plan


# OWASP follows the test setup, not the strategy (V7 OWASP rule 1), so each
# risk allows only the setups that fit it: misinformation is LLM07 alone, and
# the disclosure setups only where leaking a record or hidden context is the
# harm itself.
ATTACK_OWASP: dict[RiskCategory, tuple[OwaspCategory, ...]] = {
    RiskCategory.VIOLENCE_AND_HARM: (OwaspCategory.NOT_APPLICABLE, OwaspCategory.PROMPT_INJECTION),
    RiskCategory.HATE_AND_DISCRIMINATION: (
        OwaspCategory.NOT_APPLICABLE,
        OwaspCategory.PROMPT_INJECTION,
    ),
    RiskCategory.PRIVACY_VIOLATION: (
        OwaspCategory.NOT_APPLICABLE,
        OwaspCategory.PROMPT_INJECTION,
        OwaspCategory.SENSITIVE_INFORMATION_DISCLOSURE,
        OwaspCategory.HIDDEN_CONTEXT_EXPOSURE,
    ),
    RiskCategory.FRAUD_AND_DECEPTION: (
        OwaspCategory.NOT_APPLICABLE,
        OwaspCategory.PROMPT_INJECTION,
        OwaspCategory.SENSITIVE_INFORMATION_DISCLOSURE,
    ),
    RiskCategory.MISINFORMATION: (OwaspCategory.MISINFORMATION,),
    RiskCategory.PROPERTY_AND_SYSTEM_ATTACKS: (
        OwaspCategory.NOT_APPLICABLE,
        OwaspCategory.PROMPT_INJECTION,
        OwaspCategory.HIDDEN_CONTEXT_EXPOSURE,
    ),
}

type AttackCore = tuple[SubjectDomain, RiskCategory, BypassStrategy]


@dataclass(frozen=True)
class AttackCell:
    """One planned attack: its taxonomy codes and the variety to write it in."""

    domain: SubjectDomain
    risk: RiskCategory
    strategy: BypassStrategy
    owasp: OwaspCategory
    variety: ArabicVariety

    def __post_init__(self) -> None:
        """Reject an OWASP setup that the risk does not allow."""
        if self.owasp not in ATTACK_OWASP[self.risk]:
            raise ValueError(f"OWASP {self.owasp} does not fit risk {self.risk}.")

    @property
    def key(self) -> str:
        """Return the stable code that identifies this cell in the store."""
        return (
            f"{Axis.ADVERSARIAL}-{self.domain}-{self.risk}-{self.strategy}-"
            f"{self.owasp}-{self.variety}"
        )

    @property
    def core(self) -> AttackCore:
        """Return the domain, risk and strategy the planner balances first."""
        return (self.domain, self.risk, self.strategy)

    @classmethod
    def parse(cls, key: str) -> "AttackCell":
        """Return the cell one stored key names.

        Raises:
            ValueError: If the key is not an attack cell key of five taxonomy
                codes, or names an OWASP setup its risk does not allow.
        """
        segments = key.split("-")
        if len(segments) != 6 or segments[0] != Axis.ADVERSARIAL:
            raise ValueError(f"'{key}' is not an attack cell key.")
        _, domain, risk, strategy, owasp, variety = segments
        return cls(
            SubjectDomain(domain),
            RiskCategory(risk),
            BypassStrategy(strategy),
            OwaspCategory(owasp),
            ArabicVariety(variety),
        )


def plan_attack_round(
    count: int,
    accepted: list[str],
    succeeded: Counter[str] | None = None,
    exploit: bool = False,
    varieties: frozenset[ArabicVariety] = frozenset(),
) -> list[AttackCell]:
    """Schedule ``count`` attack cells, least-covered first, margins even.

    ``accepted`` holds the cell key of every attack that passed review and
    the safety gate; ``succeeded`` counts successful attacks per cell. Each
    slot takes the least-used core, then the core whose domain, risk and
    strategy are least used; then the least-used OWASP setup its risk allows
    and the least-used of the chosen ``varieties`` (every variety when none
    is chosen). In a discovery round (``exploit`` True) the risk and strategy
    with the most successes lead, and coverage only breaks ties.
    O(count * c) for c cores.
    """
    cores: list[AttackCore] = list(product(SubjectDomain, RiskCategory, BypassStrategy))
    allowed = [variety for variety in ArabicVariety if not varieties or variety in varieties]
    history = [AttackCell.parse(key) for key in accepted if key.startswith(Axis.ADVERSARIAL)]
    core_use = Counter(cell.core for cell in history)
    margin: Counter[str] = Counter()
    for cell in history:
        margin.update((*cell.core, cell.variety))
    owasp_use = Counter((cell.risk, cell.owasp) for cell in history)
    # Successes are sparse per cell, so a core inherits its risk's and its
    # strategy's pull, as an over-refusal cell inherits its risk's.
    pull: Counter[str] = Counter()
    for key, successes in (succeeded or Counter()).items():
        if key.startswith(Axis.ADVERSARIAL):
            cell = AttackCell.parse(key)
            pull.update({str(cell.risk): successes, str(cell.strategy): successes})
    order = {core: index for index, core in enumerate(cores)}

    def ordering(core: AttackCore) -> tuple[int, ...]:
        coverage = (core_use[core], sum(margin[code] for code in core))
        lead = -(pull[str(core[1])] + pull[str(core[2])])
        ranked = (lead, *coverage) if exploit else (*coverage, lead)
        return (*ranked, order[core])

    plan: list[AttackCell] = []
    for _ in range(count):
        core = min(cores, key=ordering)
        domain, risk, strategy = core
        owasp = min(ATTACK_OWASP[risk], key=lambda setup: owasp_use[(risk, setup)])
        variety = min(allowed, key=lambda v: margin[v])
        plan.append(AttackCell(domain, risk, strategy, owasp, variety))
        core_use[core] += 1
        margin.update((domain, risk, strategy, variety))
        owasp_use[(risk, owasp)] += 1
    return plan
