"""Tests for the generator's model-backed reviewer, safety judge and reader."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from harass.domain.generation.cells import Cell
from harass.domain.generation.review import CHECKS
from harass.domain.taxonomy import ArabicVariety, RiskCategory, SubjectDomain
from harass.infrastructure.http.generation_judges import (
    ModelFormReviewer,
    ModelPatternReader,
    ModelSafetyJudge,
)
from harass.infrastructure.http.model_gateway import JudgingGateway, ModelGateway, ModelRoute

ROUTE = ModelRoute(
    endpoint="https://models.invalid/v1/chat/completions",
    api_key="k",
    model="reviewer-model",
    temperature=0.0,
    max_tokens=600,
)
CELL = Cell(SubjectDomain.MEDICINE_AND_HEALTH, RiskCategory.VIOLENCE_AND_HARM, ArabicVariety.NAJDI)
MECHANISM = "homonym"


class ScriptedEndpoint:
    """Answer each request with the next scripted model answer."""

    def __init__(self, *answers: str) -> None:
        """Store the answers to give in order, repeating the last one."""
        self.rubrics: list[str] = []
        self._answers = list(answers)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Record the rubric that was sent and answer it."""
        self.rubrics.append(json.loads(request.content)["messages"][0]["content"])
        answer = self._answers[min(len(self.rubrics) - 1, len(self._answers) - 1)]
        return httpx.Response(200, json={"choices": [{"message": {"content": answer}}]})


@asynccontextmanager
async def judging(*answers: str) -> AsyncIterator[tuple[JudgingGateway, ScriptedEndpoint]]:
    """Provide a judging gateway whose endpoint answers from a script."""
    endpoint = ScriptedEndpoint(*answers)
    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as client:
        yield JudgingGateway(ModelGateway(client)), endpoint


def passing_answer(**overrides: bool) -> str:
    """Return a review answer that passes every check but the overrides."""
    return json.dumps(
        {check: {"pass": overrides.get(check, True), "reason": "reason"} for check in CHECKS},
        ensure_ascii=False,
    )


async def test_the_rubric_carries_the_cell_in_arabic() -> None:
    """Verify the reviewer is told the domain, risk, mechanism and variety."""
    async with judging(passing_answer()) as (gateway, endpoint):
        review = await ModelFormReviewer(gateway, ROUTE).review(CELL, MECHANISM, "طلب")
    rubric = endpoint.rubrics[0]
    assert review.passed
    assert "الطب والصحة" in rubric
    assert "العامية النجدية" in rubric
    assert "معنيان" in rubric
    assert rubric.rstrip().endswith("طلب")


async def test_a_failed_check_is_read_with_its_reason() -> None:
    """Verify a false verdict fails the review and keeps its reason."""
    answer = json.dumps(
        {**json.loads(passing_answer()), "FACTS": {"pass": False, "reason": "invented a date"}}
    )
    async with judging(answer) as (gateway, _):
        review = await ModelFormReviewer(gateway, ROUTE).review(CELL, MECHANISM, "طلب")
    assert not review.passed
    assert review.notes["FACTS"] == "no invented a date"


async def test_a_missing_check_fails_without_rejecting_the_answer() -> None:
    """Verify an absent check counts as failed, not as an unread answer."""
    verdicts = json.loads(passing_answer())
    del verdicts["SENSITIVE"]
    async with judging(json.dumps(verdicts)) as (gateway, endpoint):
        review = await ModelFormReviewer(gateway, ROUTE).review(CELL, MECHANISM, "طلب")
    assert review.obtained
    assert not review.passed
    assert len(endpoint.rubrics) == 1


async def test_an_unreadable_answer_is_asked_again_then_rejects() -> None:
    """Verify two unreadable answers leave an empty review, not a pass."""
    async with judging("no json here", "still nothing") as (gateway, endpoint):
        review = await ModelFormReviewer(gateway, ROUTE).review(CELL, MECHANISM, "طلب")
    assert not review.obtained
    assert not review.passed
    assert len(endpoint.rubrics) == 2


async def test_a_second_attempt_can_still_be_read() -> None:
    """Verify a malformed first answer does not lose a usable second one."""
    async with judging("", passing_answer()) as (gateway, _):
        assert (await ModelFormReviewer(gateway, ROUTE).review(CELL, MECHANISM, "طلب")).passed


async def test_the_alarming_word_must_survive_localization() -> None:
    """Verify only an explicit PRESERVED verdict accepts a rewrite."""
    async with judging("PRESERVED قتل") as (gateway, _):
        assert await ModelFormReviewer(gateway, ROUTE).preserves_alarm("أصل", "لهجة")
    async with judging("LOST الكلمة") as (gateway, _):
        assert not await ModelFormReviewer(gateway, ROUTE).preserves_alarm("أصل", "لهجة")
    async with judging("") as (gateway, _):
        assert not await ModelFormReviewer(gateway, ROUTE).preserves_alarm("أصل", "لهجة")


async def test_safety_needs_an_explicit_safe_verdict() -> None:
    """Verify an unreadable or unsafe verdict never passes the gate."""
    async with judging("THING: x\nANSWER: y\nHARM: no\nVERDICT: SAFE") as (gateway, _):
        assert await ModelSafetyJudge(gateway, ROUTE).is_intent_safe("طلب")
    async with judging("VERDICT: UNSAFE") as (gateway, _):
        assert not await ModelSafetyJudge(gateway, ROUTE).is_intent_safe("طلب")
    async with judging("") as (gateway, _):
        assert not await ModelSafetyJudge(gateway, ROUTE).is_intent_safe("طلب")


async def test_a_pattern_is_read_into_a_card() -> None:
    """Verify a well-formed pattern becomes a card of the given cell codes."""
    answer = json.dumps(
        {"form": "EXPLAIN", "target": "PERSON", "harmless": "homonym", "shape": "طلب إيذاء"},
        ensure_ascii=False,
    )
    async with judging(answer) as (gateway, _):
        card = await ModelPatternReader(gateway, ROUTE).read(
            "G-1", "generated", "TBB", "VIO", "طلب"
        )
    assert card is not None
    assert (card.card_id, card.source, card.domain, card.risk) == ("G-1", "generated", "TBB", "VIO")
    assert card.pattern == ("TBB", "VIO", "EXPLAIN", "PERSON", "homonym")


async def test_a_pattern_outside_the_vocabulary_is_refused() -> None:
    """Verify an invented code or a missing shape yields no card."""
    invented = json.dumps(
        {"form": "INVENTED", "target": "PERSON", "harmless": "homonym", "shape": "x"}
    )
    shapeless = json.dumps(
        {"form": "EXPLAIN", "target": "PERSON", "harmless": "homonym", "shape": ""}
    )
    async with judging(invented) as (gateway, _):
        assert (
            await ModelPatternReader(gateway, ROUTE).read("G", "generated", "TBB", "VIO", "x")
            is None
        )
    async with judging(shapeless) as (gateway, _):
        assert (
            await ModelPatternReader(gateway, ROUTE).read("G", "generated", "TBB", "VIO", "x")
            is None
        )
