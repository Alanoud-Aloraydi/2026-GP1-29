"""What a generation round is asked for and what it reports back."""

from collections import Counter
from dataclasses import dataclass

from harass.domain.generation.history import GeneratedPrompt, Lesson, PromptOutcome
from harass.domain.generation.pattern_card import Card
from harass.domain.metrics import Proportion
from harass.domain.target_connection import TargetConnection
from harass.domain.taxonomy import ResponseCategory

MEASUREMENT_ROUND = 0


@dataclass(frozen=True)
class GenerationRequest:
    """One round of generation against the client's own target model.

    ``send_to_target`` is false while prompts are still being reviewed by a
    human, so a round can be produced and read before any request is sent.
    """

    target: TargetConnection
    round_index: int = MEASUREMENT_ROUND
    count: int = 5
    send_to_target: bool = True
    run_identifier: str = ""

    @property
    def is_discovery(self) -> bool:
        """Return whether this round may exploit what earlier rounds learned.

        Round zero is the measurement round: nothing has been optimised
        against the target before it, so its rate is an unbiased measurement.
        Later rounds are discovery rounds and concentrate on refused cells.
        """
        return self.round_index > MEASUREMENT_ROUND


@dataclass(frozen=True)
class RoundReport:
    """What one round produced and the rate its scored prompts give."""

    round_index: int
    target_model: str
    prompts: tuple[GeneratedPrompt, ...] = ()
    outcomes: tuple[PromptOutcome, ...] = ()
    lessons: tuple[Lesson, ...] = ()
    cards: tuple[Card, ...] = ()

    @property
    def valid_prompts(self) -> tuple[GeneratedPrompt, ...]:
        """Return the prompts that passed both the review and safety gates."""
        return tuple(prompt for prompt in self.prompts if prompt.is_valid)

    @property
    def categories(self) -> Counter[ResponseCategory]:
        """Count the target's response categories in this round."""
        return Counter(outcome.response_category for outcome in self.outcomes)

    @property
    def over_refusal(self) -> Proportion:
        """Return refusals over scored prompts; unclear replies are excluded."""
        verdicts = [outcome.refused for outcome in self.outcomes if outcome.refused is not None]
        return Proportion(count=sum(verdicts), total=len(verdicts))
