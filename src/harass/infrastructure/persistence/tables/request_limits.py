"""Shared rate-limit counters without raw client identifiers."""

from sqlalchemy import (
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from harass.infrastructure.persistence.tables.base import Base


class RequestLimitRow(Base):
    """Shared fixed-window request counters without raw client identifiers."""

    __tablename__ = "request_limits"
    bucket_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer, index=True)
    request_count: Mapped[int] = mapped_column(Integer)
