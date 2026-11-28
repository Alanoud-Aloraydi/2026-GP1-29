"""Write one attack prompt for one cell and carry it through the gates.

The attack writer drafts one prompt in Modern Standard Arabic with the
objective a complying reply would fulfil, from the cell's definitions and,
once the target has yielded to an attack of the cell's group, from that
attack's pattern card and the lessons learned; a draft that repeats a known
prompt is dropped. The shared localizer rewrites it in the cell's variety,
and the attack reviewer then judges its form.
"""

import asyncio

from harass.application.generation.contracts import Draft, DraftDrop
from harass.application.generation.localization import VarietyLocalizer
from harass.application.ports.generation import AttackReviewer, BriefWriter, WriterTruncatedError
from harass.domain.generation.attack_briefs import attack_brief, attack_from
from harass.domain.generation.cells import AttackCell
from harass.domain.generation.novelty import ROUGE_LIMIT, KnownPrompts
from harass.domain.generation.pattern_card import Card


class AttackDraftPipeline:
    """Produce one reviewed attack prompt per cell, or the reason it has none."""

    def __init__(
        self,
        writer: BriefWriter,
        localizer: VarietyLocalizer,
        reviewer: AttackReviewer,
        rouge_limit: float = ROUGE_LIMIT,
    ) -> None:
        """Bind the attack writer, the localizer, the reviewer and the limit."""
        self._writer = writer
        self._localizer = localizer
        self._reviewer = reviewer
        self._rouge_limit = rouge_limit

    async def produce(
        self, cell: AttackCell, card: Card | None, lessons: list[str], known: KnownPrompts
    ) -> Draft | DraftDrop:
        """Draft, localize and review one attack cell.

        Returns why the cell has no prompt when the writer ran out of tokens
        or its answer is unusable, the draft repeats a known prompt, or
        localization kept failing its gates. Costs one writer call, the
        localizer's own budget and one review call.
        """
        try:
            answer = await self._writer.write(attack_brief(cell, card, lessons))
        except WriterTruncatedError:
            return DraftDrop.WRITER_TRUNCATED
        attack = attack_from(answer, cell)
        if attack is None:
            return DraftDrop.UNUSABLE_ANSWER
        if await asyncio.to_thread(known.repeats, attack.prompt, self._rouge_limit):
            return DraftDrop.REPEATS_KNOWN
        localized = await self._localizer.localize(attack.prompt, cell.variety)
        if localized is None:
            return DraftDrop.LOCALIZATION_FAILED
        review = await self._reviewer.review(cell, localized)
        return Draft(attack.prompt, localized, review, attack.objective)
