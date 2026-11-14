"""Tests for the rubric wording shared by the decision-model judges."""

from harass.domain.taxonomy import ResponseCategory
from harass.infrastructure.http.rubrics import (
    RUBRIC_DIRECTORY,
    load_rubrics,
    rubric_fingerprint,
)


def test_rubrics_come_from_the_shared_rubric_files() -> None:
    """Every response category and both attack verdicts are described."""
    rubrics = load_rubrics(RUBRIC_DIRECTORY)

    assert set(rubrics.categories) == {"FUL", "PRF", "REF", "UNC"}
    assert all(description for description in rubrics.categories.values())
    assert rubrics.attack_true
    assert rubrics.attack_false


def test_rubric_categories_match_the_domain_taxonomy() -> None:
    """The rubric and the domain agree on the response categories."""
    rubrics = load_rubrics(RUBRIC_DIRECTORY)

    assert set(rubrics.categories) == {
        category.value for category in ResponseCategory
    }


def test_rubric_separates_not_understanding_from_refusal() -> None:
    """Saying the text cannot be read is unclear, never a refusal."""
    categories = load_rubrics(RUBRIC_DIRECTORY).categories

    assert "not a refusal" in categories["REF"]
    assert "cannot be read or" in categories["UNC"]


def test_rubric_fingerprint_is_stable_and_names_the_prompt_version() -> None:
    """The same rubric files always give the same short fingerprint."""
    fingerprint = rubric_fingerprint()

    assert fingerprint == rubric_fingerprint()
    assert len(fingerprint) == 12
    int(fingerprint, 16)
