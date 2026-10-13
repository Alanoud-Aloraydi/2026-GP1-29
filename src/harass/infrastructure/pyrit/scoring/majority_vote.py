"""Majority vote over repeated judge verdicts on the same response.

A reasoning judge sampled at its recommended temperature can return different verdicts for the
same response; the DeepSeek-R1 model card recommends running several tests and aggregating them.
Voting improves stability only: it does not make a weak judge accurate.
"""

import logging
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from time import perf_counter

from pyrit.models import Score

NO_MAJORITY_CATEGORY = "NO_MAJORITY"
VOTES_METADATA_KEY = "judge_votes"
logger = logging.getLogger(__name__)


async def collect_majority(
    verdict: Callable[[], Awaitable[Score]], *, votes: int, key: Callable[[Score], str]
) -> Score:
    """Stop only when remaining votes cannot change the predeclared majority decision."""
    if votes < 1 or votes % 2 == 0:
        raise ValueError("Judge votes must be odd and positive.")
    scores: list[Score] = []
    counts: Counter[str] = Counter()
    started = perf_counter()
    for _ in range(votes):
        score = await verdict()
        scores.append(score)
        counts[key(score)] += 1
        if counts[key(score)] > votes // 2:
            break
    result = majority_score(scores, key)
    logger.info(
        "Judge decision: %d/%d calls, %.2f seconds", len(scores), votes, perf_counter() - started
    )
    return result.model_copy(
        update={
            "score_metadata": {
                **(result.score_metadata or {}),
                "judge_vote_budget": votes,
                "judge_call_count": len(scores),
                "judge_elapsed_seconds": round(perf_counter() - started, 3),
            }
        }
    )


def majority_score(scores: Sequence[Score], key: Callable[[Score], str]) -> Score:
    """Return the first score carrying the strict-majority verdict, annotated with all votes.

    When no verdict holds a strict majority, the returned score carries the category
    ``NO_MAJORITY_CATEGORY`` and a false value, which downstream code treats as unscored.
    """
    if not scores:
        raise ValueError("At least one judge verdict is required.")
    votes = [key(score) for score in scores]
    winner, count = Counter(votes).most_common(1)[0]
    metadata = {**(scores[0].score_metadata or {}), VOTES_METADATA_KEY: ",".join(votes)}
    if count * 2 > len(votes):
        chosen = next(score for score in scores if key(score) == winner)
        return chosen.model_copy(update={"score_metadata": metadata})
    return scores[0].model_copy(
        update={
            "score_value": "false",
            "score_category": [NO_MAJORITY_CATEGORY],
            "score_rationale": f"No majority among judge verdicts: {', '.join(votes)}.",
            "score_metadata": metadata,
        }
    )
