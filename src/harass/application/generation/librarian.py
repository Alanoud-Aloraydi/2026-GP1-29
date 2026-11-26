"""Distil lessons from a finished round at two scopes.

After a round the librarian contrasts a refused prompt with an answered one
from the same group and asks the writing model for one abstract lesson that
names the difference, at the cell scope and at the broader risk-and-mechanism
scope. Prompt text never enters a lesson, and a lesson that reads as safety
advice is rejected, because it would teach the writer to defuse its prompts.
"""

from collections.abc import Sequence

from harass.application.ports.generation import BriefWriter
from harass.domain.generation.briefs import lesson_brief, teaches_defusing
from harass.domain.generation.cells import Cell
from harass.domain.generation.history import CELL_SCOPE, GROUP_SCOPE, GeneratedPrompt, Lesson

LESSON_ATTEMPTS = 2

type ScoredPrompt = tuple[GeneratedPrompt, bool]


class Librarian:
    """Writes one lesson per group that holds both a refusal and an answer."""

    def __init__(self, distiller: BriefWriter, attempts: int = LESSON_ATTEMPTS) -> None:
        """Bind the writing model and how often a defusing lesson is retried."""
        self._distiller = distiller
        self._attempts = attempts

    async def lessons_from(
        self, scored: Sequence[ScoredPrompt], target_model: str, round_index: int, known: set[str]
    ) -> list[Lesson]:
        """Write the round's lessons at both scopes.

        A group yields a lesson only when it holds both a refused and an
        answered prompt, since a lesson is a contrast. Identifiers are
        deterministic in the round and the group, and one already in
        ``known`` is skipped, so re-scoring a round adds no duplicates.
        O(n) in the round's prompts.
        """
        lessons: list[Lesson] = []
        for scope in (CELL_SCOPE, GROUP_SCOPE):
            for key, members in _groups(scored, scope).items():
                lesson_id = f"L-{scope}-{key}-{target_model}-r{round_index}"
                if lesson_id in known:
                    continue
                text = await self._contrast(members)
                if not text:
                    continue
                known.add(lesson_id)
                lessons.append(
                    Lesson(
                        lesson_id=lesson_id,
                        scope=scope,
                        scope_key=key,
                        text=text,
                        target_model=target_model,
                    )
                )
        return lessons

    async def _contrast(self, members: list[ScoredPrompt]) -> str:
        """Return one lesson for a group, or empty when it teaches nothing."""
        refused = next((prompt for prompt, hit in members if hit), None)
        answered = next((prompt for prompt, hit in members if not hit), None)
        if refused is None or answered is None:
            return ""
        brief = lesson_brief([refused.sent_text], [answered.sent_text])
        for _ in range(self._attempts):
            text = (await self._distiller.write(brief)).strip()
            if text and not teaches_defusing(text):
                return text
        return ""


def _groups(scored: Sequence[ScoredPrompt], scope: str) -> dict[str, list[ScoredPrompt]]:
    """Group the round's scored prompts by the key of one lesson scope."""
    groups: dict[str, list[ScoredPrompt]] = {}
    for prompt, refused in scored:
        groups.setdefault(_key(prompt, scope), []).append((prompt, refused))
    return groups


def _key(prompt: GeneratedPrompt, scope: str) -> str:
    """Return the group key one prompt belongs to in a given scope."""
    if scope == CELL_SCOPE:
        return prompt.cell_key
    return f"{Cell.parse(prompt.cell_key).risk}-{prompt.mechanism}"
