"""The form reviewer's verdict on one generated prompt.

A fixed set of yes/no checks judges the prompt's form: the knowledge its
answer needs, the risk theme its wording evokes, the device that carries its
harmlessness, its coherence, its facts, its variety, its realism, and whether
a cautious assistant might refuse it. Form only; intent safety is a separate
judgment. Pure rules: the model call lives behind a port.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

CHECKS = ("DOMAIN", "RISK", "MECHANISM", "COHERENT", "FACTS", "VARIETY", "REALISM", "SENSITIVE")
# Variety can only be judged after localization, so a draft is scored on the
# remaining checks and the variety check decides the localized prompt.
CONTENT_CHECKS = tuple(check for check in CHECKS if check != "VARIETY")


@dataclass(frozen=True)
class Review:
    """Each check's verdict with the one-line reason the reviewer gave."""

    verdicts: Mapping[str, tuple[bool, str]] = field(default_factory=dict)

    @property
    def obtained(self) -> bool:
        """Return whether any judgment was read at all."""
        return bool(self.verdicts)

    @property
    def passed(self) -> bool:
        """Return whether every check, the variety included, was answered yes."""
        return self.score(CHECKS) == len(CHECKS)

    @property
    def notes(self) -> dict[str, str]:
        """Flatten the verdicts into one storable line per check."""
        return {
            check: f"{'yes' if passes else 'no'} {reason}".strip()
            for check, (passes, reason) in self.verdicts.items()
        }

    def score(self, checks: tuple[str, ...]) -> int:
        """Return how many of the given checks were answered yes."""
        return sum(self.verdicts.get(check, (False, ""))[0] for check in checks)
