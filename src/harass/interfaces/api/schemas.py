"""Pydantic request and response models for the HTTP API.

These models live in the interface layer; the application and domain layers never import
pydantic. API keys appear only in requests, never in any response.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from harass.domain.prompt_variant import EvaluationMode
from harass.domain.taxonomy import ArabicVariety, Axis, BypassStrategy, RiskCategory, SubjectDomain


class ConnectionRequest(BaseModel):
    """Details a client submits to add or update a model connection."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    base_url: str = Field(min_length=1, max_length=2048)
    model_name: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, repr=False, min_length=1, max_length=8192)
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


class SelectionModel(BaseModel):
    """Optional filters over the dataset for a run."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    axis: Axis | None = None
    subject_domains: list[SubjectDomain] = Field(default_factory=list)
    risk_categories: list[RiskCategory] = Field(default_factory=list)
    varieties: list[ArabicVariety] = Field(default_factory=list)
    strategies: list[BypassStrategy] = Field(default_factory=list)


class RunRequest(BaseModel):
    """What a client chooses when starting a run."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    connection_id: str
    run_type: Literal["baseline", "agentic"] | None = None
    selection: SelectionModel = Field(default_factory=SelectionModel)
    include_baseline: bool = True
    max_base_cases_per_axis: int | None = None
    sampling_seed: int = 0
    template_names: list[str] | None = None
    transform_names: list[str] | None = None
    evaluation_mode: EvaluationMode = EvaluationMode.ADAPTIVE
    attempt_budget: int = Field(default=8, ge=1, le=100)


class RunResponse(BaseModel):
    """The lifecycle view of a run."""

    run_id: str
    connection_id: str
    target_model: str
    status: str
    created_at: datetime
    finished_at: datetime | None
    error: str | None
    total_cases: int = 0
    completed_cases: int = 0
    completed_attempts: int = 0
    resumable: bool = False
    started_at: datetime | None = None
    lifecycle_events: list[dict[str, str]] = Field(default_factory=list)
    worker_available: bool | None = None
