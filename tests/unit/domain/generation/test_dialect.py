"""Tests for the dialect marker gates."""

from harass.domain.generation.dialect import foreign_markers, formal_leakage, native_markers


def test_a_najdi_marker_is_foreign_in_a_hijazi_prompt() -> None:
    """A Najdi-only word flags when the prompt claims Hijazi."""
    assert foreign_markers("شلون أسوي هالشي", "HIJ")
    assert not foreign_markers("شلون أسوي هالشي", "NAJ")


def test_a_native_marker_is_found_for_its_own_variety() -> None:
    """A Levantine word counts as native in a Levantine prompt."""
    assert native_markers("شو بدك مني هلق", "LEV")


def test_formal_words_show_an_unlocalized_prompt() -> None:
    """A strongly formal word signals the dialect pass never happened."""
    assert formal_leakage("ماذا تريد سوف نذهب")
    assert not formal_leakage("وش تبي نروح")
