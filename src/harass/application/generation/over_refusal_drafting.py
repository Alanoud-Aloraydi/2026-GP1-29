"""Write one over-refusal prompt for one cell and carry it through the gates.

The writer drafts several candidates in Modern Standard Arabic; a draft that
repeats a known prompt is dropped and the reviewer keeps the best of the rest.
The shared localizer then rewrites the winner in the cell's variety, and one
model call checks that the alarming expression survived the rewrite.
"""

import asyncio

from harass.application.generation.contracts import Draft
from harass.application.generation.localization import VarietyLocalizer
from harass.application.ports.generation import BriefWriter, OverRefusalReviewer
from harass.domain.generation.cells import OverRefusalCell
from harass.domain.generation.novelty import ROUGE_LIMIT, KnownPrompts
from harass.domain.generation.over_refusal_briefs import over_refusal_brief, request_from
from harass.domain.generation.pattern_card import Assignment
from harass.domain.generation.review import OVER_REFUSAL_CONTENT_CHECKS

CANDIDATES = 4


class OverRefusalDraftPipeline:
    """Produce one reviewed over-refusal prompt per assignment, or nothing."""

    def __init__(
        self,
        writer: BriefWriter,
        localizer: VarietyLocalizer,
        reviewer: OverRefusalReviewer,
        candidates: int = CANDIDATES,
        rouge_limit: float = ROUGE_LIMIT,
    ) -> None:
        """Bind the writing model, the localizer, the reviewer and the budget."""
        self._writer = writer
        self._localizer = localizer
        self._reviewer = reviewer
        self._candidates = candidates
        self._rouge_limit = rouge_limit

    async def produce(
        self, assignment: Assignment[OverRefusalCell], lessons: list[str], known: KnownPrompts
    ) -> Draft | None:
        """Draft, localize and review one assignment.

        Returns None when no candidate survived the novelty gate, or when
        localization kept failing its gates. Costs at most ``candidates``
        writer calls plus the localizer's own budget.
        """
        written = await self._best_candidate(assignment, lessons, known)
        if written is None:
            return None
        localized = await self._localizer.localize(
            written, assignment.cell.variety, self._reviewer.preserves_alarm
        )
        if localized is None:
            return None
        review = await self._reviewer.review(assignment.cell, assignment.device, localized)
        return Draft(written, localized, review)

    async def _best_candidate(
        self, assignment: Assignment[OverRefusalCell], lessons: list[str], known: KnownPrompts
    ) -> str | None:
        """Draft candidates and keep the one the reviewer rates highest.

        Variety can only be judged after localization, so candidates are
        scored on the content checks; a clean sweep stops the search early.
        """
        brief = over_refusal_brief(assignment.cell, assignment.card, lessons)
        best: str | None = None
        best_score = -1
        for _ in range(self._candidates):
            candidate = request_from(await self._writer.write(brief))
            if not candidate:
                continue
            if await asyncio.to_thread(known.repeats, candidate, self._rouge_limit):
                continue
            review = await self._reviewer.review(assignment.cell, assignment.device, candidate)
            score = review.score(OVER_REFUSAL_CONTENT_CHECKS)
            if score > best_score:
                best, best_score = candidate, score
            if score == len(OVER_REFUSAL_CONTENT_CHECKS):
                break
        return best
