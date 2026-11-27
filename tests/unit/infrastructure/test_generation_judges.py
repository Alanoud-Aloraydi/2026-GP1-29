"""Tests for the generator's model-backed reviewers, safety judge and reader."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from harass.domain.generation.cells import AttackCell, OverRefusalCell
from harass.domain.generation.pattern_card import Card
from harass.domain.generation.review import ATTACK_CHECKS, OVER_REFUSAL_CHECKS
from harass.domain.taxonomy import ArabicVariety, Axis, RiskCategory, SubjectDomain
from harass.infrastructure.http.generation_judges import (
    ModelAttackReviewer,
    ModelOverRefusalReviewer,
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
CELL = OverRefusalCell(
    SubjectDomain.MEDICINE_AND_HEALTH, RiskCategory.VIOLENCE_AND_HARM, ArabicVariety.NAJDI
)
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
        {
            check: {"pass": overrides.get(check, True), "reason": "reason"}
            for check in OVER_REFUSAL_CHECKS
        },
        ensure_ascii=False,
    )


async def test_the_rubric_carries_the_cell_in_arabic() -> None:
    """Verify the reviewer is told the domain, risk, mechanism and variety."""
    async with judging(passing_answer()) as (gateway, endpoint):
        review = await ModelOverRefusalReviewer(gateway, ROUTE).review(CELL, MECHANISM, "طلب")
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
        review = await ModelOverRefusalReviewer(gateway, ROUTE).review(CELL, MECHANISM, "طلب")
    assert not review.passed
    assert review.notes["FACTS"] == "no invented a date"


async def test_a_missing_check_fails_without_rejecting_the_answer() -> None:
    """Verify an absent check counts as failed, not as an unread answer."""
    verdicts = json.loads(passing_answer())
    del verdicts["SENSITIVE"]
    async with judging(json.dumps(verdicts)) as (gateway, endpoint):
        review = await ModelOverRefusalReviewer(gateway, ROUTE).review(CELL, MECHANISM, "طلب")
    assert review.obtained
    assert not review.passed
    assert len(endpoint.rubrics) == 1


async def test_an_unreadable_answer_is_asked_again_then_rejects() -> None:
    """Verify two unreadable answers leave an empty review, not a pass."""
    async with judging("no json here", "still nothing") as (gateway, endpoint):
        review = await ModelOverRefusalReviewer(gateway, ROUTE).review(CELL, MECHANISM, "طلب")
    assert not review.obtained
    assert not review.passed
    assert len(endpoint.rubrics) == 2


async def test_a_second_attempt_can_still_be_read() -> None:
    """Verify a malformed first answer does not lose a usable second one."""
    async with judging("", passing_answer()) as (gateway, _):
        assert (
            await ModelOverRefusalReviewer(gateway, ROUTE).review(CELL, MECHANISM, "طلب")
        ).passed


async def test_the_alarming_word_must_survive_localization() -> None:
    """Verify only an explicit PRESERVED verdict accepts a rewrite."""
    async with judging("PRESERVED قتل") as (gateway, _):
        assert await ModelOverRefusalReviewer(gateway, ROUTE).preserves_alarm("أصل", "لهجة")
    async with judging("LOST الكلمة") as (gateway, _):
        assert not await ModelOverRefusalReviewer(gateway, ROUTE).preserves_alarm("أصل", "لهجة")
    async with judging("") as (gateway, _):
        assert not await ModelOverRefusalReviewer(gateway, ROUTE).preserves_alarm("أصل", "لهجة")


async def test_safety_needs_an_explicit_safe_verdict() -> None:
    """Verify an unreadable or unsafe verdict never passes the gate."""
    async with judging("THING: x\nANSWER: y\nHARM: no\nVERDICT: SAFE") as (gateway, _):
        assert await ModelSafetyJudge(gateway, ROUTE).is_intent_safe("طلب")
    async with judging("VERDICT: UNSAFE") as (gateway, _):
        assert not await ModelSafetyJudge(gateway, ROUTE).is_intent_safe("طلب")
    async with judging("") as (gateway, _):
        assert not await ModelSafetyJudge(gateway, ROUTE).is_intent_safe("طلب")


def origin(axis: Axis = Axis.OVER_REFUSAL, strategy: str | None = None) -> Card:
    """Return what is known of a card before its prompt is read."""
    return Card(
        "G-1",
        "generated",
        "TBB",
        "VIO",
        form="",
        target="",
        device="",
        shape="",
        axis=axis,
        strategy=strategy,
        target_model="target",
    )


def pattern(device: str, form: str = "EXPLAIN", shape: str = "طلب إيذاء") -> str:
    """Return a reader answer naming one pattern."""
    return json.dumps(
        {"form": form, "target": "PERSON", "device": device, "shape": shape}, ensure_ascii=False
    )


async def test_a_pattern_is_read_into_a_card() -> None:
    """Verify a well-formed pattern completes the card it was read for."""
    async with judging(pattern("homonym")) as (gateway, _):
        card = await ModelPatternReader(gateway, ROUTE).read(origin(), "طلب")
    assert card is not None
    assert (card.card_id, card.source, card.target_model) == ("G-1", "generated", "target")
    assert card.pattern == (Axis.OVER_REFUSAL, "TBB", "VIO", "", "EXPLAIN", "PERSON", "homonym")


async def test_an_attack_pattern_takes_a_device_of_its_strategy() -> None:
    """Verify an attack is read with the devices of its own strategy only."""
    async with judging(pattern("fiction")) as (gateway, endpoint):
        card = await ModelPatternReader(gateway, ROUTE).read(origin(Axis.ADVERSARIAL, "ROL"), "x")
    assert card is not None
    assert (card.axis, card.strategy, card.device) == (Axis.ADVERSARIAL, "ROL", "fiction")
    assert "fiction" in endpoint.rubrics[0]
    async with judging(pattern("authority")) as (gateway, _):
        assert (
            await ModelPatternReader(gateway, ROUTE).read(origin(Axis.ADVERSARIAL, "ROL"), "x")
            is None
        )


async def test_a_pattern_outside_the_vocabulary_is_refused() -> None:
    """Verify an invented code or a missing shape yields no card."""
    for answer in (pattern("homonym", form="INVENTED"), pattern("homonym", shape="")):
        async with judging(answer) as (gateway, _):
            assert await ModelPatternReader(gateway, ROUTE).read(origin(), "x") is None


async def test_the_attack_reviewer_reads_every_attack_check() -> None:
    """Verify the attack rubric carries the cell and its eight checks are read."""
    cell = AttackCell.parse("AT-HSB-PRV-ROL-LLM08-MSA")
    answer = json.dumps(
        {check: {"pass": check != "NO_PAYLOAD", "reason": "r"} for check in ATTACK_CHECKS}
    )
    async with judging(answer) as (gateway, endpoint):
        review = await ModelAttackReviewer(gateway, ROUTE).review(cell, "طلب")
    assert "hidden internal operating context" in endpoint.rubrics[0]
    assert "التأطير بدور" in endpoint.rubrics[0]
    assert not review.passed
    assert review.score(ATTACK_CHECKS) == len(ATTACK_CHECKS) - 1


async def test_an_unreadable_attack_review_fails_closed() -> None:
    """Verify an attack review that cannot be read passes nothing."""
    async with judging("no json") as (gateway, _):
        review = await ModelAttackReviewer(gateway, ROUTE).review(
            AttackCell.parse("AT-DIN-VIO-DIR-NAP-MSA"), "طلب"
        )
    assert not review.obtained
    assert not review.passed
