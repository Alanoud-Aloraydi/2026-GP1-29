"""Register all ORM mappings against one shared metadata collection."""

from harass.infrastructure.persistence.tables.accounts import (
    AccountActionRow,
    AuthenticationSessionRow,
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
from harass.infrastructure.persistence.tables.request_limits import (
    RequestLimitRow,
)
from harass.infrastructure.persistence.tables.research import (
    GeneratedPromptRow,
    PromptFindingRow,
)

__all__ = [
    "ENTITY_ID",
    "AccountActionRow",
    "AuthenticationSessionRow",
    "Base",
    "ConnectionRow",
    "GeneratedPromptRow",
    "PromptFindingRow",
    "ReportRow",
    "RequestLimitRow",
    "RunJobRow",
    "RunOutcomeRow",
    "RunRow",
    "UserRow",
    "WorkerPresenceRow",
    "WorkerSlotRow",
]
