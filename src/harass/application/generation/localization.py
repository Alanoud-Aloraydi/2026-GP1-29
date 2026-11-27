"""Rewrite a Modern Standard Arabic draft into its variety behind rule gates.

Both axes localize the same way: a rewrite is rejected for markers of another
variety, formal leakage, an echo of the localizer's own brief or an added
question, and only then is the axis's own acceptance check asked, since that
check may cost a model call.
"""

from collections.abc import Awaitable, Callable

from harass.application.ports.generation import BriefWriter
from harass.domain.generation.dialect import foreign_markers, formal_leakage
from harass.domain.generation.localization_briefs import (
    INSTRUCTION_PHRASES,
    echoes_instructions,
    localize_brief,
    question_count,
)
from harass.domain.taxonomy import ArabicVariety

LOCALIZE_ATTEMPTS = 3
# The localizer sometimes opens with a lone diacritic or a colon on its own line.
STRAY_MARKS = "".join(map(chr, range(0x064B, 0x0653))) + " :\n"

type AcceptRewrite = Callable[[str, str], Awaitable[bool]]


class VarietyLocalizer:
    """Turn one MSA draft into its variety, or report that it could not."""

    def __init__(
        self,
        writer: BriefWriter,
        echo_phrases: tuple[str, ...] = INSTRUCTION_PHRASES,
        attempts: int = LOCALIZE_ATTEMPTS,
    ) -> None:
        """Bind the localizing model, the axis's echo phrases and the budget."""
        self._writer = writer
        self._echo_phrases = echo_phrases
        self._attempts = attempts

    async def localize(
        self, written: str, variety: ArabicVariety, accept: AcceptRewrite | None = None
    ) -> str | None:
        """Return the first rewrite that passes every gate, or None.

        Modern Standard Arabic needs no rewrite. Costs at most ``attempts``
        localizer calls plus one ``accept`` call per rewrite that passed the
        rule gates.
        """
        if variety is ArabicVariety.MODERN_STANDARD:
            return written
        brief = localize_brief(written, variety)
        for _ in range(self._attempts):
            rewrite = (await self._writer.write(brief)).lstrip(STRAY_MARKS).strip()
            if not rewrite or foreign_markers(rewrite, str(variety)) or formal_leakage(rewrite):
                continue
            if echoes_instructions(rewrite, self._echo_phrases):
                continue
            if question_count(rewrite) > question_count(written):
                continue
            if accept is None or await accept(written, rewrite):
                return rewrite
        return None
