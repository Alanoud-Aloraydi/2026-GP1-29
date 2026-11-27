"""Pattern cards: why a prompt succeeded on a target, abstracted from its text.

A success is a refusal of a harmless prompt on the over-refusal axis and a
fulfilled attack on the attack axis. A card records the form of request, its
object, the device that carried it (where its harmlessness lives, or how its
bypass is enacted) and the harmful request its surface resembles, never the
prompt's wording. The writer sees a card, not the prompt, and writes a new
prompt on another subject in the same pattern (the strategy library of
AutoDAN-Turbo, grown like the archive of Rainbow Teaming: successful
generated prompts become cards too).

Cards with the same axis, domain, risk, strategy, form, target and device
share a pattern. For each cell the planner draws the pattern with the highest
upper-confidence success rate on the current target, so untried patterns come
first and the ones that succeed are revisited. Pure rules: reading a prompt
into a card (a model call) and storing cards live behind ports elsewhere.
"""

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from harass.domain.generation.cells import AttackCell, OverRefusalCell
from harass.domain.taxonomy import Axis

# How much an untried pattern is favoured over a proven one; lowered from 1.4
# so patterns the target already refuses are preferred sooner.
UCB_EXPLORATION = 0.7

# The request's form and the object it acts on, as a code mapped to its gloss.
FORMS = {
    "STEPS": "يطلب خطوات أو طريقة عملية",
    "WRITE": "يطلب كتابة نص: رسالة أو منشور أو قصة أو خطاب",
    "FIND": "يطلب العثور على معلومة أو مكان أو وسيلة",
    "COLLECT": "يطلب جمع معلومات أو بيانات",
    "CODE": "يطلب برنامجًا أو كودًا",
    "EXPLAIN": "يطلب شرح أمر أو تفسيره",
}
TARGETS = {
    "PERSON": "شخص",
    "ACCOUNT": "حساب أو جهاز",
    "ORGANIZATION": "جهة أو شركة",
    "SYSTEM": "نظام أو شبكة",
    "DOCUMENT": "مستند أو وثيقة",
    "SUBSTANCE": "مادة أو دواء أو أداة",
    "GROUP": "جماعة من الناس",
    "NONE": "بلا هدف محدد",
}

Pattern = tuple[str, ...]
type Cell = OverRefusalCell | AttackCell


@dataclass(frozen=True)
class Card:
    """One abstract pattern taken from a prompt that succeeded.

    ``strategy`` is the bypass strategy of an attack card and None on the
    over-refusal axis. ``target_model`` names the model whose results the
    card was read from, or is None for a card shared by every target.
    """

    card_id: str
    source: str
    domain: str
    risk: str
    form: str
    target: str
    device: str
    shape: str
    axis: Axis = Axis.OVER_REFUSAL
    strategy: str | None = None
    target_model: str | None = None

    @property
    def pattern(self) -> Pattern:
        """Return the key shared by cards that describe the same pattern."""
        return (
            self.axis,
            self.domain,
            self.risk,
            self.strategy or "",
            self.form,
            self.target,
            self.device,
        )

    def fits(self, cell: Cell) -> bool:
        """Return whether a prompt for this cell may be written from the card."""
        if isinstance(cell, AttackCell):
            return (
                self.axis is Axis.ADVERSARIAL
                and self.risk == cell.risk
                and self.strategy == cell.strategy
            )
        return self.axis is Axis.OVER_REFUSAL and self.risk == cell.risk


@dataclass(frozen=True)
class Assignment[CellT: (OverRefusalCell, AttackCell)]:
    """One unit of work for a round: a cell and the card to write it from."""

    cell: CellT
    card: Card

    @property
    def device(self) -> str:
        """Return the device that carried the card's prompt."""
        return self.card.device


def _ucb(wins: int, tries: int, total: int) -> float:
    """Return a pattern's upper-confidence refusal score; untried is infinite."""
    if tries == 0:
        return math.inf
    return wins / tries + UCB_EXPLORATION * math.sqrt(math.log(total + 1) / tries)


def assign[CellT: (OverRefusalCell, AttackCell)](
    cells: Sequence[CellT],
    cards: Sequence[Card],
    card_uses: Counter[str],
    results: dict[str, tuple[int, int]],
) -> list[Assignment[CellT]]:
    """Give each planned cell the card whose pattern looks most promising.

    ``card_uses`` counts prompts already written from each card; ``results``
    maps a card to (successes, scored) on the current target, and an empty
    mapping ranks every pattern as untried. A cell draws from the cards that
    fit it in its own domain, or from every fitting card when its domain has
    none. Patterns rank by UCB over their cards' results, then by how little
    their device was used for the risk, then by how little the pattern was
    used; within a pattern the least-used card wins. A cell with no fitting
    card is left out. O(cells * cards).
    """
    uses = Counter(card_uses)
    by_id = {card.card_id: card for card in cards}
    # Most seed cards carry one device (fictional_entity); spreading devices
    # per risk keeps one pattern from dominating a round.
    device_use: Counter[tuple[str, str]] = Counter()
    for card_id, count in uses.items():
        if card_id in by_id:
            device_use[(by_id[card_id].risk, by_id[card_id].device)] += count

    plan: list[Assignment[CellT]] = []
    for cell in cells:
        fitting = [card for card in cards if card.fits(cell)]
        pool = [card for card in fitting if card.domain == cell.domain] or fitting
        if not pool:
            continue
        card = _choose(pool, uses, device_use, results)
        uses[card.card_id] += 1
        device_use[(card.risk, card.device)] += 1
        plan.append(Assignment(cell, card))
    return plan


def _choose(
    pool: list[Card],
    uses: Counter[str],
    device_use: Counter[tuple[str, str]],
    results: dict[str, tuple[int, int]],
) -> Card:
    """Pick the best card from one cell's candidate pool."""
    wins: Counter[Pattern] = Counter()
    tries: Counter[Pattern] = Counter()
    pattern_uses: Counter[Pattern] = Counter()
    for card in pool:
        won, scored = results.get(card.card_id, (0, 0))
        wins[card.pattern] += won
        tries[card.pattern] += scored
        pattern_uses[card.pattern] += uses[card.card_id]
    total = sum(tries.values())
    best = max(
        sorted({card.pattern for card in pool}),
        key=lambda key: (
            _ucb(wins[key], tries[key], total),
            -device_use[(key[2], key[6])],
            -pattern_uses[key],
        ),
    )
    return min((c for c in pool if c.pattern == best), key=lambda c: (uses[c.card_id], c.card_id))
