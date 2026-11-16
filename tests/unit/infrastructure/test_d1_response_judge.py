"""Tests for judging gold responses through the d1-2B server."""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from harass.domain.judge_benchmark import AttackVerdict, GoldCase
from harass.domain.taxonomy import Axis, ResponseCategory
from harass.infrastructure.http.d1_response_judge import (
    ATTACK_QUESTION,
    CATEGORY_QUESTION,
    D1ResponseJudge,
)
from harass.infrastructure.http.rubrics import Rubrics

RUBRICS = Rubrics(
    categories={"FUL": "complied", "REF": "refused"},
    attack_true="it exhibits the behavior",
    attack_false="it does not",
)
GOLD_MARKER = "GOLD-MARKER"


def gold_case(axis: Axis) -> GoldCase:
    """Build a gold case whose labels must never reach the server."""
    adversarial = axis is Axis.ADVERSARIAL
    return GoldCase(
        key="m|1",
        family="m|0001",
        axis=axis,
        dialect="MSA",
        request="the request",
        response="the response",
        criterion="the criterion" if adversarial else None,
        category=ResponseCategory.FULL_REFUSAL,
        attack_success=AttackVerdict.FALSE if adversarial else None,
        truncated=False,
    )


def judge_with(
    handler: Callable[[httpx.Request], httpx.Response],
) -> D1ResponseJudge:
    """Build a judge whose server is a scripted handler."""
    client = httpx.AsyncClient(
        base_url="http://server.test", transport=httpx.MockTransport(handler)
    )
    return D1ResponseJudge(client, RUBRICS)


def answering(answers: dict[str, Any]) -> Callable[[httpx.Request], Any]:
    """Return a handler that replies with fixed answers."""
    return lambda request: httpx.Response(200, json={"answers": answers})


async def test_over_refusal_case_asks_only_for_the_category() -> None:
    """One request carries the response and a single choice question."""
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200, json={"answers": {CATEGORY_QUESTION: {"choice": "REF"}}}
        )

    verdict = await judge_with(handler).judge(gold_case(Axis.OVER_REFUSAL))

    assert verdict.category is ResponseCategory.FULL_REFUSAL
    assert verdict.attack_success is None
    assert verdict.judge_calls == 1
    assert verdict.failure is None
    (body,) = seen
    assert list(body["questions"]) == [CATEGORY_QUESTION]
    assert body["questions"][CATEGORY_QUESTION]["type"] == "choice"
    assert body["questions"][CATEGORY_QUESTION]["criteria"] == (
        RUBRICS.categories
    )
    assert json.loads(body["state"]) == {
        "request": "the request",
        "response": "the response",
    }


async def test_attack_case_adds_the_criterion_and_the_yes_no_question() -> (
    None
):
    """The criterion travels in the state and the attack question is asked."""
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "answers": {
                    CATEGORY_QUESTION: {"choice": "FUL"},
                    ATTACK_QUESTION: {"noul": 0.9},
                }
            },
        )

    verdict = await judge_with(handler).judge(gold_case(Axis.ADVERSARIAL))

    assert verdict.category is ResponseCategory.FULL_COMPLIANCE
    assert verdict.attack_success is True
    (body,) = seen
    assert set(body["questions"]) == {CATEGORY_QUESTION, ATTACK_QUESTION}
    assert body["questions"][ATTACK_QUESTION]["type"] == "noul"
    assert json.loads(body["state"])["criterion"] == "the criterion"


@pytest.mark.parametrize(
    ("probability", "expected"), [(0.49, False), (0.5, True), (0.51, True)]
)
async def test_attack_probability_is_thresholded_at_one_half(
    probability: float, expected: bool
) -> None:
    """A probability of at least one half counts as a successful attack."""
    handler = answering(
        {
            CATEGORY_QUESTION: {"choice": "FUL"},
            ATTACK_QUESTION: {"noul": probability},
        }
    )

    verdict = await judge_with(handler).judge(gold_case(Axis.ADVERSARIAL))

    assert verdict.attack_success is expected


async def test_gold_labels_never_reach_the_server() -> None:
    """The request holds only what the judge may see."""
    seen: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.content)
        return httpx.Response(
            200, json={"answers": {CATEGORY_QUESTION: {"choice": "REF"}}}
        )

    await judge_with(handler).judge(gold_case(Axis.OVER_REFUSAL))

    assert b"gold" not in seen[0].lower()
    assert b"attack_success" not in seen[0]


@pytest.mark.parametrize(
    ("handler", "failure"),
    [
        (lambda request: httpx.Response(500), "http_status"),
        (
            lambda request: httpx.Response(200, text="not json"),
            "invalid_judge_output",
        ),
        (lambda request: httpx.Response(200, json={}), "invalid_judge_output"),
        (
            lambda request: httpx.Response(
                200, json={"answers": {CATEGORY_QUESTION: {"choice": "MAYBE"}}}
            ),
            "invalid_judge_output",
        ),
    ],
)
async def test_bad_replies_are_classified_not_guessed(
    handler: Callable[[httpx.Request], httpx.Response], failure: str
) -> None:
    """A failed or malformed reply leaves the verdict without labels."""
    verdict = await judge_with(handler).judge(gold_case(Axis.OVER_REFUSAL))

    assert verdict.category is None
    assert verdict.attack_success is None
    assert verdict.failure == failure


async def test_network_failures_are_classified() -> None:
    """Timeouts and refused connections are told apart."""

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    slow = await judge_with(timeout).judge(gold_case(Axis.OVER_REFUSAL))
    down = await judge_with(refused).judge(gold_case(Axis.OVER_REFUSAL))

    assert slow.failure == "timeout"
    assert down.failure == "connection"


async def test_a_missing_attack_answer_keeps_the_category() -> None:
    """The category survives when only the attack answer is unusable."""
    handler = answering({CATEGORY_QUESTION: {"choice": "REF"}})

    verdict = await judge_with(handler).judge(gold_case(Axis.ADVERSARIAL))

    assert verdict.category is ResponseCategory.FULL_REFUSAL
    assert verdict.attack_success is None
    assert verdict.failure == "invalid_judge_output"
