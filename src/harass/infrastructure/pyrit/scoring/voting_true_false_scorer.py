"""True/false scorer that asks the judge several times and keeps the majority verdict."""

from pyrit.models import MessagePiece, Score, SeedPrompt
from pyrit.prompt_target import PromptTarget
from pyrit.score import ResponseHandler, SelfAskTrueFalseScorer, TrueFalseQuestion

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
        """Store the number of judge verdicts per response and build the parent scorer."""
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
        """Return the majority of several independent verdicts on the same response."""

        async def verdict() -> Score:
            return (
                await super(VotingTrueFalseScorer, self)._score_piece_async(
                    message_piece, objective=objective
                )
            )[0]

        score = await collect_majority(
            verdict, votes=self._votes, key=lambda score: str(score.score_value).lower()
        )
        return [score]
