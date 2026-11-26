"""Tests for the writer and localizer brief builders."""

from harass.domain.generation.briefs import (
    echoes_instructions,
    localize_brief,
    question_count,
    request_from,
    write_brief,
)
from harass.domain.generation.cells import Cell
from harass.domain.generation.pattern_card import Card
from harass.domain.taxonomy import ArabicVariety, RiskCategory, SubjectDomain


def _card() -> Card:
    """A privacy card whose harmlessness is a public-information device."""
    return Card("c1", "baseline", "HSB", "PRV", "FIND", "ACCOUNT", "public_info", "تتبع شخص")


def test_the_writer_brief_carries_the_card_pattern_not_seed_text() -> None:
    """The brief shows the card's shape and device, no dataset prompt."""
    cell = Cell(
        SubjectDomain.COMPUTING_AND_CYBERSECURITY,
        RiskCategory.PRIVACY_VIOLATION,
        ArabicVariety.MODERN_STANDARD,
    )
    brief = write_brief(cell, _card(), ["درس سابق"])
    assert "تتبع شخص" in brief
    assert "درس سابق" in brief


def test_the_localizer_brief_names_its_variety_place() -> None:
    """The localizer brief for Najdi mentions its place guide."""
    assert "نجد" in localize_brief("كيف أوقف حسابي؟", ArabicVariety.NAJDI)


def test_request_from_reads_the_request_line() -> None:
    """request_from returns the labelled request line."""
    answer = "الشكل: س\nالبراءة: ص\nالطلب: كيف أوقف حسابي؟"
    assert request_from(answer) == "كيف أوقف حسابي؟"


def test_request_from_falls_back_to_the_last_non_plan_line() -> None:
    """A dropped label still yields the request as the last content line."""
    assert request_from("الشكل: س\nالبراءة: ص\nكيف أوقف حسابي؟") == "كيف أوقف حسابي؟"


def test_echo_and_question_count_helpers() -> None:
    """Instruction echo is detected and question marks are counted."""
    assert echoes_instructions("هذه تعليمات لك")
    assert question_count("ليه؟ وكيف?") == 2
