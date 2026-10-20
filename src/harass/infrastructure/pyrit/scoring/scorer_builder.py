"""Assembly of HARASS's Jev decision scorers from the existing rubric files."""

from pathlib import Path

from harass.infrastructure.pyrit.scoring.jev_scorer import JevJudge, JevScorer

RUBRIC_DIRECTORY = Path(__file__).parent / "rubrics"


def build_response_category_scorer(judge: JevJudge) -> JevScorer:
    """Classify responses; true means partial or full refusal."""
    return JevScorer(judge=judge, attack=False)


def build_attack_success_scorer(judge: JevJudge) -> JevScorer:
    """Judge the requested harmful behavior rather than general compliance."""
    return JevScorer(judge=judge, attack=True)
