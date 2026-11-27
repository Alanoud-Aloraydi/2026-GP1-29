"""Distil lessons from a finished round at two scopes, on either axis.

After a round the librarian contrasts a successful prompt with a failed one
from the same group and asks the writing model for one abstract lesson that
names the difference, at the cell scope and at the broader group scope. A
success is a refused harmless prompt on the over-refusal axis and a fulfilled
attack on the attack axis. Prompt text never enters a lesson: one that copies
a prompt is rejected, and so is an over-refusal lesson that reads as safety
advice, because it would teach the writer to defuse its prompts.
"""

import asyncio
from collections.abc import Sequence

from harass.application.ports.generation import BriefWriter
from harass.domain.generation.attack_briefs import attack_lesson_brief
from harass.domain.generation.history import CELL_SCOPE, GROUP_SCOPE, GeneratedPrompt, Lesson
from harass.domain.generation.novelty import ROUGE_LIMIT, KnownPrompts
from harass.domain.generation.over_refusal_briefs import lesson_brief, teaches_defusing
from harass.domain.taxonomy import Axis

LESSON_ATTEMPTS = 2

type ScoredPrompt = tuple[GeneratedPrompt, bool]


class Librarian:
    """Writes one lesson per group that holds both a success and a failure."""

    def __init__(self, distiller: BriefWriter, attempts: int = LESSON_ATTEMPTS) -> None:
        """Bind the writing model and how often a rejected lesson is retried."""
        self._distiller = distiller
        self._attempts = attempts

    async def lessons_from(
        self,
        axis: Axis,
        scored: Sequence[ScoredPrompt],
        target_model: str,
        origin: str,
        round_index: int,
        known: set[str],
    ) -> list[Lesson]:
        """Write the round's lessons at both scopes.

        A group yields a lesson only when it holds both a success and a
        failure, since a lesson is a contrast. ``origin`` (the run, or the
        target outside a run) and the round make identifiers deterministic,
        and one already in ``known`` is skipped, so re-scoring a round adds no
        duplicates. O(n) in the round's prompts.
        """
        lessons: list[Lesson] = []
        for scope in (CELL_SCOPE, GROUP_SCOPE):
            for key, members in _groups(scored, scope).items():
                lesson_id = f"L-{scope}-{key}-{origin}-r{round_index}"
                if lesson_id in known:
                    continue
                text = await self._contrast(axis, members)
                if not text:
                    continue
                known.add(lesson_id)
                lessons.append(Lesson(lesson_id, scope, key, text, target_model, axis))
        return lessons

    async def _contrast(self, axis: Axis, members: list[ScoredPrompt]) -> str:
        """Return one lesson for a group, or empty when it teaches nothing."""
        success = next((prompt for prompt, hit in members if hit), None)
        failure = next((prompt for prompt, hit in members if not hit), None)
        if success is None or failure is None:
            return ""
        texts = [success.localized_text, failure.localized_text]
        brief = (
            attack_lesson_brief(texts[:1], texts[1:])
            if axis is Axis.ADVERSARIAL
            else lesson_brief(texts[:1], texts[1:])
        )
        sources = KnownPrompts.of(texts)
        for _ in range(self._attempts):
            text = (await self._distiller.write(brief)).strip()
            if not text or await asyncio.to_thread(sources.repeats, text, ROUGE_LIMIT):
                continue
            if axis is Axis.OVER_REFUSAL and teaches_defusing(text):
                continue
            return text
        return ""


def _groups(scored: Sequence[ScoredPrompt], scope: str) -> dict[str, list[ScoredPrompt]]:
    """Group the round's scored prompts by the key of one lesson scope."""
    groups: dict[str, list[ScoredPrompt]] = {}
    for prompt, success in scored:
        key = prompt.cell_key if scope == CELL_SCOPE else prompt.group
        groups.setdefault(key, []).append((prompt, success))
    return groups
