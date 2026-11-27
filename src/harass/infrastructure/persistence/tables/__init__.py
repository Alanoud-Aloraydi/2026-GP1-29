"""Register all ORM mappings against one shared metadata collection."""

from harass.infrastructure.persistence.tables.accounts import (
    AccountActionRow,
    AuthenticationSessionRow,
    RequestLimitRow,
    UserRow,
)
from harass.infrastructure.persistence.tables.base import ENTITY_ID, Base
from harass.infrastructure.persistence.tables.connections import ConnectionRow
from harass.infrastructure.persistence.tables.evaluations import (
    ReportRow,
    RunJobRow,
    RunOutcomeRow,
    RunRow,
    WorkerPresenceRow,
    WorkerSlotRow,
)
from harass.infrastructure.persistence.tables.generation import (
    GeneratorCardRow,
    GeneratorLessonRow,
    GeneratorOutcomeRow,
    GeneratorPromptRow,
)
from harass.infrastructure.persistence.tables.judge_reports import JudgeBenchmarkReportRow

__all__ = [
    "ENTITY_ID",
    "AccountActionRow",
    "AuthenticationSessionRow",
    "Base",
    "ConnectionRow",
    "GeneratorCardRow",
    "GeneratorLessonRow",
    "GeneratorOutcomeRow",
    "GeneratorPromptRow",
    "JudgeBenchmarkReportRow",
    "ReportRow",
    "RequestLimitRow",
    "RunJobRow",
    "RunOutcomeRow",
    "RunRow",
    "UserRow",
    "WorkerPresenceRow",
    "WorkerSlotRow",
]
