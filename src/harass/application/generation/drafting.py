"""Write one prompt for one cell and carry it through the writing gates.

The writer drafts several candidates in Modern Standard Arabic; a draft that
repeats a known prompt is dropped and the reviewer keeps the best of the rest.
The localizer then rewrites the winner in the cell's variety, where cheap
rules reject foreign markers, formal leakage and a stuffed dialect before one
model call checks that the alarming expression survived the rewrite.
"""

import asyncio
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from harass.application.ports.generation import BriefWriter, FormReviewer
from harass.domain.generation.briefs import (
    echoes_instructions,
    localize_brief,
    question_count,
    request_from,
    write_brief,
)
from harass.domain.generation.dialect import foreign_markers, formal_leakage
from harass.domain.generation.pattern_card import Assignment
from harass.domain.generation.review import CONTENT_CHECKS, Review
from harass.domain.owasp_scenario import rouge_l
from harass.domain.taxonomy import ArabicVariety

# A draft this close to a known prompt is a rewrite of it, not a new prompt.
ROUGE_LIMIT = 0.5
CANDIDATES = 4
LOCALIZE_ATTEMPTS = 3
# The localizer sometimes opens with a lone diacritic on its own line.
STRAY_MARKS = "".join(map(chr, range(0x064B, 0x0653))) + " :\n"
TOKENS = re.compile(r"\w+")


@dataclass(frozen=True)
class Draft:
    """One prompt that survived the writing gates, with its review."""

    written_text: str
    sent_text: str
    review: Review


@dataclass(frozen=True)
class KnownPrompts:
    """The texts a new draft must not repeat, tokenized once per round.

    ROUGE-L F1 is ``2 * LCS / (n + m)`` and the longest common subsequence
    cannot exceed the tokens the two texts share, so a reference sharing
    fewer than ``limit * (n + m) / 2`` tokens cannot reach the limit and needs
    no quadratic comparison. Building the counts once turns the novelty gate
    from O(r * n * m) per draft into O(r * n) for all but a few references.
    """

    counted: tuple[tuple[str, Counter[str]], ...]

    @classmethod
    def of(cls, texts: Iterable[str]) -> "KnownPrompts":
        """Count the tokens of every distinct known text."""
        return cls(tuple((text, Counter(TOKENS.findall(text.casefold()))) for text in set(texts)))

    def repeats(self, candidate: str, limit: float) -> bool:
        """Return whether the candidate repeats a known prompt too closely."""
        counts = Counter(TOKENS.findall(candidate.casefold()))
        length = sum(counts.values())
        for text, other in self.counted:
            shared = sum((counts & other).values())
            if shared < limit * (length + sum(other.values())) / 2:
                continue
            if rouge_l(text, candidate) >= limit:
                return True
        return False


class DraftPipeline:
    """Produce one reviewed prompt per assignment, or nothing for it."""

    def __init__(
        self,
        writer: BriefWriter,
        localizer: BriefWriter,
        reviewer: FormReviewer,
        candidates: int = CANDIDATES,
        rouge_limit: float = ROUGE_LIMIT,
    ) -> None:
        """Bind the writing models, the reviewer and the drafting budget."""
        self._writer = writer
        self._localizer = localizer
        self._reviewer = reviewer
        self._candidates = candidates
        self._rouge_limit = rouge_limit

    async def produce(
        self, assignment: Assignment, lessons: list[str], known: KnownPrompts
    ) -> Draft | None:
        """Draft, localize and review one assignment.

        Returns None when no candidate survived the novelty gate, or when
        localization kept failing its gates. Costs at most ``candidates``
        writer calls plus one localizer call per localization attempt.
        """
        written = await self._best_candidate(assignment, lessons, known)
        if written is None:
            return None
        sent = await self._localize(written, assignment.cell.variety)
        if sent is None:
            return None
        review = await self._reviewer.review(assignment.cell, assignment.mechanism, sent)
        return Draft(written, sent, review)

    async def _best_candidate(
        self, assignment: Assignment, lessons: list[str], known: KnownPrompts
    ) -> str | None:
        """Draft candidates and keep the one the reviewer rates highest.

        Variety can only be judged after localization, so candidates are
        scored on the content checks; a clean sweep stops the search early.
        """
        brief = write_brief(assignment.cell, assignment.card, lessons)
        best: str | None = None
        best_score = -1
        for _ in range(self._candidates):
            candidate = request_from(await self._writer.write(brief))
            if not candidate:
                continue
            if await asyncio.to_thread(known.repeats, candidate, self._rouge_limit):
                continue
            review = await self._reviewer.review(assignment.cell, assignment.mechanism, candidate)
            score = review.score(CONTENT_CHECKS)
            if score > best_score:
                best, best_score = candidate, score
            if score == len(CONTENT_CHECKS):
                break
        return best

    async def _localize(self, written: str, variety: ArabicVariety) -> str | None:
        """Rewrite a draft into its variety, keeping the alarming word intact.

        A rewrite is rejected for markers of another variety, formal leakage,
        an echo of the localizer's own brief or an added question, and finally
        for losing the alarming expression; that last check costs a model
        call, so it runs only once the rule gates pass.
        """
        if variety is ArabicVariety.MODERN_STANDARD:
            return written
        brief = localize_brief(written, variety)
        for _ in range(LOCALIZE_ATTEMPTS):
            rewrite = (await self._localizer.write(brief)).lstrip(STRAY_MARKS).strip()
            if not rewrite or foreign_markers(rewrite, str(variety)) or formal_leakage(rewrite):
                continue
            if echoes_instructions(rewrite) or question_count(rewrite) > question_count(written):
                continue
            if await self._reviewer.preserves_alarm(written, rewrite):
                return rewrite
        return None
