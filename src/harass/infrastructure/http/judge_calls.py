"""Pieces that every decision-server judge shares."""

import httpx

from harass.domain.judge_benchmark import GoldCase
from harass.domain.taxonomy import Axis

JUDGE_ERRORS = (httpx.HTTPError, ValueError, KeyError, TypeError)


def classify_failure(error: Exception) -> str:
    """Name a judge call failure without keeping provider text."""
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, httpx.HTTPStatusError):
        return "http_status"
    if isinstance(error, httpx.HTTPError):
        return "connection"
    return "invalid_judge_output"


def case_state(
    case: GoldCase, *, with_criterion: bool = True
) -> dict[str, str]:
    """Show a judge the request and response, and the criterion if asked.

    The criterion only exists for adversarial cases, and no gold label is
    ever part of the state.
    """
    state = {"request": case.request, "response": case.response}
    if with_criterion and case.axis is Axis.ADVERSARIAL:
        state["criterion"] = case.criterion or ""
    return state
