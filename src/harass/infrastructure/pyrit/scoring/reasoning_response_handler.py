"""Separate judge reasoning traces from structured verdicts."""

import uuid
from collections.abc import Sequence

from pyrit.models import (
    ComponentIdentifier,
    JsonResponseConfig,
    UnvalidatedScore,
)
from pyrit.score import ResponseHandler

REASONING_END_TAG = "</think>"


def remove_reasoning_trace(response_text: str) -> str:
    """Remove text through the final reasoning block when present.

    Splitting on the closing tag also covers chat templates that inject the
    opening tag into the prompt, in which case the model output contains only
    the closing tag.
    """
    return response_text.rsplit(REASONING_END_TAG, maxsplit=1)[-1]


class ReasoningModelResponseHandler(ResponseHandler):
    """Remove legacy thinking tags before verdict validation."""

    def __init__(
        self,
        wire_format_handler: ResponseHandler,
        *,
        structured_output: bool = False,
    ) -> None:
        """Wrap the handler that parses the verdict itself."""
        self._wire_format_handler = wire_format_handler
        self._structured_output = structured_output

    @property
    def json_response_config(self) -> JsonResponseConfig:
        """Request free-form output from the judge."""
        return (
            self._wire_format_handler.json_response_config
            if self._structured_output
            else JsonResponseConfig(enabled=False)
        )

    def parse(
        self,
        *,
        response_text: str,
        scorer_identifier: ComponentIdentifier,
        scored_prompt_id: str | uuid.UUID,
        category: Sequence[str] | str | None = None,
        objective: str | None = None,
    ) -> UnvalidatedScore:
        """Parse the verdict that follows the reasoning trace."""
        return self._wire_format_handler.parse(
            response_text=remove_reasoning_trace(response_text),
            scorer_identifier=scorer_identifier,
            scored_prompt_id=scored_prompt_id,
            category=category,
            objective=objective,
        )
