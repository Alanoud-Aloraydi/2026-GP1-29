"""Reconstruct stored outcomes for evidence pages and lightweight statistical summaries."""

from typing import Any

from harass.domain.case_identifier import CaseIdentifier
from harass.domain.case_outcome import AttemptTranscript, CaseOutcome, JudgeTrace
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.prompt_variant import PromptVariant
from harass.domain.taxonomy import BypassStrategy, ResponseCategory


def read_outcome(document: dict[str, Any], *, lightweight: bool = False) -> CaseOutcome:
    """Read a stored outcome, optionally omitting text that metrics never inspect."""
    case = EvaluationCase(
        CaseIdentifier.parse(document["case_id"]),
        "Stored request" if lightweight else document["original_prompt"],
        "Stored request" if lightweight else document["objective"],
    )
    recipe = document.get("variant")
    variant = None
    if recipe and not lightweight:
        variant = PromptVariant(
            **{
                **recipe,
                "transform_names": tuple(recipe["transform_names"]),
                "source_urls": tuple(recipe["source_urls"]),
                "effective_strategies": tuple(map(BypassStrategy, recipe["effective_strategies"])),
            }
        )
    transcript = document.get("transcript")
    recorded = None
    if transcript and not lightweight:
        recorded = AttemptTranscript(
            transcript["sent_prompt"],
            transcript["response"],
            transcript.get("category_rationale"),
            transcript.get("attack_rationale"),
            _trace(transcript.get("category_judge")),
            _trace(transcript.get("attack_judge")),
        )
    return CaseOutcome(
        case=case,
        variant_name=document["variant_name"],
        response_category=ResponseCategory(document["response_category"])
        if document.get("response_category")
        else None,
        attack_succeeded=document.get("attack_succeeded"),
        error=document.get("error"),
        transcript=recorded,
        variant=variant,
        attempt_number=document["attempt_number"],
        stop_reason=document.get("stop_reason"),
        posterior_before=tuple(document["posterior_before"])
        if document.get("posterior_before")
        else None,
        scenario_name=document.get("scenario"),
        leak_exact_match=document.get("leak_exact_match"),
        leak_rouge_l=document.get("leak_rouge_l"),
        submission_uncertain=document.get("submission_uncertain", False),
        technical_error=document.get("technical_error"),
        judge_requests=tuple(document.get("judge_requests", ())),
        elapsed_seconds=document.get("elapsed_seconds"),
    )


def _trace(document: dict[str, Any] | None) -> JudgeTrace | None:
    return (
        JudgeTrace(document["vote_budget"], tuple(document["votes"]), document["elapsed_seconds"])
        if document
        else None
    )
