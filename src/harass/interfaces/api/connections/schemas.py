"""Validate model connection requests and public response fields."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConnectionRequest(BaseModel):
    """Details a client submits to add or update a model connection."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    base_url: str = Field(min_length=1, max_length=2048)
    model_name: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(
        default=None, repr=False, min_length=1, max_length=8192
    )
    api_compatibility: Literal["openai_compatible"] = "openai_compatible"
    revision: int | None = Field(default=None, ge=0)


class ConnectionResponse(BaseModel):
    """A stored connection, without its API key."""

    connection_id: str
    base_url: str
    model_name: str
    status: str
    failure_reason: str | None
    last_tested_at: datetime | None
    revision: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    api_compatibility: Literal["openai_compatible"] = "openai_compatible"
