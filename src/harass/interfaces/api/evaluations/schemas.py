"""Validate evaluation selections and lifecycle response fields."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from harass.application.evaluation.contracts import MAX_PROMPTS_PER_ROUND, MAX_ROUNDS
from harass.domain.taxonomy import ArabicVariety, Axis, BypassStrategy, RiskCategory, SubjectDomain


class SelectionModel(BaseModel):
    """Optional filters over the dataset for a run."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    axis: Axis | None = None
    subject_domains: list[SubjectDomain] = Field(default_factory=list)
    risk_categories: list[RiskCategory] = Field(default_factory=list)
    varieties: list[ArabicVariety] = Field(default_factory=list)
    strategies: list[BypassStrategy] = Field(default_factory=list)


class AgenticModel(BaseModel):
    """The rounds, prompt count and adapter of an agentic run."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    rounds: int = Field(default=3, ge=1, le=MAX_ROUNDS)
    prompts_per_round: int = Field(default=20, ge=1, le=MAX_PROMPTS_PER_ROUND)
    transform_names: list[str] = Field(default_factory=list, max_length=8)


class RunRequest(BaseModel):
    """What a client chooses when starting a run.

    A baseline run sends the selected dataset cases; an agentic run writes its
    own prompts on the selected axis, both when none, in the selected varieties.
    """

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    connection_id: str
    kind: Literal["baseline", "agentic"] = "baseline"
    selection: SelectionModel = Field(default_factory=SelectionModel)
    max_base_cases_per_axis: int | None = Field(default=None, ge=1)
    sampling_seed: int = 0
    agentic: AgenticModel = Field(default_factory=AgenticModel)


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
    resumable: bool = False
    started_at: datetime | None = None
    lifecycle_events: list[dict[str, str]] = Field(default_factory=list)
    worker_available: bool | None = None
    kind: str = "baseline"
    awaits_run_id: str | None = None
