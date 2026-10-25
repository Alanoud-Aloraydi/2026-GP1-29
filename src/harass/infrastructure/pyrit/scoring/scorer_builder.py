"""Assembly of the judge-model scorers from their rubric files."""

from pathlib import Path

from pyrit.models import SeedPrompt
from pyrit.prompt_target import PromptTarget
from pyrit.score import (
    ContentClassifier,
    JsonSchemaResponseHandler,
    TrueFalseQuestion,
    render_category_system_prompt,
    render_true_false_system_prompt,
)

from harass.infrastructure.pyrit.scoring.reasoning_response_handler import (
    ReasoningModelResponseHandler,
)
from harass.infrastructure.pyrit.scoring.request_aware_category_scorer import (
    RequestAwareCategoryScorer,
)
from harass.infrastructure.pyrit.scoring.voting_true_false_scorer import (
    VotingTrueFalseScorer,
)

RUBRIC_DIRECTORY = Path(__file__).parent / "rubrics"


def build_response_category_scorer(
    judge: PromptTarget, *, votes: int, structured_output: bool = False
) -> RequestAwareCategoryScorer:
    """Build the XSTest response-category scorer."""
    content_classifier = ContentClassifier.from_yaml(
        RUBRIC_DIRECTORY / "response_categories.yaml"
    )
    system_prompt = render_category_system_prompt(
        content_classifier=content_classifier,
        system_prompt_template=SeedPrompt.from_yaml_file(
            RUBRIC_DIRECTORY / "response_category_system_prompt.yaml"
        ),
    )
    return RequestAwareCategoryScorer(
        chat_target=judge,
        system_prompt=system_prompt,
        content_classifier=content_classifier,
        response_handler=_reasoning_handler(
            system_prompt, structured_output=structured_output
        ),
        votes=votes,
    )


def build_attack_success_scorer(
    judge: PromptTarget, *, votes: int, structured_output: bool = False
) -> VotingTrueFalseScorer:
    """Build the attack-success scorer."""
    question = TrueFalseQuestion.from_yaml(
        RUBRIC_DIRECTORY / "attack_success_question.yaml"
    )
    system_prompt = render_true_false_system_prompt(
        question=question,
        system_prompt_template=SeedPrompt.from_yaml_file(
            RUBRIC_DIRECTORY / "attack_success_system_prompt.yaml"
        ),
    )
    return VotingTrueFalseScorer(
        chat_target=judge,
        system_prompt=system_prompt,
        question=question,
        response_handler=_reasoning_handler(
            system_prompt, structured_output=structured_output
        ),
        votes=votes,
    )


def _reasoning_handler(
    system_prompt: SeedPrompt, *, structured_output: bool
) -> ReasoningModelResponseHandler:
    """Build a reasoning-aware structured-verdict handler."""
    return ReasoningModelResponseHandler(
        JsonSchemaResponseHandler(
            response_schema=system_prompt.response_json_schema
        ),
        structured_output=structured_output,
    )
