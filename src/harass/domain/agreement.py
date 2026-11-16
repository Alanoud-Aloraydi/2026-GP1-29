"""Agreement between two raters labelling the same responses."""

from collections import Counter
from collections.abc import Callable, Sequence


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


def weighted_cohen_kappa(
    first: Sequence[str],
    second: Sequence[str],
    distance: Callable[[str, str], float],
) -> float | None:
    """Compute Cohen's kappa where each disagreement costs its distance.

    A distance of 0 means the labels agree and 1 is the worst disagreement, so
    swapping neighbouring ordinal labels is penalized less than swapping the
    extremes. With distances of only 0 and 1 this equals `cohen_kappa`. It is
    undefined for no pairs or when no disagreement is expected by chance.
    Time is O(n + k^2) for n pairs and k distinct labels.
    """
    if len(first) != len(second):
        raise ValueError(
            "Both raters must label the same number of responses."
        )
    total = len(first)
    if total == 0:
        return None
    observed = (
        sum(distance(a, b) for a, b in zip(first, second, strict=True)) / total
    )
    first_counts, second_counts = Counter(first), Counter(second)
    expected = (
        sum(
            first_counts[a] * second_counts[b] * distance(a, b)
            for a in first_counts
            for b in second_counts
        )
        / total**2
    )
    if expected == 0:
        return None
    return 1 - observed / expected
