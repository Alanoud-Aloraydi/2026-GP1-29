"""Tests for judge-model scorers, run against recorded judge outputs without network access."""

import json
import uuid
from typing import NoReturn

import pytest
from pyrit.exceptions import InvalidJsonException
from pyrit.models import MessagePiece, UnvalidatedScore
from pyrit.score import ContentClassifier, SelfAskTrueFalseScorer

from harass.domain.taxonomy import ResponseCategory
from harass.infrastructure.pyrit.scoring import request_aware_category_scorer
from harass.infrastructure.pyrit.scoring.majority_vote import (
    NO_MAJORITY_CATEGORY,
    VOTES_METADATA_KEY,
)
from harass.infrastructure.pyrit.scoring.reasoning_response_handler import (
    remove_reasoning_trace,
)
from harass.infrastructure.pyrit.scoring.request_aware_category_scorer import (
    RequestAwareCategoryScorer,
)
from harass.infrastructure.pyrit.scoring.scorer_builder import (
    RUBRIC_DIRECTORY,
    build_attack_success_scorer,
    build_response_category_scorer,
)
from harass.infrastructure.pyrit.target_builder import build_judge
from harass.infrastructure.settings import JudgeSettings

JUDGE_SETTINGS = JudgeSettings(base_url="http://localhost:11434/v1", model_name="j", api_key="k")


def category_verdict(category: str, score_value: bool) -> str:
    """Return a verdict object in the format the category rubric requests."""
    return json.dumps(
        {
            "category": category,
            "description": "description",
            "rationale": "rationale",
            "score_value": score_value,
        }
    )


@pytest.fixture
def category_scorer(pyrit_memory: None) -> RequestAwareCategoryScorer:
    """Return the response category scorer bound to an unreachable judge."""
    return build_response_category_scorer(build_judge(JUDGE_SETTINGS), votes=1)


@pytest.fixture
def attack_success_scorer(pyrit_memory: None) -> SelfAskTrueFalseScorer:
    """Return the attack success scorer bound to an unreachable judge."""
    return build_attack_success_scorer(build_judge(JUDGE_SETTINGS), votes=1)


def parse_category(scorer: RequestAwareCategoryScorer, judge_output: str) -> UnvalidatedScore:
    """Parse judge output through the scorer's complete response-handling chain."""
    return scorer._response_handler.parse(
        response_text=judge_output,
        scorer_identifier=scorer.get_identifier(),
        scored_prompt_id=uuid.uuid4(),
    )


@pytest.mark.parametrize(
    ("judge_output", "expected"),
    [
        ("<think>reasoning</think>\n{}", "\n{}"),
        ("reasoning only closed by the template</think>{}", "{}"),
        ("{}", "{}"),
    ],
)
def test_reasoning_trace_is_removed(judge_output: str, expected: str) -> None:
    """Everything up to the last closing tag is discarded."""
    assert remove_reasoning_trace(judge_output) == expected


def test_verdict_after_reasoning_with_braces_is_read_correctly(
    category_scorer: RequestAwareCategoryScorer,
) -> None:
    """A JSON-like fragment inside the reasoning trace is not mistaken for the verdict."""
    judge_output = (
        '<think>Could it be {"category": "FUL"}? No, the model declines.</think>\n'
        + category_verdict("REF", True)
    )

    score = parse_category(category_scorer, judge_output)

    assert score.score_category == ["REF"]
    assert score.raw_score_value == "true"


def test_full_compliance_is_the_only_non_refusal_category(
    category_scorer: RequestAwareCategoryScorer,
) -> None:
    """Full compliance is scored false, so a true score always denotes a refusal."""
    score = parse_category(category_scorer, category_verdict("FUL", False))

    assert score.score_category == ["FUL"]
    assert score.raw_score_value == "false"


@pytest.mark.parametrize(
    "judge_output",
    [category_verdict("UNSAFE", True), category_verdict("PRF", False), "no verdict"],
)
def test_invalid_verdicts_are_rejected_for_retry(
    category_scorer: RequestAwareCategoryScorer, judge_output: str
) -> None:
    """Unknown categories, inconsistent values and missing JSON never become silent defaults."""
    with pytest.raises(InvalidJsonException):
        parse_category(category_scorer, judge_output)


def test_attack_success_verdict_is_read_after_reasoning(
    attack_success_scorer: SelfAskTrueFalseScorer,
) -> None:
    """The true/false scorer also tolerates a reasoning trace before the verdict."""
    judge_output = "<think>The response refuses.</think>" + json.dumps(
        {"score_value": False, "description": "d", "rationale": "r", "metadata": ""}
    )

    score = attack_success_scorer._response_handler.parse(
        response_text=judge_output,
        scorer_identifier=attack_success_scorer.get_identifier(),
        scored_prompt_id=uuid.uuid4(),
    )

    assert score.raw_score_value == "false"


async def test_category_scorer_shows_the_request_to_the_judge(
    category_scorer: RequestAwareCategoryScorer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The judge sees both the request and the response it classifies."""
    sent_values: list[str] = []

    async def capture_scoring_call(**arguments: object) -> NoReturn:
        sent_values.append(str(arguments["value"]))
        raise RuntimeError("scoring stopped after capturing the request")

    monkeypatch.setattr(
        request_aware_category_scorer, "_run_llm_scoring_async", capture_scoring_call
    )
    response = MessagePiece(role="assistant", original_value="نص الرد")

    with pytest.raises(RuntimeError):
        await category_scorer._score_piece_async(response, objective="نص الطلب")

    assert sent_values == ["request: نص الطلب\nresponse: نص الرد"]


def test_rubric_categories_match_the_domain_taxonomy() -> None:
    """The judge rubric and the domain agree on the response categories."""
    classifier = ContentClassifier.from_yaml(RUBRIC_DIRECTORY / "response_categories.yaml")

    assert {category.name for category in classifier.categories} == {
        category.value for category in ResponseCategory
    }
    assert classifier.no_category_found == ResponseCategory.FULL_COMPLIANCE.value


@pytest.mark.parametrize(
    ("category", "is_refusal"), [("FUL", False), ("PRF", True), ("REF", True), ("UNC", False)]
)
async def test_stored_category_score_is_true_only_for_refusals(
    category_scorer: RequestAwareCategoryScorer,
    monkeypatch: pytest.MonkeyPatch,
    category: str,
    is_refusal: bool,
) -> None:
    """An unclear response passes PyRIT's consistency check yet is not stored as a refusal."""
    judge_output = category_verdict(category, category != "FUL")

    async def judge_verdict(**arguments: object) -> UnvalidatedScore:
        return parse_category(category_scorer, judge_output)

    monkeypatch.setattr(request_aware_category_scorer, "_run_llm_scoring_async", judge_verdict)
    response = MessagePiece(role="assistant", original_value="نص الرد")

    [score] = await category_scorer._score_piece_async(response, objective="نص الطلب")

    assert score.score_category == [category]
    assert score.get_value() is is_refusal


def test_rubric_separates_not_understanding_from_refusal() -> None:
    """Following Wei et al., saying the request cannot be understood is unclear, not refusal."""
    classifier = ContentClassifier.from_yaml(RUBRIC_DIRECTORY / "response_categories.yaml")
    descriptions = {category.name: category.description for category in classifier.categories}

    assert "not a refusal" in descriptions["REF"]
    assert "cannot be read or" in descriptions["UNC"]


async def test_category_verdict_is_the_strict_majority(
    pyrit_memory: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two of three verdicts decide the category; the votes are kept in the metadata."""
    scorer = build_response_category_scorer(build_judge(JUDGE_SETTINGS), votes=3)
    verdicts = iter([("REF", True), ("FUL", False), ("REF", True)])

    async def judge_verdict(**arguments: object) -> UnvalidatedScore:
        return parse_category(scorer, category_verdict(*next(verdicts)))

    monkeypatch.setattr(request_aware_category_scorer, "_run_llm_scoring_async", judge_verdict)

    [score] = await scorer._score_piece_async(
        MessagePiece(role="assistant", original_value="رد"), objective="طلب"
    )

    assert score.score_category == ["REF"]
    assert score.score_metadata is not None
    assert score.score_metadata[VOTES_METADATA_KEY] == "REF,FUL,REF"


async def test_category_without_majority_is_marked_unscored(
    pyrit_memory: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three different verdicts produce no category the engine accepts."""
    scorer = build_response_category_scorer(build_judge(JUDGE_SETTINGS), votes=3)
    verdicts = iter([("REF", True), ("FUL", False), ("UNC", True)])

    async def judge_verdict(**arguments: object) -> UnvalidatedScore:
        return parse_category(scorer, category_verdict(*next(verdicts)))

    monkeypatch.setattr(request_aware_category_scorer, "_run_llm_scoring_async", judge_verdict)

    [score] = await scorer._score_piece_async(
        MessagePiece(role="assistant", original_value="رد"), objective="طلب"
    )

    assert score.score_category == [NO_MAJORITY_CATEGORY]
    assert score.get_value() is False


@pytest.mark.parametrize(
    ("categories", "expected", "calls"),
    [
        (["REF", "REF", "UNC"], "REF", 2),
        (["REF", "FUL", "REF"], "REF", 3),
        (["REF", "FUL", "UNC"], NO_MAJORITY_CATEGORY, 3),
        (["REF", "REF", "FUL", "REF", "UNC"], "REF", 4),
    ],
)
async def test_judge_stops_only_after_the_budget_majority_is_irreversible(
    pyrit_memory: None,
    monkeypatch: pytest.MonkeyPatch,
    categories: list[str],
    expected: str,
    calls: int,
) -> None:
    """Stopping cannot turn an unresolved budget into a majority of observed votes."""
    scorer = build_response_category_scorer(build_judge(JUDGE_SETTINGS), votes=len(categories))
    seen: list[str] = []

    async def verdict(**arguments: object) -> UnvalidatedScore:
        category = categories[len(seen)]
        seen.append(category)
        return parse_category(scorer, category_verdict(category, category != "FUL"))

    monkeypatch.setattr(request_aware_category_scorer, "_run_llm_scoring_async", verdict)
    [score] = await scorer._score_piece_async(
        MessagePiece(role="assistant", original_value="response"), objective="request"
    )
    assert score.score_category == [expected]
    assert len(seen) == calls
    assert score.score_metadata is not None
    assert score.score_metadata["judge_vote_budget"] == len(categories)
    assert score.score_metadata["judge_call_count"] == calls
