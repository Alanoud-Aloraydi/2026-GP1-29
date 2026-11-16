"""Judge that takes each judgment from the model best suited to it."""

from dataclasses import replace

from harass.application.ports.response_judge import ResponseJudge
from harass.domain.judge_benchmark import GoldCase, JudgeVerdict
from harass.domain.taxonomy import Axis


class SplitResponseJudge(ResponseJudge):
    """Take the category from one judge and attack success from another.

    The category judge sees every case. On the attack axis the attack judge
    also sees it, and only its attack verdict is kept; its own category is
    ignored. Cost is the sum of both judges' calls and time.
    """

    def __init__(
        self, category_judge: ResponseJudge, attack_judge: ResponseJudge
    ) -> None:
        """Bind the judge for categories and the judge for attacks."""
        self._category_judge = category_judge
        self._attack_judge = attack_judge

    async def judge(self, case: GoldCase) -> JudgeVerdict:
        """Return the category verdict, completed with the attack verdict."""
        categorised = await self._category_judge.judge(case)
        if case.axis is not Axis.ADVERSARIAL:
            return categorised
        attack = await self._attack_judge.judge(case)
        return replace(
            categorised,
            attack_success=attack.attack_success,
            judge_calls=categorised.judge_calls + attack.judge_calls,
            elapsed_seconds=categorised.elapsed_seconds
            + attack.elapsed_seconds,
            failure=categorised.failure or attack.failure,
        )
