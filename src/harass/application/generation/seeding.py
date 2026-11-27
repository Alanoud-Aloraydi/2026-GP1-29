"""Seed the pattern cards of an agentic run from the target's baseline run.

Both axes start from what the dataset already found on the target: an
over-refusal card is read from a harmless dataset prompt the target refused,
and an attack card from a dataset attack the target fulfilled. Each group of
risk (and strategy, for attacks) keeps a few cards, so no group crowds the
others out. The cards belong to the target model and are shared by every
later run against it.
"""

import asyncio
import hashlib
from collections import Counter
from collections.abc import Iterator, Sequence
from typing import Any

from harass.application.ports.generation import GenerationStore, PatternReader
from harass.application.ports.runs import RunAdmission
from harass.domain.case_identifier import CaseIdentifier
from harass.domain.generation.history import REFUSALS
from harass.domain.generation.pattern_card import Card
from harass.domain.taxonomy import Axis, ResponseCategory

BASELINE_SOURCE = "baseline"
# Cards kept per risk (and strategy) group, so no group crowds the others out.
SEEDS_PER_GROUP = 4
CONCURRENCY = 8

type _Group = tuple[Axis, str, str | None]


class SeedFromBaseline:
    """Read the target's baseline successes into pattern cards, once per target."""

    def __init__(
        self,
        store: GenerationStore,
        patterns: PatternReader,
        evidence: RunAdmission,
        concurrency: int = CONCURRENCY,
    ) -> None:
        """Bind the card store, the pattern reader and the baseline evidence."""
        self._store = store
        self._patterns = patterns
        self._evidence = evidence
        self._concurrency = concurrency

    async def seed(
        self, target_model: str, owner_id: str, baseline_run_id: str, axes: Sequence[Axis]
    ) -> int:
        """Store the cards read from one baseline run on ``axes`` and return how many.

        A card already stored for the target counts toward its group and is
        not read again, so seeding twice adds nothing. O(n) in the run's
        outcomes, plus one reader call per new card.
        """
        stored = await asyncio.to_thread(self._store.cards, target_model)
        origins = await asyncio.to_thread(
            self._origins,
            target_model,
            owner_id,
            baseline_run_id,
            frozenset(axes),
            {card.card_id for card in stored},
        )
        semaphore = asyncio.Semaphore(self._concurrency)

        async def read(origin: Card, text: str) -> Card | None:
            async with semaphore:
                return await self._patterns.read(origin, text)

        cards = await asyncio.gather(*(read(origin, text) for origin, text in origins))
        kept = [card for card in cards if card is not None]
        for card in kept:
            await asyncio.to_thread(self._store.add_card, card)
        return len(kept)

    def _origins(
        self, target_model: str, owner_id: str, run_id: str, axes: frozenset[Axis], known: set[str]
    ) -> list[tuple[Card, str]]:
        """Return the cards still to read, each with the prompt to read it from."""
        prefix = f"B-{hashlib.sha256(target_model.encode()).hexdigest()[:10]}-"
        taken: Counter[_Group] = Counter()
        origins: list[tuple[Card, str]] = []
        for document in _successes(self._evidence.outcome_documents(run_id, owner_id)):
            identifier = CaseIdentifier.parse(document["case_id"])
            if identifier.axis not in axes:
                continue
            strategy = str(identifier.strategy) if identifier.strategy else None
            group = (identifier.axis, str(identifier.risk_category), strategy)
            if taken[group] >= SEEDS_PER_GROUP:
                continue
            taken[group] += 1
            card_id = prefix + document["case_id"]
            if card_id in known:
                continue
            known.add(card_id)
            origin = Card(
                card_id,
                BASELINE_SOURCE,
                str(identifier.subject_domain),
                str(identifier.risk_category),
                form="",
                target="",
                device="",
                shape="",
                axis=identifier.axis,
                strategy=strategy,
                target_model=target_model,
            )
            origins.append((origin, document["original_prompt"]))
        return origins


def _successes(documents: Iterator[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield the scored outcomes where the target failed its axis.

    A failure is a refused harmless prompt or a fulfilled attack; an
    uncertain or errored attempt carries no verdict and is skipped.
    """
    for document in documents:
        if document["error"] or document["submission_uncertain"]:
            continue
        if document["axis"] == Axis.ADVERSARIAL:
            if document["attack_succeeded"] is True:
                yield document
            continue
        category = document["response_category"]
        if category and ResponseCategory(category) in REFUSALS:
            yield document
