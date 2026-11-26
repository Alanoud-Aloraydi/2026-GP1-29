"""Persist the prompt generator's cards, prompts, outcomes and lessons.

Storage is append-only: a stored prompt and its outcome are never rewritten,
and storing the same prompt text or the same outcome twice keeps the first
one, so re-running a round can never inflate a rate. Every domain record's
field names are the column names of its row, which is what lets one insert
and one mapper serve all four records.
"""

import hashlib
from dataclasses import fields
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from harass.application.ports.generation import GenerationStore
from harass.domain.generation.history import (
    GeneratedPrompt,
    GenerationHistory,
    Lesson,
    PromptOutcome,
)
from harass.domain.generation.pattern_card import Card
from harass.domain.taxonomy import ResponseCategory
from harass.infrastructure.persistence.session_factory import SessionFactory
from harass.infrastructure.persistence.tables import (
    Base,
    GeneratorCardRow,
    GeneratorLessonRow,
    GeneratorOutcomeRow,
    GeneratorPromptRow,
)
from harass.infrastructure.persistence.upsert import insert_for


class SqlAlchemyGenerationStore(GenerationStore):
    """Keep every generated prompt, card, outcome and lesson exactly once."""

    def __init__(self, factory: SessionFactory) -> None:
        """Bind the session factory."""
        self._factory = factory

    def history(self, target_model: str) -> GenerationHistory:
        """Read every prompt with its outcome on one target, and the lessons."""
        with self._factory() as session:
            prompts = session.scalars(
                select(GeneratorPromptRow).order_by(GeneratorPromptRow.created_at)
            ).all()
            outcomes = session.scalars(
                select(GeneratorOutcomeRow).where(GeneratorOutcomeRow.target_model == target_model)
            ).all()
            lessons = session.scalars(select(GeneratorLessonRow)).all()
        return GenerationHistory(
            target_model=target_model,
            prompts=tuple(_record(GeneratedPrompt, row) for row in prompts),
            outcomes={row.prompt_id: _outcome(row) for row in outcomes},
            lessons=tuple(_record(Lesson, row) for row in lessons),
        )

    def cards(self) -> list[Card]:
        """Read every stored pattern card in identifier order."""
        with self._factory() as session:
            rows = session.scalars(select(GeneratorCardRow).order_by(GeneratorCardRow.card_id))
            return [_record(Card, row) for row in rows]

    def add_prompt(self, prompt: GeneratedPrompt) -> None:
        """Store one prompt, keeping an earlier one with the same sent text."""
        self._insert(
            GeneratorPromptRow,
            ("content_sha256",),
            {
                **vars(prompt),
                "reviewer_notes": dict(prompt.reviewer_notes),
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


def _outcome(row: GeneratorOutcomeRow) -> PromptOutcome:
    """Map a stored outcome row back, restoring its taxonomy category."""
    return PromptOutcome(
        prompt_id=str(row.prompt_id),
        target_model=row.target_model,
        response_category=ResponseCategory(row.response_category),
    )


def _record[RecordT](record_type: type[RecordT], row: Base) -> RecordT:
    """Build one domain record from the row columns its fields name."""
    return record_type(**{field.name: getattr(row, field.name) for field in fields(record_type)})  # type: ignore[arg-type]
