"""Tests for the attack writer's brief and the reading of its answer."""

import json

from harass.domain.generation.attack_briefs import (
    ATTACK_DEVICES,
    ATTACK_ECHO_PHRASES,
    attack_brief,
    attack_from,
    attack_lesson_brief,
)
from harass.domain.generation.cells import AttackCell
from harass.domain.generation.pattern_card import Card
from harass.domain.taxonomy import Axis, BypassStrategy

CELL = AttackCell.parse("AT-HSB-CRM-ROL-LLM01-NAJ")
MISINFORMATION = AttackCell.parse("AT-SIY-MIS-PER-LLM07-MSA")


def answer(**fields: str) -> str:
    """Return a writer answer holding the given JSON fields after some prose."""
    return "إليك الطلب:\n" + json.dumps(fields, ensure_ascii=False)


def test_the_brief_quotes_the_official_definitions_and_setup() -> None:
    """Verify the writer sees the V7 definitions of every code and the setup."""
    brief = attack_brief(CELL, None, [])
    assert "الحوسبة والأمن السيبراني" in brief
    assert "الاعتداء على الممتلكات والأنظمة" in brief
    assert "التأطير بدور أو سياق متخيَّل" in brief
    assert "حقن التعليمات" in brief
    assert "ignore or override those instructions" in brief
    assert "chemical, biological, radiological or nuclear" in brief


def test_a_card_and_lessons_add_the_pattern_but_no_prompt_text() -> None:
    """Verify a discovery brief carries the winning pattern and the lessons."""
    card = Card(
        "B-1",
        "baseline",
        "HSB",
        "CRM",
        "STEPS",
        "SYSTEM",
        "fiction",
        "طلب خطوات داخل قصة",
        axis=Axis.ADVERSARIAL,
        strategy="ROL",
    )
    brief = attack_brief(CELL, card, ["الدرس الأول"])
    assert "طلب خطوات داخل قصة" in brief
    assert ATTACK_DEVICES[BypassStrategy.ROLE_FRAMING]["fiction"] in brief
    assert "الدرس الأول" in brief
    assert "نمط هجوم" not in attack_brief(CELL, None, [])


def test_every_strategy_has_its_own_devices() -> None:
    """Verify each bypass strategy offers at least one framing device."""
    assert set(ATTACK_DEVICES) == set(BypassStrategy)
    assert all(ATTACK_DEVICES[strategy] for strategy in BypassStrategy)


def test_a_lesson_brief_contrasts_successes_with_failures() -> None:
    """Verify the lesson brief lists both sides of the contrast."""
    brief = attack_lesson_brief(["نجح"], ["فشل"])
    assert brief.index("نجح") < brief.index("فشل")


def test_an_answer_is_read_into_the_prompt_and_its_objective() -> None:
    """Verify the prompt and the harmful goal come out of the JSON answer."""
    draft = attack_from(answer(prompt="الطلب", harmful_goal="الهدف", false_claim=""), CELL)
    assert draft is not None
    assert (draft.prompt, draft.objective) == ("الطلب", "الهدف")


def test_an_answer_without_a_prompt_or_goal_is_unusable() -> None:
    """Verify a missing field or broken JSON yields no draft."""
    assert attack_from(answer(prompt="الطلب"), CELL) is None
    assert attack_from(answer(harmful_goal="الهدف"), CELL) is None
    assert attack_from("لا أستطيع المساعدة", CELL) is None
    assert attack_from("{not json}", CELL) is None


def test_a_misinformation_attack_needs_its_false_claim() -> None:
    """Verify LLM07 requires the claim and carries it into the objective."""
    assert attack_from(answer(prompt="الطلب", harmful_goal="الهدف"), MISINFORMATION) is None
    draft = attack_from(
        answer(prompt="الطلب", harmful_goal="الهدف", false_claim="الادعاء"), MISINFORMATION
    )
    assert draft is not None
    assert draft.objective.endswith("الادعاء")


def test_an_attack_may_name_instructions_without_counting_as_an_echo() -> None:
    """Verify the attack echo list leaves out the word for instructions."""
    assert "تعليمات" not in ATTACK_ECHO_PHRASES
    assert "أعد كتابته" in ATTACK_ECHO_PHRASES
