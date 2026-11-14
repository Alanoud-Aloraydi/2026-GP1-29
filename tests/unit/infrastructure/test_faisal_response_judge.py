"""Tests for judging gold responses through the Faisal server."""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from harass.domain.judge_benchmark import ABSTAINED, AttackVerdict, GoldCase
from harass.domain.taxonomy import Axis, ResponseCategory
from harass.infrastructure.http.faisal_response_judge import (
    FaisalResponseJudge,
)
from harass.infrastructure.http.rubrics import Rubrics

RUBRICS = Rubrics(
    categories={"FUL": "complied", "REF": "refused"},
    attack_true="it exhibits the behavior",
    attack_false="it does not",
)


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
) -> FaisalResponseJudge:
    """Build a judge whose server is a scripted handler."""
    client = httpx.AsyncClient(
        base_url="http://server.test", transport=httpx.MockTransport(handler)
    )
    return FaisalResponseJudge(client, RUBRICS)


def distribution(**probabilities: float) -> Callable[[httpx.Request], Any]:
    """Return a handler that replies with a fixed distribution."""
    return lambda request: httpx.Response(
        200, json={"probabilities": probabilities}
    )


def by_question(
    category: dict[str, float], attack: dict[str, float]
) -> Callable[[httpx.Request], httpx.Response]:
    """Return a handler that answers the category and attack questions."""

    def handler(request: httpx.Request) -> httpx.Response:
        keys = {o["key"] for o in json.loads(request.content)["options"]}
        answer = attack if "unknown" in keys else category
        return httpx.Response(200, json={"probabilities": answer})

    return handler


async def test_over_refusal_case_asks_the_category_question_once() -> None:
    """The most probable category is the verdict, from a single request."""
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200, json={"probabilities": {"FUL": 0.1, "REF": 0.9}}
        )

    verdict = await judge_with(handler).judge(gold_case(Axis.OVER_REFUSAL))

    assert verdict.category is ResponseCategory.FULL_REFUSAL
    assert verdict.attack_success is None
    assert verdict.judge_calls == 1
    assert verdict.failure is None
    (body,) = seen
    assert body["state"] == {
        "request": "the request",
        "response": "the response",
    }
    assert [option["key"] for option in body["options"]] == ["FUL", "REF"]


async def test_attack_case_adds_a_question_with_the_criterion() -> None:
    """The attack question sees the criterion and may answer unknown."""
    seen: list[dict[str, Any]] = []
    answering = by_question(
        {"FUL": 0.9, "REF": 0.1},
        {"success": 0.8, "failure": 0.1, "unknown": 0.1},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return answering(request)

    verdict = await judge_with(handler).judge(gold_case(Axis.ADVERSARIAL))

    assert verdict.category is ResponseCategory.FULL_COMPLIANCE
    assert verdict.attack_success is True
    assert verdict.judge_calls == 2
    assert "criterion" not in seen[0]["state"]
    assert seen[1]["state"]["criterion"] == "the criterion"
    assert [o["key"] for o in seen[1]["options"]] == [
        "success",
        "failure",
        "unknown",
    ]


async def test_choosing_failure_means_the_attack_did_not_succeed() -> None:
    """The failure option gives a false attack verdict."""
    handler = by_question(
        {"FUL": 0.1, "REF": 0.9},
        {"success": 0.1, "failure": 0.8, "unknown": 0.1},
    )

    verdict = await judge_with(handler).judge(gold_case(Axis.ADVERSARIAL))

    assert verdict.attack_success is False
    assert verdict.failure is None


async def test_choosing_unknown_abstains_on_the_attack_verdict() -> None:
    """Not enough information leaves the attack verdict unjudged."""
    handler = by_question(
        {"FUL": 0.9, "REF": 0.1},
        {"success": 0.1, "failure": 0.1, "unknown": 0.8},
    )

    verdict = await judge_with(handler).judge(gold_case(Axis.ADVERSARIAL))

    assert verdict.category is ResponseCategory.FULL_COMPLIANCE
    assert verdict.attack_success is None
    assert verdict.failure == ABSTAINED


async def test_gold_labels_never_reach_the_server() -> None:
    """The request holds only what the judge may see."""
    seen: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.content)
        return httpx.Response(
            200, json={"probabilities": {"FUL": 0.1, "REF": 0.9}}
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
        (distribution(FUL=0.5, REF=0.1), "invalid_judge_output"),
        (distribution(FUL=0.5, OTHER=0.5), "invalid_judge_output"),
    ],
)
async def test_failures_and_invalid_distributions_are_classified(
    handler: Callable[[httpx.Request], httpx.Response], failure: str
) -> None:
    """A broken reply becomes a failure class, never a guessed label."""
    verdict = await judge_with(handler).judge(gold_case(Axis.OVER_REFUSAL))

    assert verdict.category is None
    assert verdict.failure == failure


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (httpx.ReadTimeout("slow"), "timeout"),
        (httpx.ConnectError("down"), "connection"),
    ],
)
async def test_transport_failures_are_classified(
    raised: Exception, expected: str
) -> None:
    """A transport problem becomes a failure class without leaking text."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise raised

    verdict = await judge_with(handler).judge(gold_case(Axis.OVER_REFUSAL))

    assert verdict.failure == expected
