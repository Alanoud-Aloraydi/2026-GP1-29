"""Validated selections and immutable inputs for evaluation admission."""

from dataclasses import asdict, dataclass, field
from typing import Any

from harass.domain.case_selection import CaseSelection
from harass.domain.prompt_variant import AdaptiveSettings, VariantSelection


@dataclass(frozen=True)
class RunParameters:
    """What a client chose for a run, besides which connection to evaluate."""

    selection: CaseSelection = field(default_factory=CaseSelection)
    include_baseline: bool = True
    max_base_cases_per_axis: int | None = None
    sampling_seed: int = 0
    variant_selection: VariantSelection = field(
        default_factory=VariantSelection
    )
    adaptive_settings: AdaptiveSettings = field(
        default_factory=AdaptiveSettings
    )

    def document(self) -> dict[str, Any]:
        """Return JSON-compatible job inputs without any target credentials."""
        document = asdict(self)
        document["selection"] = {
            key: sorted(value) if isinstance(value, frozenset) else value
            for key, value in document["selection"].items()
        }
        return document
