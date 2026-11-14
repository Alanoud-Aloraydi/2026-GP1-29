"""Tests for the judge that splits categories from attack success."""

from harass.application.ports.response_judge import ResponseJudge
from harass.application.split_response_judge import SplitResponseJudge
from harass.domain.judge_benchmark import (
    ABSTAINED,
    AttackVerdict,
    GoldCase,
    JudgeVerdict,
)
from harass.domain.taxonomy import Axis, ResponseCategory


def gold_case(axis: Axis) -> GoldCase:
    """Build a gold case on the given axis."""
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


class ScriptedJudge(ResponseJudge):
    """A judge that returns one fixed verdict and counts its calls."""

    def __init__(self, verdict: JudgeVerdict) -> None:
        """Keep the verdict to return."""
        self.verdict = verdict
        self.calls = 0

    async def judge(self, case: GoldCase) -> JudgeVerdict:
        """Return the scripted verdict."""
        self.calls += 1
        return self.verdict


CATEGORISED = JudgeVerdict(ResponseCategory.PARTIAL_REFUSAL, False, 1, 1.0)
ATTACKED = JudgeVerdict(ResponseCategory.FULL_COMPLIANCE, True, 1, 4.0)


async def test_an_attack_case_combines_both_judges() -> None:
    """The category comes from the first judge, the attack from the second."""
    verdict = await SplitResponseJudge(
        ScriptedJudge(CATEGORISED), ScriptedJudge(ATTACKED)
    ).judge(gold_case(Axis.ADVERSARIAL))

    assert verdict.category is ResponseCategory.PARTIAL_REFUSAL
    assert verdict.attack_success is True
    assert verdict.judge_calls == 2
    assert verdict.elapsed_seconds == 5.0


async def test_over_refusal_cases_skip_the_attack_judge() -> None:
    """Only the category judge sees the over refusal axis."""
    attack_judge = ScriptedJudge(ATTACKED)

    verdict = await SplitResponseJudge(
        ScriptedJudge(CATEGORISED), attack_judge
    ).judge(gold_case(Axis.OVER_REFUSAL))

    assert verdict == CATEGORISED
    assert attack_judge.calls == 0


async def test_an_attack_judge_abstention_is_kept() -> None:
    """The abstention is reported and the category is still scored."""
    abstained = JudgeVerdict(
        ResponseCategory.FULL_COMPLIANCE, None, 1, 1.0, ABSTAINED
    )

    verdict = await SplitResponseJudge(
        ScriptedJudge(CATEGORISED), ScriptedJudge(abstained)
    ).judge(gold_case(Axis.ADVERSARIAL))

    assert verdict.category is ResponseCategory.PARTIAL_REFUSAL
    assert verdict.attack_success is None
    assert verdict.failure == ABSTAINED
