"""Tests for the append-only storage of the prompt generator."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from harass.application.errors import UnknownRunError
from harass.application.evaluation.contracts import RunParameters
from harass.domain.case_selection import CaseSelection
from harass.domain.evaluation_run import EvaluationRun, RunKind, RunStatus
from harass.domain.generation.history import (
    CELL_SCOPE,
    GROUP_SCOPE,
    GeneratedPrompt,
    Lesson,
    PromptOutcome,
)
from harass.domain.generation.pattern_card import Card
from harass.domain.taxonomy import Axis, ResponseCategory
from harass.infrastructure.persistence.row_mapping import new_run_row
from harass.infrastructure.persistence.sqlalchemy_generation import (
    SqlAlchemyGeneratedEvidence,
    SqlAlchemyGenerationStore,
)
from harass.infrastructure.persistence.sqlalchemy_runs import SqlAlchemyRunStore
from harass.infrastructure.persistence.tables import (
    Base,
    ConnectionRow,
    GeneratorPromptRow,
    RunJobRow,
    UserRow,
)

CELL = "OR-DIN-VIO-MSA"
TARGET = "target-model"
OTHER_TARGET = "other-model"
OWNER = "20000000-0000-4000-8000-000000000001"
STRANGER = "20000000-0000-4000-8000-000000000002"
CONNECTION = "30000000-0000-4000-8000-000000000001"
RUN = "10000000-0000-4000-8000-000000000001"
START = datetime(2026, 1, 1, tzinfo=UTC)


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


def prompt(
    prompt_id: str,
    sent_text: str = "النص المُلهَّج",
    target_model: str = TARGET,
    run_id: str | None = None,
    round_index: int = 0,
) -> GeneratedPrompt:
    """Return one generated prompt of the cell, written for one target."""
    return GeneratedPrompt(
        prompt_id=prompt_id,
        case_id="OR-DIN-VIO-MSA-00001",
        axis=Axis.OVER_REFUSAL,
        cell_key=CELL,
        device="homonym",
        card_id="C-1",
        round_index=round_index,
        written_text="النص الفصيح",
        localized_text=sent_text,
        sent_text=sent_text,
        reviewer_passed=True,
        intent_safe=True,
        reviewer_notes={"FACTS": "yes nothing invented"},
        attempts=2,
        target_model=target_model,
        run_id=run_id,
        lesson_ids=("L-1",),
    )


def test_a_stored_prompt_reads_back_whole(session_factory: sessionmaker[Session]) -> None:
    """Verify every field of a prompt survives the round trip."""
    store = SqlAlchemyGenerationStore(session_factory)
    store.add_card(card())
    store.add_prompt(prompt("11111111-1111-4111-8111-111111111111"))
    stored = store.history(TARGET, Axis.OVER_REFUSAL)
    assert stored.prompts == (prompt("11111111-1111-4111-8111-111111111111"),)
    assert store.cards(TARGET) == [card()]
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
    assert store.history(TARGET, Axis.OVER_REFUSAL).prompts == (first,)


def test_a_history_holds_only_its_own_target(session_factory: sessionmaker[Session]) -> None:
    """Verify prompts, outcomes and lessons of another target stay out of its history."""
    store = SqlAlchemyGenerationStore(session_factory)
    store.add_card(card())
    identifier = "11111111-1111-4111-8111-111111111111"
    store.add_prompt(prompt(identifier))
    store.add_prompt(prompt("22222222-2222-4222-8222-222222222222", "آخر", OTHER_TARGET))
    store.add_outcome(PromptOutcome(identifier, TARGET, ResponseCategory.FULL_REFUSAL))
    store.add_lesson(Lesson("L-2", GROUP_SCOPE, "VIO-homonym", "درس", OTHER_TARGET))
    mine = store.history(TARGET, Axis.OVER_REFUSAL)
    assert mine.successful_cells() == {CELL: 1}
    assert mine.card_results() == {"C-1": (1, 1)}
    assert [p.prompt_id for p in mine.prompts] == [identifier]
    assert mine.lessons == ()
    assert store.history(OTHER_TARGET, Axis.OVER_REFUSAL).card_results() == {}


def test_one_target_answers_a_prompt_once(session_factory: sessionmaker[Session]) -> None:
    """Verify re-scoring keeps the first answer of that target."""
    store = SqlAlchemyGenerationStore(session_factory)
    store.add_card(card())
    identifier = "11111111-1111-4111-8111-111111111111"
    store.add_prompt(prompt(identifier))
    store.add_outcome(PromptOutcome(identifier, TARGET, ResponseCategory.FULL_REFUSAL))
    store.add_outcome(PromptOutcome(identifier, TARGET, ResponseCategory.FULL_COMPLIANCE))
    outcome = store.history(TARGET, Axis.OVER_REFUSAL).outcomes[identifier]
    assert outcome.response_category is ResponseCategory.FULL_REFUSAL


def test_lessons_and_cards_are_kept_once(session_factory: sessionmaker[Session]) -> None:
    """Verify storing the same lesson or card twice changes nothing."""
    store = SqlAlchemyGenerationStore(session_factory)
    lesson = Lesson("L-1", CELL_SCOPE, CELL, "اجعل الطلب يبدو مريبًا", TARGET)
    store.add_lesson(lesson)
    store.add_lesson(Lesson("L-1", CELL_SCOPE, CELL, "نص آخر", TARGET))
    store.add_card(card())
    store.add_card(card())
    assert store.history(TARGET, Axis.OVER_REFUSAL).lessons == (lesson,)
    assert store.history(TARGET, Axis.ADVERSARIAL).lessons == ()
    assert store.cards(TARGET) == [card()]


def test_cards_are_shared_or_belong_to_one_target(session_factory: sessionmaker[Session]) -> None:
    """Verify a target reads the shared cards and its own, never another target's."""
    store = SqlAlchemyGenerationStore(session_factory)
    attack_card = Card(
        "B-2",
        "baseline",
        "HSB",
        "CRM",
        "STEPS",
        "SYSTEM",
        "persona",
        "شكل",
        axis=Axis.ADVERSARIAL,
        strategy="ROL",
        target_model=TARGET,
    )
    store.add_card(card())
    store.add_card(attack_card)
    assert store.cards(TARGET) == [attack_card, card()]
    assert store.cards(OTHER_TARGET) == [card()]


def attack(prompt_id: str) -> GeneratedPrompt:
    """Return one stored attack, transformed before it was sent."""
    return GeneratedPrompt(
        target_model=TARGET,
        prompt_id=prompt_id,
        case_id="AT-HSB-CRM-OBF-NAP-MSA-00001",
        axis=Axis.ADVERSARIAL,
        cell_key="AT-HSB-CRM-OBF-NAP-MSA",
        round_index=0,
        written_text="الهجوم الفصيح",
        localized_text="الهجوم الفصيح",
        sent_text="الهجوم المرمّز",
        reviewer_passed=True,
        intent_safe=False,
        objective="الهدف الضار",
        transform_names=("base64",),
    )


def test_an_attack_and_its_judged_reply_read_back_on_their_own_axis(
    session_factory: sessionmaker[Session],
) -> None:
    """Verify an attack keeps every stage and its reply, apart from over-refusal."""
    store = SqlAlchemyGenerationStore(session_factory)
    store.add_card(card())
    identifier = "33333333-3333-4333-8333-333333333333"
    store.add_prompt(attack(identifier))
    store.add_prompt(prompt("44444444-4444-4444-8444-444444444444"))
    judged = PromptOutcome(
        identifier,
        TARGET,
        ResponseCategory.FULL_COMPLIANCE,
        attack_succeeded=True,
        response_text="الرد",
        category_rationale="تعليل",
        attack_rationale="تعليل النجاح",
    )
    store.add_outcome(judged)
    attacks = store.history(TARGET, Axis.ADVERSARIAL)
    assert attacks.prompts == (attack(identifier),)
    assert attacks.outcomes[identifier] == judged
    assert len(store.history(TARGET, Axis.OVER_REFUSAL).prompts) == 1


def add_run(
    factory: sessionmaker[Session],
    run_id: str,
    kind: RunKind,
    hours: int,
    status: RunStatus = RunStatus.COMPLETED,
    axis: Axis | None = None,
) -> None:
    """Store one run of the owner on the connection, created ``hours`` after the start."""
    created = START + timedelta(hours=hours)
    finished = created if status is RunStatus.COMPLETED else None
    with factory.begin() as session:
        session.add(
            new_run_row(
                EvaluationRun(
                    run_id,
                    OWNER,
                    CONNECTION,
                    TARGET,
                    status,
                    created,
                    finished_at=finished,
                    kind=kind,
                )
            )
        )
        session.flush()
        session.add(
            RunJobRow(
                run_id=run_id,
                parameters=RunParameters(CaseSelection(axis=axis)).document(),
                target_endpoint="https://api.invalid/v1",
                execution_profile="test",
                checkpoint={},
                revision=0,
            )
        )


@pytest.fixture
def owned(session_factory: sessionmaker[Session]) -> sessionmaker[Session]:
    """Store an owner and their connection, which runs refer to."""
    with session_factory.begin() as session:
        for owner in (OWNER, STRANGER):
            session.add(
                UserRow(
                    user_id=owner,
                    full_name="Test",
                    email=f"{owner[-1]}@example.test",
                    password_hash="test-only",
                )
            )
        session.flush()
        session.add(
            ConnectionRow(
                connection_id=CONNECTION,
                owner_id=OWNER,
                base_url="https://api.invalid/v1",
                model_name=TARGET,
                status="connected",
                encrypted_api_key="test-only",
            )
        )
    return session_factory


def test_baselines_are_listed_newest_first_with_their_axis(owned: sessionmaker[Session]) -> None:
    """Verify only baselines that completed or may still complete are listed."""
    runs = SqlAlchemyRunStore(owned)
    assert runs.baselines(OWNER, CONNECTION) == []
    older, newer, cancelled = (
        "10000000-0000-4000-8000-000000000002",
        "10000000-0000-4000-8000-000000000003",
        "10000000-0000-4000-8000-000000000004",
    )
    add_run(owned, older, RunKind.BASELINE, 1)
    add_run(owned, newer, RunKind.BASELINE, 2, RunStatus.PENDING, Axis.OVER_REFUSAL)
    add_run(owned, cancelled, RunKind.BASELINE, 3, RunStatus.CANCELLED)
    add_run(owned, RUN, RunKind.AGENTIC, 4)
    listed = [(run.run_id, run.status, axis) for run, axis in runs.baselines(OWNER, CONNECTION)]
    assert listed == [
        (newer, RunStatus.PENDING, Axis.OVER_REFUSAL),
        (older, RunStatus.COMPLETED, None),
    ]
    assert runs.baselines(STRANGER, CONNECTION) == []
    assert runs.get(RUN, OWNER).kind is RunKind.AGENTIC


def test_a_run_pages_its_prompts_with_the_replies(owned: sessionmaker[Session]) -> None:
    """Verify an agentic run's evidence is its own prompts, in round order."""
    add_run(owned, RUN, RunKind.AGENTIC, 1)
    store = SqlAlchemyGenerationStore(owned)
    store.add_card(card())
    later = "11111111-1111-4111-8111-111111111111"
    first = "22222222-2222-4222-8222-222222222222"
    store.add_prompt(prompt(later, "ثانية", run_id=RUN, round_index=1))
    store.add_prompt(prompt(first, "أولى", run_id=RUN))
    store.add_prompt(prompt("33333333-3333-4333-8333-333333333333", "خارج التشغيل"))
    store.add_outcome(
        PromptOutcome(first, TARGET, ResponseCategory.FULL_REFUSAL, response_text="لا")
    )
    evidence = SqlAlchemyGeneratedEvidence(owned)
    page = evidence.prompt_page(RUN, OWNER, 0, 1)
    assert (page["total"], len(page["items"])) == (2, 1)
    [item] = page["items"]
    assert (item["prompt_id"], item["sent_text"], item["lesson_ids"]) == (first, "أولى", ["L-1"])
    assert item["outcome"]["response_text"] == "لا"
    exported = list(evidence.prompt_documents(RUN, OWNER))
    assert [entry["prompt_id"] for entry in exported] == [first, later]
    assert exported[1]["outcome"] is None


def test_another_owner_cannot_read_a_run_s_prompts(owned: sessionmaker[Session]) -> None:
    """Verify a run's prompts are hidden from every other owner."""
    add_run(owned, RUN, RunKind.AGENTIC, 1)
    evidence = SqlAlchemyGeneratedEvidence(owned)
    with pytest.raises(UnknownRunError):
        evidence.prompt_page(RUN, STRANGER, 0, 10)
    with pytest.raises(UnknownRunError):
        list(evidence.prompt_documents(RUN, STRANGER))
    with pytest.raises(ValueError, match="limit"):
        evidence.prompt_page(RUN, OWNER, 0, 101)
