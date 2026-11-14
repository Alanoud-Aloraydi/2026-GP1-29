"""Tests for the judge that escalates doubtful cases."""

from harass.application.escalating_response_judge import (
    EscalatingResponseJudge,
)
from harass.application.ports.response_judge import ResponseJudge
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


FAST_REFUSAL = JudgeVerdict(ResponseCategory.FULL_REFUSAL, False, 1, 1.0)
STRONG_COMPLIANCE = JudgeVerdict(
    ResponseCategory.FULL_COMPLIANCE, True, 1, 4.0
)


async def test_a_confirmed_attack_is_final() -> None:
    """The stronger judge is not asked when the fast one confirms."""
    fast = ScriptedJudge(
        JudgeVerdict(ResponseCategory.FULL_COMPLIANCE, True, 1, 1.0)
    )
    strong = ScriptedJudge(STRONG_COMPLIANCE)

    verdict = await EscalatingResponseJudge(fast, strong).judge(
        gold_case(Axis.ADVERSARIAL)
    )

    assert verdict == fast.verdict
    assert strong.calls == 0


async def test_an_unconfirmed_attack_goes_to_the_stronger_judge() -> None:
    """The second verdict replaces the first and the costs add up."""
    fast = ScriptedJudge(FAST_REFUSAL)
    strong = ScriptedJudge(STRONG_COMPLIANCE)

    verdict = await EscalatingResponseJudge(fast, strong).judge(
        gold_case(Axis.ADVERSARIAL)
    )

    assert verdict.category is ResponseCategory.FULL_COMPLIANCE
    assert verdict.attack_success is True
    assert verdict.judge_calls == 2
    assert verdict.elapsed_seconds == 5.0


async def test_an_abstention_is_escalated() -> None:
    """A doubtful first judge hands the case over."""
    fast = ScriptedJudge(
        JudgeVerdict(ResponseCategory.FULL_COMPLIANCE, None, 1, 1.0, ABSTAINED)
    )
    strong = ScriptedJudge(STRONG_COMPLIANCE)

    verdict = await EscalatingResponseJudge(fast, strong).judge(
        gold_case(Axis.ADVERSARIAL)
    )

    assert verdict.failure is None
    assert strong.calls == 1


async def test_over_refusal_cases_never_escalate() -> None:
    """The fast judge decides the whole over refusal axis."""
    fast = ScriptedJudge(FAST_REFUSAL)
    strong = ScriptedJudge(STRONG_COMPLIANCE)

    verdict = await EscalatingResponseJudge(fast, strong).judge(
        gold_case(Axis.OVER_REFUSAL)
    )

    assert verdict == FAST_REFUSAL
    assert strong.calls == 0
