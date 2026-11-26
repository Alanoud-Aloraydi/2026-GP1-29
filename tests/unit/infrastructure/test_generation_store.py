"""Tests for the append-only storage of the prompt generator."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from harass.domain.generation.history import CELL_SCOPE, GeneratedPrompt, Lesson, PromptOutcome
from harass.domain.generation.pattern_card import Card
from harass.domain.taxonomy import ResponseCategory
from harass.infrastructure.persistence.sqlalchemy_generation import SqlAlchemyGenerationStore
from harass.infrastructure.persistence.tables import Base, GeneratorPromptRow

CELL = "OR-DIN-VIO-MSA"
TARGET = "target-model"
OTHER_TARGET = "other-model"


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    """Return a session factory bound to a fresh in-memory database."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine)
    engine.dispose()


def card(card_id: str = "C-1") -> Card:
    """Return one pattern card."""
    return Card(card_id, "baseline", "DIN", "VIO", "EXPLAIN", "NONE", "homonym", "شكل الطلب الضار")


def prompt(prompt_id: str, sent_text: str = "النص المُلهَّج", card_id: str = "C-1") -> GeneratedPrompt:
    """Return one generated prompt of the cell."""
    return GeneratedPrompt(
        prompt_id=prompt_id,
        case_id="OR-DIN-VIO-MSA-00001",
        cell_key=CELL,
        mechanism="homonym",
        card_id=card_id,
        round_index=0,
        written_text="النص الفصيح",
        sent_text=sent_text,
        reviewer_passed=True,
        intent_safe=True,
        reviewer_notes={"FACTS": "yes nothing invented"},
        attempts=2,
    )


def test_a_stored_prompt_reads_back_whole(session_factory: sessionmaker[Session]) -> None:
    """Verify every field of a prompt survives the round trip."""
    store = SqlAlchemyGenerationStore(session_factory)
    store.add_card(card())
    store.add_prompt(prompt("11111111-1111-4111-8111-111111111111"))
    stored = store.history(TARGET)
    assert stored.prompts == (prompt("11111111-1111-4111-8111-111111111111"),)
    assert store.cards() == [card()]
    assert stored.outcomes == {}


def test_the_same_prompt_text_is_never_stored_twice(session_factory: sessionmaker[Session]) -> None:
    """Verify an identical prompt keeps the first row and inflates nothing."""
    store = SqlAlchemyGenerationStore(session_factory)
    store.add_card(card())
    first = prompt("11111111-1111-4111-8111-111111111111")
    store.add_prompt(first)
    store.add_prompt(prompt("22222222-2222-4222-8222-222222222222"))
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(GeneratorPromptRow)) == 1
    assert store.history(TARGET).prompts == (first,)


def test_a_history_holds_only_its_own_target(session_factory: sessionmaker[Session]) -> None:
    """Verify outcomes of another target never enter this target's rates."""
    store = SqlAlchemyGenerationStore(session_factory)
    store.add_card(card())
    identifier = "11111111-1111-4111-8111-111111111111"
    store.add_prompt(prompt(identifier))
    store.add_outcome(PromptOutcome(identifier, TARGET, ResponseCategory.FULL_REFUSAL))
    store.add_outcome(PromptOutcome(identifier, OTHER_TARGET, ResponseCategory.FULL_COMPLIANCE))
    assert store.history(TARGET).refused_cells() == {CELL: 1}
    assert store.history(OTHER_TARGET).refused_cells() == {}
    assert store.history(OTHER_TARGET).card_results() == {"C-1": (0, 1)}


def test_one_target_answers_a_prompt_once(session_factory: sessionmaker[Session]) -> None:
    """Verify re-scoring keeps the first answer of that target."""
    store = SqlAlchemyGenerationStore(session_factory)
    store.add_card(card())
    identifier = "11111111-1111-4111-8111-111111111111"
    store.add_prompt(prompt(identifier))
    store.add_outcome(PromptOutcome(identifier, TARGET, ResponseCategory.FULL_REFUSAL))
    store.add_outcome(PromptOutcome(identifier, TARGET, ResponseCategory.FULL_COMPLIANCE))
    outcome = store.history(TARGET).outcomes[identifier]
    assert outcome.response_category is ResponseCategory.FULL_REFUSAL


def test_lessons_and_cards_are_kept_once(session_factory: sessionmaker[Session]) -> None:
    """Verify storing the same lesson or card twice changes nothing."""
    store = SqlAlchemyGenerationStore(session_factory)
    lesson = Lesson("L-1", CELL_SCOPE, CELL, "اجعل الطلب يبدو مريبًا", TARGET, uses=2, successes=1)
    store.add_lesson(lesson)
    store.add_lesson(Lesson("L-1", CELL_SCOPE, CELL, "نص آخر", TARGET))
    store.add_card(card())
    store.add_card(card())
    assert store.history(TARGET).lessons == (lesson,)
    assert store.cards() == [card()]
