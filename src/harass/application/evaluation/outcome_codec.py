"""Decode stored outcomes for evidence and statistical analysis."""

from typing import Any

from harass.domain.case_identifier import CaseIdentifier
from harass.domain.case_outcome import AttemptTranscript, CaseOutcome, JudgeTrace
from harass.domain.comprehension import ComprehensionSignal
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.taxonomy import ResponseCategory


def read_outcome(document: dict[str, Any], *, lightweight: bool = False) -> CaseOutcome:
    """Decode an outcome, optionally excluding transcript text."""
    case = EvaluationCase(
        CaseIdentifier.parse(document["case_id"]),
        "Stored request" if lightweight else document["original_prompt"],
        "Stored request" if lightweight else document["objective"],
    )
    transcript = None if lightweight else document.get("transcript")
    return CaseOutcome(
        case=case,
        response_category=ResponseCategory(document["response_category"])
        if document.get("response_category")
        else None,
        attack_succeeded=document.get("attack_succeeded"),
        error=document.get("error"),
        transcript=_transcript(transcript) if transcript else None,
        scenario_name=document.get("scenario"),
        leak_exact_match=document.get("leak_exact_match"),
        leak_rouge_l=document.get("leak_rouge_l"),
        submission_uncertain=document.get("submission_uncertain", False),
        technical_error=document.get("technical_error"),
        judge_requests=tuple(document.get("judge_requests", ())),
        elapsed_seconds=document.get("elapsed_seconds"),
        comprehension_signal=ComprehensionSignal(document["comprehension_signal"])
        if document.get("comprehension_signal")
        else None,
    )


def _transcript(transcript: dict[str, Any]) -> AttemptTranscript:
    """Rebuild the stored request, response and judge rationales."""
    return AttemptTranscript(
        transcript["sent_prompt"],
        transcript["response"],
        transcript.get("category_rationale"),
        transcript.get("attack_rationale"),
        _trace(transcript.get("category_judge")),
        _trace(transcript.get("attack_judge")),
    )


def _trace(document: dict[str, Any] | None) -> JudgeTrace | None:
    """Reconstruct the stored vote budget, observations and elapsed time."""
    return (
        JudgeTrace(document["vote_budget"], tuple(document["votes"]), document["elapsed_seconds"])
        if document
        else None
    )
