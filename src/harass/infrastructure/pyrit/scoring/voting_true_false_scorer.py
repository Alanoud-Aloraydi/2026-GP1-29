"""Aggregate independent binary judge votes by majority."""

from pyrit.models import MessagePiece, Score, SeedPrompt
from pyrit.prompt_target import PromptTarget
from pyrit.score import (
    ResponseHandler,
    SelfAskTrueFalseScorer,
    TrueFalseQuestion,
)

from harass.infrastructure.pyrit.scoring.majority_vote import collect_majority


class VotingTrueFalseScorer(SelfAskTrueFalseScorer):
    """Repeat the question until its predeclared strict majority is settled."""

    def __init__(
        self,
        *,
        chat_target: PromptTarget,
        system_prompt: SeedPrompt,
        question: TrueFalseQuestion,
        response_handler: ResponseHandler,
        votes: int,
    ) -> None:
        """Configure judge votes and construct the wrapped scorer."""
        super().__init__(
            chat_target=chat_target,
            system_prompt=system_prompt,
            question=question,
            response_handler=response_handler,
        )
        self._votes = votes

    async def _score_piece_async(
        self, message_piece: MessagePiece, *, objective: str | None = None
    ) -> list[Score]:
        """Aggregate independent binary verdicts for one response."""

        async def verdict() -> Score:
            """Request one independent binary judgment."""
            return (
                await super(VotingTrueFalseScorer, self)._score_piece_async(
                    message_piece, objective=objective
                )
            )[0]

        score = await collect_majority(
            verdict,
            votes=self._votes,
            key=lambda score: str(score.score_value).lower(),
        )
        return [score]
