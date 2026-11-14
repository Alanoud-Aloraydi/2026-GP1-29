"""Judge with a fast model first and a stronger model for doubtful cases."""

from dataclasses import replace

from harass.application.ports.response_judge import ResponseJudge
from harass.domain.judge_benchmark import GoldCase, JudgeVerdict
from harass.domain.taxonomy import Axis


class EscalatingResponseJudge(ResponseJudge):
    """Ask the second judge only when the first one did not confirm an attack.

    A confirmed attack is final because the first judge is precise there.
    Every other attack-axis outcome, including a failure or an abstention,
    goes to the second judge, whose verdict replaces the first one. Over
    refusal cases never escalate, so most of the work stays on the fast
    model. Cost is the sum of both judges' calls and time.
    """

    def __init__(self, first: ResponseJudge, second: ResponseJudge) -> None:
        """Bind the fast judge and the stronger judge."""
        self._first = first
        self._second = second

    async def judge(self, case: GoldCase) -> JudgeVerdict:
        """Return the first verdict, or the second one after escalation."""
        first = await self._first.judge(case)
        if case.axis is not Axis.ADVERSARIAL or first.attack_success is True:
            return first
        second = await self._second.judge(case)
        return replace(
            second,
            judge_calls=first.judge_calls + second.judge_calls,
            elapsed_seconds=first.elapsed_seconds + second.elapsed_seconds,
        )
