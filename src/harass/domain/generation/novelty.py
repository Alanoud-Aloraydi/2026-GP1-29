"""The novelty gate: a new draft must not repeat a known prompt.

Both axes drop a draft whose ROUGE-L against any dataset or stored prompt
reaches the limit, since it is a rewrite of that prompt rather than a new
one. Pure rules: the known texts are supplied by the caller.
"""

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from harass.domain.owasp_scenario import rouge_l

TOKENS = re.compile(r"\w+")
# A draft this close to a known prompt is a rewrite of it, not a new prompt.
ROUGE_LIMIT = 0.5


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
