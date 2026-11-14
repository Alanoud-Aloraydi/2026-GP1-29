"""Port for the judge model whose verdicts are benchmarked."""

from abc import ABC, abstractmethod

from harass.domain.judge_benchmark import GoldCase, JudgeVerdict


class ResponseJudge(ABC):
    """Judge one recorded target response."""

    @abstractmethod
    async def judge(self, case: GoldCase) -> JudgeVerdict:
        """Return a verdict that never depends on the case's gold labels.

        A technical failure is returned as a verdict without labels, never
        as a guessed category.
        """
