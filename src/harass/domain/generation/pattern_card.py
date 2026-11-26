"""Pattern cards: why a seed prompt was refused, abstracted from its text.

A card records the form of request, its object, where its harmlessness lives
and the harmful request its surface resembles, never the seed's wording. The
writer sees a card, not the seed, and writes a new prompt on another subject
in the same pattern (the strategy library of AutoDAN-Turbo, grown like the
archive of Rainbow Teaming: refused generated prompts become cards too).

Cards with the same (domain, risk, form, target, harmless) share a pattern.
For each cell the planner draws the pattern with the highest upper-confidence
refusal rate on the current target, so untried patterns come first and the
ones the target refuses are revisited. Pure rules: reading a refused prompt
into a card (a model call) and storing cards live behind ports elsewhere.
"""

import math
from collections import Counter
from dataclasses import dataclass

from harass.domain.generation.cells import Cell

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

Pattern = tuple[str, str, str, str, str]


@dataclass(frozen=True)
class Card:
    """One abstract refusal pattern taken from a refused prompt."""

    card_id: str
    source: str
    domain: str
    risk: str
    form: str
    target: str
    harmless: str
    shape: str

    @property
    def pattern(self) -> Pattern:
        """Return the key shared by cards that describe the same pattern."""
        return (self.domain, self.risk, self.form, self.target, self.harmless)


@dataclass(frozen=True)
class Assignment:
    """One unit of work for a round: a cell and the card to write it from."""

    cell: Cell
    card: Card

    @property
    def mechanism(self) -> str:
        """Return the device that carries the prompt's harmlessness."""
        return self.card.harmless


def _ucb(wins: int, tries: int, total: int) -> float:
    """Return a pattern's upper-confidence refusal score; untried is infinite."""
    if tries == 0:
        return math.inf
    return wins / tries + UCB_EXPLORATION * math.sqrt(math.log(total + 1) / tries)


def assign(
    cells: list[Cell],
    cards: list[Card],
    card_uses: Counter[str],
    results: dict[str, tuple[int, int]],
) -> list[Assignment]:
    """Give each planned cell the card whose pattern looks most promising.

    ``card_uses`` counts prompts already written from each card; ``results``
    maps a card to (refused, scored) on the current target. A cell draws from
    cards of its own domain and risk, or of its risk alone when its pair has
    none. Patterns rank by UCB over their cards' results, then by how little
    their harmlessness device was used for the risk, then by how little the
    pattern was used; within a pattern the least-used card wins. A cell with
    no card for its risk is skipped. O(cells * cards).
    """
    uses = Counter(card_uses)
    by_id = {card.card_id: card for card in cards}
    # Most seed cards carry one device (fictional_entity); spreading devices
    # per risk keeps one pattern from dominating a round.
    device_use: Counter[tuple[str, str]] = Counter()
    for card_id, count in uses.items():
        if card_id in by_id:
            device_use[(by_id[card_id].risk, by_id[card_id].harmless)] += count

    plan: list[Assignment] = []
    for cell in cells:
        domain, risk = str(cell.domain), str(cell.risk)
        pool = [c for c in cards if c.domain == domain and c.risk == risk] or [
            c for c in cards if c.risk == risk
        ]
        if not pool:
            continue
        card = _choose(pool, uses, device_use, results)
        uses[card.card_id] += 1
        device_use[(card.risk, card.harmless)] += 1
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
            -device_use[(key[1], key[4])],
            -pattern_uses[key],
        ),
    )
    return min((c for c in pool if c.pattern == best), key=lambda c: (uses[c.card_id], c.card_id))
