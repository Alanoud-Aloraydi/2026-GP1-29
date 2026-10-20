"""Rubric invariants for Jev; network/score contracts are in test_jev_scorer."""

from pyrit.score import ContentClassifier

from harass.domain.taxonomy import ResponseCategory
from harass.infrastructure.pyrit.scoring.scorer_builder import RUBRIC_DIRECTORY


def test_rubric_categories_match_domain() -> None:
    """The evaluator and persisted domain agree on the same category codes."""
    classifier = ContentClassifier.from_yaml(RUBRIC_DIRECTORY / "response_categories.yaml")
    assert {row.name for row in classifier.categories} == {row.value for row in ResponseCategory}


def test_caveat_alone_is_not_refusal() -> None:
    """Retain the original refusal taxonomy rather than broadening its meaning."""
    classifier = ContentClassifier.from_yaml(RUBRIC_DIRECTORY / "response_categories.yaml")
    descriptions = {row.name: row.description for row in classifier.categories}
    assert "safety caveats or disclaimers is full compliance" in descriptions["FUL"]
    assert "no refusal is never" in descriptions["PRF"]
    assert "not a refusal" in descriptions["REF"]
