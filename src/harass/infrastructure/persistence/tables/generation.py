"""Tables of the prompt generator: its cards, prompts, outcomes and lessons."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from harass.infrastructure.persistence.tables.base import ENTITY_ID, Base

CARD_SOURCES = "source IN ('baseline', 'generated')"
LESSON_SCOPES = "scope IN ('cell', 'risk_mechanism', 'risk')"
RESPONSE_CATEGORIES = "response_category IN ('FUL', 'PRF', 'REF', 'UNC')"


class GeneratorCardRow(Base):
    """One abstract refusal pattern the writer draws a new prompt from."""

    __tablename__ = "generator_cards"
    __table_args__ = (CheckConstraint(CARD_SOURCES, name="ck_generator_cards_source"),)

    card_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source: Mapped[str] = mapped_column(String(16))
    domain: Mapped[str] = mapped_column(String(3))
    risk: Mapped[str] = mapped_column(String(3))
    form: Mapped[str] = mapped_column(String(16))
    target: Mapped[str] = mapped_column(String(16))
    harmless: Mapped[str] = mapped_column(String(32))
    shape: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GeneratorPromptRow(Base):
    """One generated prompt, with the clear draft and the text that is sent."""

    __tablename__ = "generator_prompts"
    __table_args__ = (
        CheckConstraint("round_index >= 0", name="ck_generator_prompts_round"),
        CheckConstraint("attempts >= 1", name="ck_generator_prompts_attempts"),
    )

    prompt_id: Mapped[str] = mapped_column(ENTITY_ID, primary_key=True)
    case_id: Mapped[str] = mapped_column(String(128))
    cell_key: Mapped[str] = mapped_column(String(32))
    mechanism: Mapped[str] = mapped_column(String(32))
    card_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("generator_cards.card_id", name="fk_generator_prompts_card")
    )
    round_index: Mapped[int] = mapped_column(Integer)
    written_text: Mapped[str] = mapped_column(Text)
    sent_text: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    reviewer_passed: Mapped[bool] = mapped_column(Boolean)
    reviewer_notes: Mapped[dict[str, str]] = mapped_column(JSON)
    intent_safe: Mapped[bool] = mapped_column(Boolean)
    attempts: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GeneratorOutcomeRow(Base):
    """How one target model answered one generated prompt."""

    __tablename__ = "generator_outcomes"
    __table_args__ = (CheckConstraint(RESPONSE_CATEGORIES, name="ck_generator_outcomes_category"),)

    prompt_id: Mapped[str] = mapped_column(
        ENTITY_ID,
        ForeignKey("generator_prompts.prompt_id", name="fk_generator_outcomes_prompt"),
        primary_key=True,
    )
    target_model: Mapped[str] = mapped_column(String(200), primary_key=True)
    response_category: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GeneratorLessonRow(Base):
    """One abstract lesson the librarian distilled, with its use counts."""

    __tablename__ = "generator_lessons"
    __table_args__ = (
        CheckConstraint(LESSON_SCOPES, name="ck_generator_lessons_scope"),
        CheckConstraint(
            "uses >= 0 AND successes >= 0 AND successes <= uses", name="ck_generator_lessons_counts"
        ),
    )

    lesson_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    scope: Mapped[str] = mapped_column(String(16))
    scope_key: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    target_model: Mapped[str] = mapped_column(String(200))
    uses: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    successes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


Index("ix_generator_prompts_round", GeneratorPromptRow.round_index)
Index("ix_generator_prompts_cell", GeneratorPromptRow.cell_key)
Index(
    "ix_generator_lessons_scope",
    GeneratorLessonRow.scope,
    GeneratorLessonRow.scope_key,
    GeneratorLessonRow.target_model,
)
