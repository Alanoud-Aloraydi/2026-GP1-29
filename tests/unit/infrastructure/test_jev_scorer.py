"""Exercise Jev's PyRIT contract without sending prompts to a provider."""

import json

import httpx
import pytest
from pyrit.models import MessagePiece

from harass.infrastructure.pyrit.scoring.jev_scorer import JevJudge, JevScorer
from harass.infrastructure.pyrit.scoring.scorer_builder import build_response_category_scorer
from harass.infrastructure.pyrit.target_builder import build_judge, close_target
from harass.infrastructure.settings import Settings


@pytest.mark.parametrize(
    ("attack", "choice", "category", "value"),
    [
        (False, "FUL", "FUL", False),
        (False, "PRF", "PRF", True),
        (False, "REF", "REF", True),
        (False, "UNC", "UNC", False),
        (True, "success", "attack_success", True),
        (True, "failure", "attack_success", False),
    ],
)
async def test_jev_preserves_score_contract(
    pyrit_memory: None, attack: bool, choice: str, category: str, value: bool
) -> None:
    """Real PyRIT scoring preserves labels and links the supplied message."""
    judge = JevJudge(api_key="test-key", model="jev-1.13.0", min_confidence=0.8)
    scorer = JevScorer(judge=judge, attack=attack)
    await judge.client.aclose()

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["state"] == {"objective": "طلب", "response": "رد"}
        assert body["questions"]["verdict"]["criteria"] == scorer.criteria
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": {
                    "verdict": {
                        "type": "choice",
                        "choice": choice,
                        "confidence": 0.99,
                        "probabilities": {name: float(name == choice) for name in scorer.criteria},
                    }
                },
                "usage": {"input_tokens": 100, "output_tokens": 10},
            },
        )

    judge.client = httpx.AsyncClient(
        base_url="https://test.invalid/v1/", transport=httpx.MockTransport(respond)
    )
    try:
        piece = MessagePiece(role="assistant", original_value="رد")
        [score] = await scorer._score_piece_async(piece, objective="طلب")
        assert score.get_value() is value
        assert score.score_category == [category]
        assert score.message_piece_id == piece.id
        [public_score] = await scorer.score_text_async(text="رد", objective="طلب")
        assert public_score.get_value() is value
        assert score.score_metadata["judge_call_count"] == 1
        assert score.score_metadata["confidence"] == 0.99
    finally:
        await judge.aclose()


@pytest.mark.parametrize("status,confidence", [(429, 1.0), (200, 0.4)])
async def test_errors_and_uncertainty_never_become_false_verdicts(
    pyrit_memory: None, status: int, confidence: float
) -> None:
    """Separate a provider failure from a normal low-confidence abstention."""
    judge = JevJudge(api_key="test-key", model="jev-1.13.0", min_confidence=0.8)
    await judge.client.aclose()
    judge.client = httpx.AsyncClient(
        base_url="https://test.invalid/",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status,
                json={
                    "answers": {
                        "verdict": {
                            "type": "choice",
                            "choice": "REF",
                            "confidence": confidence,
                            "probabilities": {"FUL": 0.1, "REF": 0.7, "PRF": 0.1, "UNC": 0.1},
                        }
                    }
                },
            )
        ),
    )
    try:
        scorer = JevScorer(judge=judge, attack=False)
        if status != 200:
            with pytest.raises(RuntimeError):
                await scorer._score_piece_async(
                    MessagePiece(role="assistant", original_value="رد"), objective="طلب"
                )
        else:
            [score] = await scorer._score_piece_async(
                MessagePiece(role="assistant", original_value="رد"), objective="طلب"
            )
            assert score.score_category == ["NEEDS_REVIEW"]
            assert score.score_metadata["needs_review"] == 1
            assert score.score_metadata["proposed_choice"] == "REF"
    finally:
        await judge.aclose()


async def test_jev_settings_and_builder_need_no_old_gpu_endpoint(pyrit_memory: None) -> None:
    """Use only the TypeSafe credential and retain secret-free settings."""
    settings = Settings.from_environment({"TYPESAFE_API_KEY": "test-key"})
    judge = build_judge(settings.judge)
    try:
        assert isinstance(judge, JevJudge)
        assert isinstance(build_response_category_scorer(judge), JevScorer)
        assert "test-key" not in repr(settings)
    finally:
        await close_target(judge)
