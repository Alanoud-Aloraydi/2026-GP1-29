"""Generated prompt content and reproducible defect observations."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from harass.infrastructure.persistence.tables.base import ENTITY_ID, Base


class GeneratedPromptRow(Base):
    """Exact generated text, separate from the human-authored dataset."""

    __tablename__ = "generated_prompts"
    content_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PromptFindingRow(Base):
    """Persist a scored defect and reproducible research evidence."""

    __tablename__ = "prompt_findings"
    __table_args__ = (
        UniqueConstraint("run_id", "case_id", "variant_id", "attempt_number"),
    )
    finding_id: Mapped[str] = mapped_column(ENTITY_ID, primary_key=True)
    content_sha256: Mapped[str] = mapped_column(
        String(64), ForeignKey("generated_prompts.content_sha256"), index=True
    )
    run_id: Mapped[str] = mapped_column(
        ENTITY_ID, ForeignKey("runs.run_id"), index=True
    )
    case_id: Mapped[str] = mapped_column(String(128))
    variant_id: Mapped[str] = mapped_column(Text)
    attempt_number: Mapped[int] = mapped_column(Integer)
    axis: Mapped[str] = mapped_column(String(2))
    target_model: Mapped[str] = mapped_column(Text)
    target_endpoint: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON)
