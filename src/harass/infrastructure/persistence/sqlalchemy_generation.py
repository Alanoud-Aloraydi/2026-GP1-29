"""Persist the prompt generator's cards, prompts, outcomes and lessons.

Storage is append-only: a stored prompt and its outcome are never rewritten,
and storing the same prompt text or the same outcome twice keeps the first
one, so re-running a round can never inflate a rate. Every domain record's
field names are the column names of its row, which is what lets one insert
and one mapper serve all four records. An agentic run's report reads its
prompts back here, a bounded page at a time.
"""

import hashlib
from collections.abc import Iterator
from dataclasses import fields, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from harass.application.errors import UnknownRunError
from harass.application.ports.generation import GeneratedEvidence, GenerationStore
from harass.domain.generation.history import (
    GeneratedPrompt,
    GenerationHistory,
    Lesson,
    PromptOutcome,
)
from harass.domain.generation.pattern_card import Card
from harass.domain.taxonomy import Axis, ResponseCategory
from harass.infrastructure.persistence.session_factory import SessionFactory
from harass.infrastructure.persistence.tables import (
    Base,
    GeneratorCardRow,
    GeneratorLessonRow,
    GeneratorOutcomeRow,
    GeneratorPromptRow,
    RunRow,
)
from harass.infrastructure.persistence.upsert import insert_for

EXPORT_BATCH = 100


class SqlAlchemyGenerationStore(GenerationStore):
    """Keep every generated prompt, card, outcome and lesson exactly once."""

    def __init__(self, factory: SessionFactory) -> None:
        """Bind the session factory."""
        self._factory = factory

    def history(self, target_model: str, axis: Axis) -> GenerationHistory:
        """Read one axis's prompts written for one target, their outcomes and lessons."""
        with self._factory() as session:
            prompts = session.scalars(
                select(GeneratorPromptRow)
                .where(
                    GeneratorPromptRow.axis == axis, GeneratorPromptRow.target_model == target_model
                )
                .order_by(GeneratorPromptRow.created_at, GeneratorPromptRow.prompt_id)
            ).all()
            outcomes = session.scalars(
                select(GeneratorOutcomeRow)
                .join(GeneratorPromptRow)
                .where(
                    GeneratorOutcomeRow.target_model == target_model,
                    GeneratorPromptRow.axis == axis,
                )
            ).all()
            lessons = session.scalars(
                select(GeneratorLessonRow).where(
                    GeneratorLessonRow.axis == axis, GeneratorLessonRow.target_model == target_model
                )
            ).all()
        return GenerationHistory(
            target_model=target_model,
            axis=axis,
            prompts=tuple(_prompt(row) for row in prompts),
            outcomes={str(row.prompt_id): _outcome(row) for row in outcomes},
            lessons=tuple(replace(_record(Lesson, row), axis=Axis(row.axis)) for row in lessons),
        )

    def cards(self, target_model: str) -> list[Card]:
        """Read the shared cards and those of one target, in identifier order."""
        with self._factory() as session:
            rows = session.scalars(
                select(GeneratorCardRow)
                .where(
                    or_(
                        GeneratorCardRow.target_model.is_(None),
                        GeneratorCardRow.target_model == target_model,
                    )
                )
                .order_by(GeneratorCardRow.card_id)
            )
            return [replace(_record(Card, row), axis=Axis(row.axis)) for row in rows]

    def add_prompt(self, prompt: GeneratedPrompt) -> None:
        """Store one prompt, keeping an earlier one with the same sent text."""
        self._insert(
            GeneratorPromptRow,
            ("content_sha256",),
            {
                **vars(prompt),
                "reviewer_notes": dict(prompt.reviewer_notes),
                "transform_names": list(prompt.transform_names),
                "lesson_ids": list(prompt.lesson_ids),
                "content_sha256": hashlib.sha256(prompt.sent_text.encode("utf-8")).hexdigest(),
            },
        )

    def add_outcome(self, outcome: PromptOutcome) -> None:
        """Store one target's answer, keeping that target's earlier answer."""
        self._insert(GeneratorOutcomeRow, ("prompt_id", "target_model"), vars(outcome))

    def add_lesson(self, lesson: Lesson) -> None:
        """Store one lesson, keeping an earlier lesson of the same identifier."""
        self._insert(GeneratorLessonRow, ("lesson_id",), vars(lesson))

    def add_card(self, card: Card) -> None:
        """Store one card, keeping an earlier card of the same identifier."""
        self._insert(GeneratorCardRow, ("card_id",), vars(card))

    def _insert(self, row_type: type[Base], keys: tuple[str, ...], values: dict[str, Any]) -> None:
        """Insert one row, keeping any row that already holds those keys."""
        with self._factory() as session, session.begin():
            session.execute(
                insert_for(session, row_type)
                .values(created_at=datetime.now(UTC), **values)
                .on_conflict_do_nothing(index_elements=list(keys))
            )


class SqlAlchemyGeneratedEvidence(GeneratedEvidence):
    """Read an owned agentic run's prompts with the target's replies."""

    def __init__(self, factory: SessionFactory) -> None:
        """Bind the session factory."""
        self._factory = factory

    def prompt_page(self, run_id: str, owner_id: str, offset: int, limit: int) -> dict[str, Any]:
        """Return one page of the run's prompts in writing order, and their total.

        Raises:
            ValueError: If the page bounds are out of range.
            UnknownRunError: If the owner has no such run.
        """
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("Evidence pages require offset >= 0 and limit 1-100.")
        with self._factory() as session:
            target_model = _owned_target(session, run_id, owner_id)
            total = session.scalar(
                select(func.count())
                .select_from(GeneratorPromptRow)
                .where(GeneratorPromptRow.run_id == run_id)
            )
            rows = session.execute(
                _evidence_query(run_id, target_model).offset(offset).limit(limit)
            ).all()
            return {
                "offset": offset,
                "limit": limit,
                "total": total or 0,
                "items": [_evidence(prompt, outcome) for prompt, outcome in rows],
            }

    def prompt_documents(self, run_id: str, owner_id: str) -> Iterator[dict[str, Any]]:
        """Stream every prompt of the run in bounded batches."""
        with self._factory() as session:
            target_model = _owned_target(session, run_id, owner_id)
        offset = 0
        while True:
            with self._factory() as session:
                rows = session.execute(
                    _evidence_query(run_id, target_model).offset(offset).limit(EXPORT_BATCH)
                ).all()
            if not rows:
                return
            offset += len(rows)
            for prompt, outcome in rows:
                yield _evidence(prompt, outcome)


def _owned_target(session: Session, run_id: str, owner_id: str) -> str:
    """Return the target model of an owned run.

    Raises: UnknownRunError: If the owner has no such run.
    """
    target_model = session.scalar(
        select(RunRow.target_model).where(RunRow.run_id == run_id, RunRow.owner_id == owner_id)
    )
    if target_model is None:
        raise UnknownRunError(run_id)
    return str(target_model)


def _evidence_query(
    run_id: str, target_model: str
) -> Select[GeneratorPromptRow, GeneratorOutcomeRow]:
    """Select a run's prompts with the target's outcome, in a stable order."""
    return (
        select(GeneratorPromptRow, GeneratorOutcomeRow)
        .outerjoin(
            GeneratorOutcomeRow,
            (GeneratorOutcomeRow.prompt_id == GeneratorPromptRow.prompt_id)
            & (GeneratorOutcomeRow.target_model == target_model),
        )
        .where(GeneratorPromptRow.run_id == run_id)
        .order_by(
            GeneratorPromptRow.round_index,
            GeneratorPromptRow.axis.desc(),
            GeneratorPromptRow.created_at,
            GeneratorPromptRow.prompt_id,
        )
    )


def _evidence(prompt: GeneratorPromptRow, outcome: GeneratorOutcomeRow | None) -> dict[str, Any]:
    """Return one prompt's stages, gates and the judged reply as a document."""
    return {
        "prompt_id": str(prompt.prompt_id),
        "case_id": prompt.case_id,
        "axis": prompt.axis,
        "round": prompt.round_index,
        "cell_key": prompt.cell_key,
        "card_id": prompt.card_id,
        "device": prompt.device,
        "written_text": prompt.written_text,
        "localized_text": prompt.localized_text,
        "sent_text": prompt.sent_text,
        "objective": prompt.objective,
        "transform_names": list(prompt.transform_names),
        "reviewer_passed": prompt.reviewer_passed,
        "reviewer_notes": dict(prompt.reviewer_notes),
        "intent_safe": prompt.intent_safe,
        "attempts": prompt.attempts,
        "lesson_ids": list(prompt.lesson_ids),
        "outcome": None
        if outcome is None
        else {
            "response_category": outcome.response_category,
            "attack_succeeded": outcome.attack_succeeded,
            "response_text": outcome.response_text,
            "category_rationale": outcome.category_rationale,
            "attack_rationale": outcome.attack_rationale,
        },
    }


def _prompt(row: GeneratorPromptRow) -> GeneratedPrompt:
    """Map a stored prompt row back, restoring its axis, run and tuples."""
    prompt = _record(GeneratedPrompt, row)
    return replace(
        prompt,
        prompt_id=str(row.prompt_id),
        axis=Axis(row.axis),
        transform_names=tuple(row.transform_names),
        lesson_ids=tuple(row.lesson_ids),
        run_id=str(row.run_id) if row.run_id else None,
    )


def _outcome(row: GeneratorOutcomeRow) -> PromptOutcome:
    """Map a stored outcome row back, restoring its taxonomy category."""
    outcome = _record(PromptOutcome, row)
    return replace(
        outcome,
        prompt_id=str(row.prompt_id),
        response_category=ResponseCategory(row.response_category),
    )


def _record[RecordT](record_type: type[RecordT], row: Base) -> RecordT:
    """Build one domain record from the row columns its fields name."""
    return record_type(**{field.name: getattr(row, field.name) for field in fields(record_type)})  # type: ignore[arg-type]
