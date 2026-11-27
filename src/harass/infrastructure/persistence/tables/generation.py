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
# An attack card belongs to one bypass strategy; an over-refusal card to none.
CARD_AXES = "(axis = 'OR' AND strategy IS NULL) OR (axis = 'AT' AND strategy IS NOT NULL)"
LESSON_SCOPES = "scope IN ('cell', 'group')"
RESPONSE_CATEGORIES = "response_category IN ('FUL', 'PRF', 'REF', 'UNC')"
PROMPT_AXES = "axis IN ('OR', 'AT')"
# An over-refusal prompt is written from a card, which names its device; an
# attack is written from a card once its group has one, and always carries the
# objective it pursues.
PROMPT_SOURCES = (
    "(axis = 'OR' AND card_id IS NOT NULL AND device IS NOT NULL) "
    "OR (axis = 'AT' AND objective <> '' AND (card_id IS NULL) = (device IS NULL))"
)


class GeneratorCardRow(Base):
    """One abstract pattern a target failed on, which the writer draws a prompt from.

    A card read from a target's baseline run or from a generated success
    names that target; a card of the shared library names none.
    """

    __tablename__ = "generator_cards"
    __table_args__ = (
        CheckConstraint(CARD_SOURCES, name="ck_generator_cards_source"),
        CheckConstraint(CARD_AXES, name="ck_generator_cards_axis"),
    )

    card_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source: Mapped[str] = mapped_column(String(16))
    axis: Mapped[str] = mapped_column(String(2))
    domain: Mapped[str] = mapped_column(String(3))
    risk: Mapped[str] = mapped_column(String(3))
    strategy: Mapped[str | None] = mapped_column(String(3))
    form: Mapped[str] = mapped_column(String(16))
    target: Mapped[str] = mapped_column(String(16))
    device: Mapped[str] = mapped_column(String(32))
    shape: Mapped[str] = mapped_column(Text)
    target_model: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GeneratorPromptRow(Base):
    """One generated prompt of either axis, with the text of every stage.

    ``target_model`` is the model it was written against, ``run_id`` the
    agentic run that wrote it, if any, and ``lesson_ids`` the lessons its
    writer read.
    """

    __tablename__ = "generator_prompts"
    __table_args__ = (
        CheckConstraint("round_index >= 0", name="ck_generator_prompts_round"),
        CheckConstraint("attempts >= 1", name="ck_generator_prompts_attempts"),
        CheckConstraint(PROMPT_AXES, name="ck_generator_prompts_axis"),
        CheckConstraint(PROMPT_SOURCES, name="ck_generator_prompts_source"),
    )

    prompt_id: Mapped[str] = mapped_column(ENTITY_ID, primary_key=True)
    case_id: Mapped[str] = mapped_column(String(128))
    axis: Mapped[str] = mapped_column(String(2))
    cell_key: Mapped[str] = mapped_column(String(32))
    device: Mapped[str | None] = mapped_column(String(32))
    card_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("generator_cards.card_id", name="fk_generator_prompts_card")
    )
    round_index: Mapped[int] = mapped_column(Integer)
    written_text: Mapped[str] = mapped_column(Text)
    localized_text: Mapped[str] = mapped_column(Text)
    sent_text: Mapped[str] = mapped_column(Text)
    objective: Mapped[str] = mapped_column(Text)
    transform_names: Mapped[list[str]] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    reviewer_passed: Mapped[bool] = mapped_column(Boolean)
    reviewer_notes: Mapped[dict[str, str]] = mapped_column(JSON)
    intent_safe: Mapped[bool] = mapped_column(Boolean)
    attempts: Mapped[int] = mapped_column(Integer)
    target_model: Mapped[str] = mapped_column(String(200))
    run_id: Mapped[str | None] = mapped_column(
        ENTITY_ID, ForeignKey("runs.run_id", name="fk_generator_prompts_run")
    )
    lesson_ids: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GeneratorOutcomeRow(Base):
    """How one target model answered one generated prompt, and why it was judged so."""

    __tablename__ = "generator_outcomes"
    __table_args__ = (CheckConstraint(RESPONSE_CATEGORIES, name="ck_generator_outcomes_category"),)

    prompt_id: Mapped[str] = mapped_column(
        ENTITY_ID,
        ForeignKey("generator_prompts.prompt_id", name="fk_generator_outcomes_prompt"),
        primary_key=True,
    )
    target_model: Mapped[str] = mapped_column(String(200), primary_key=True)
    response_category: Mapped[str] = mapped_column(String(3))
    attack_succeeded: Mapped[bool | None] = mapped_column(Boolean)
    response_text: Mapped[str] = mapped_column(Text)
    category_rationale: Mapped[str] = mapped_column(Text)
    attack_rationale: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GeneratorLessonRow(Base):
    """One abstract lesson the librarian distilled on one axis from one target.

    How well a lesson worked is read from the prompts that cite it, so the
    row stores no counts that could drift from them.
    """

    __tablename__ = "generator_lessons"
    __table_args__ = (
        CheckConstraint(LESSON_SCOPES, name="ck_generator_lessons_scope"),
        CheckConstraint(PROMPT_AXES, name="ck_generator_lessons_axis"),
    )

    lesson_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    axis: Mapped[str] = mapped_column(String(2))
    scope: Mapped[str] = mapped_column(String(16))
    scope_key: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    target_model: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


Index("ix_generator_prompts_round", GeneratorPromptRow.round_index)
Index("ix_generator_prompts_cell", GeneratorPromptRow.cell_key)
Index("ix_generator_prompts_axis", GeneratorPromptRow.axis)
Index("ix_generator_prompts_target", GeneratorPromptRow.target_model, GeneratorPromptRow.axis)
Index("ix_generator_prompts_run", GeneratorPromptRow.run_id)
Index("ix_generator_cards_target", GeneratorCardRow.target_model)
Index(
    "ix_generator_lessons_scope",
    GeneratorLessonRow.scope,
    GeneratorLessonRow.scope_key,
    GeneratorLessonRow.target_model,
)
