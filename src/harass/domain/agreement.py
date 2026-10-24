"""Agreement between two raters labelling the same responses."""

from collections import Counter
from collections.abc import Sequence


def cohen_kappa(first: Sequence[str], second: Sequence[str]) -> float | None:
    """Compute Cohen's kappa for paired labels when defined.

    Kappa compares the observed agreement with the agreement expected by chance
    from each rater's label frequencies. It is undefined when there are no
    pairs or when chance agreement is already perfect (both raters always use
    the same single label).
    """
    if len(first) != len(second):
        raise ValueError(
            "Both raters must label the same number of responses."
        )
    total = len(first)
    if total == 0:
        return None
    observed = (
        sum(1 for a, b in zip(first, second, strict=True) if a == b) / total
    )
    first_counts, second_counts = Counter(first), Counter(second)
    expected = (
        sum(
            first_counts[label] * second_counts[label]
            for label in first_counts
        )
        / total**2
    )
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)
