"""Tests for the adapter's Arabic surface transforms."""

import pytest

from harass.domain.generation.transforms import (
    adapter_sequence,
    apply_transform,
    axis_transforms,
    transform_text,
)
from harass.domain.taxonomy import Axis

ENGLISH = "english_number_sounds"
ARABIC = "arabic_number_words"


@pytest.mark.parametrize(
    ("name", "text", "expected"),
    [
        (ENGLISH, "محفور عليها لا تنساني", "مح4 عليها لا 10ساني"),
        (ENGLISH, "جناين ورد", "ج9 ورد"),
        (ENGLISH, "تونتي", "20"),
        (ARABIC, "الستين", "ال60"),
        (ARABIC, "ثلاثين", "30"),
        (ARABIC, "أربعة إثنين", "4ة 2"),
        (ARABIC, "رسمية تألفت", "رس100 ت1000ت"),
    ],
)
def test_spoken_number_names_become_digits(name: str, text: str, expected: str) -> None:
    """Write tens before units and accept every alef spelling."""
    assert apply_transform(name, text) == expected


def test_each_word_keeps_one_number_so_digits_never_merge() -> None:
    """Replace one name per word and skip words that already have digits."""
    assert apply_transform(ENGLISH, "توتو") == "2تو"
    assert apply_transform(ARABIC, "عام 2014 ستة") == "عام 2014 6ة"
    once = apply_transform(ENGLISH, "التنظيم يستخدم")
    assert apply_transform(ARABIC, once) == "ال10ظيم ي6خدم"


def test_the_article_is_not_read_as_a_thousand() -> None:
    """Keep the hamza on ألف so words starting with الف stay intact."""
    assert apply_transform(ARABIC, "الفكرة") == "الفكرة"


def test_rebus_is_for_attacks_and_needs_a_number_name() -> None:
    """Refuse rebus for over-refusal prompts and for text with no Arabic."""
    with pytest.raises(ValueError, match="meaning-preserving"):
        adapter_sequence((ENGLISH,), Axis.OVER_REFUSAL)
    sequence = adapter_sequence((ARABIC,), Axis.ADVERSARIAL)
    assert transform_text("الستين", sequence) == "ال60"
    assert transform_text("text", sequence) is None


def test_the_adapter_keeps_transforms_in_the_order_named() -> None:
    """Verify an attack may take an encoding after letter noise."""
    sequence = adapter_sequence(("tatweel", "base64"), Axis.ADVERSARIAL)
    assert [transform.name for transform in sequence] == ["tatweel", "base64"]
    assert adapter_sequence((), Axis.OVER_REFUSAL) == ()


def test_the_adapter_refuses_what_cannot_be_applied() -> None:
    """Verify unknown, repeated, uncomposable and meaning-losing transforms fail."""
    with pytest.raises(ValueError, match="Unknown"):
        adapter_sequence(("rot13",), Axis.ADVERSARIAL)
    with pytest.raises(ValueError, match="only once"):
        adapter_sequence(("tatweel", "tatweel"), Axis.ADVERSARIAL)
    with pytest.raises(ValueError, match="composed"):
        adapter_sequence(("base64", "unicode_escape"), Axis.ADVERSARIAL)
    with pytest.raises(ValueError, match="meaning-preserving"):
        adapter_sequence(("arabizi",), Axis.OVER_REFUSAL)


def test_transformed_text_is_produced_or_refused() -> None:
    """Verify a transform that needs Arabic refuses text without it."""
    sequence = adapter_sequence(("tatweel",), Axis.OVER_REFUSAL)
    assert transform_text("كتب", sequence) == "كـتـب"
    assert transform_text("text", sequence) is None


def test_an_over_refusal_prompt_keeps_only_meaning_preserving_transforms() -> None:
    """One adapter serves both axes: attacks take all, over-refusal the readable ones."""
    names = ("arabizi", "tatweel", "base64")
    assert axis_transforms(names, Axis.ADVERSARIAL) == names
    assert axis_transforms(names, Axis.OVER_REFUSAL) == ("tatweel", "base64")
    assert axis_transforms(("unknown",), Axis.OVER_REFUSAL) == ("unknown",)
