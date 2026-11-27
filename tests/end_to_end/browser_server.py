"""Run local browser QA against real application adapters.

Run this file directly for browser QA. The synthetic verifier and model/judge
are deliberately test-only; no .env credentials or production database are
loaded.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import uvicorn
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pyrit.models import Message, construct_response_from_request
from pyrit.prompt_target import PromptTarget
from pyrit.prompt_target.common.target_capabilities import TargetCapabilities
from pyrit.prompt_target.common.target_configuration import TargetConfiguration
from pyrit.setup import IN_MEMORY, initialize_pyrit_async
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from harass.application.accounts.authentication import ManageAuthentication
from harass.application.connections import ManageConnections
from harass.application.evaluation.baseline_engine import BaselineEngine
from harass.application.evaluation.run_service import ManageRuns
from harass.application.evaluation.runner import RunEvaluation
from harass.application.evaluation.worker import ProcessRuns
from harass.application.ports.connections import ConnectionVerifier
from harass.application.ports.evaluation import SeedSource
from harass.domain.case_selection import CaseSelection
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.target_connection import TargetConnection
from harass.infrastructure.dataset.spreadsheet_seed_source import SpreadsheetSeedSource
from harass.infrastructure.persistence.sqlalchemy_authentication import (
    SqlAlchemyAuthenticationStore,
)
from harass.infrastructure.persistence.sqlalchemy_connections import SqlAlchemyConnectionStore
from harass.infrastructure.persistence.sqlalchemy_generation import SqlAlchemyGeneratedEvidence
from harass.infrastructure.persistence.sqlalchemy_jobs import SqlAlchemyRunQueue
from harass.infrastructure.persistence.sqlalchemy_runs import SqlAlchemyRunStore
from harass.infrastructure.persistence.tables import Base
from harass.infrastructure.pyrit.attempt_executor import PyritAttemptExecutor
from harass.infrastructure.pyrit.scoring.guard_scorers import (
    GuardAttackScorer,
    GuardCategoryScorer,
    GuardModerator,
)
from harass.infrastructure.security.fernet_secret_cipher import FernetSecretCipher
from harass.infrastructure.security.jwt_authentication import JwtAuthenticationSecurity
from harass.interfaces.api.app import create_app

ROOT = Path(__file__).resolve().parents[2]
REFUSAL = "رفض اصطناعي لاختبار الواجهة."


class BrowserTarget(PromptTarget):
    """Test double for browser target."""

    def __init__(self) -> None:
        """Declare the capabilities needed by the real executor."""
        super().__init__(
            custom_configuration=TargetConfiguration(
                capabilities=TargetCapabilities(
                    supports_multi_turn=True,
                    supports_editable_history=True,
                    supports_system_prompt=True,
                )
            )
        )

    async def _send_prompt_to_target_async(
        self, *, normalized_conversation: list[Message]
    ) -> list[Message]:
        request = normalized_conversation[-1].message_pieces[0]
        response = (
            REFUSAL
            if "أجب عن الطلب التالي" in request.converted_value
            else "إجابة اصطناعية محايدة."
        )
        return [construct_response_from_request(request=request, response_text_pieces=[response])]


def browser_guard(request: httpx.Request) -> httpx.Response:
    """Answer a moderation request the way the judge server does."""
    response = json.loads(request.content)["messages"][-1]["content"]
    refusal = "Yes" if REFUSAL in response else "No"
    return httpx.Response(200, json={"text": f"Safety: Safe\nCategories: None\nRefusal: {refusal}"})


class BrowserVerifier(ConnectionVerifier):
    """Accept test fixture connections without contacting their addresses."""

    async def verify(self, target: TargetConnection) -> str | None:
        """Declare the synthetic model ready for browser testing."""
        return None


class BrowserSeeds(SeedSource):
    """Test double for browser seeds."""

    def __init__(self, count: int | None) -> None:
        """Retain an optional synthetic fixture size."""
        self._count = count

    def load_cases(self, selection: CaseSelection) -> list[EvaluationCase]:
        """Load original or expanded neutral fixture cases."""
        original = SpreadsheetSeedSource(ROOT / "data/baseline_dataset.xlsx").load_cases(selection)
        if self._count is None or not original:
            return original
        return [
            replace(
                original[index % len(original)],
                identifier=replace(
                    original[index % len(original)].identifier,
                    case_number=original[index % len(original)].identifier.variety.case_number_digit
                    + f"{index:04d}",
                ),
            )
            for index in range(self._count)
        ]


def build_smoke_app(*, case_count: int | None = None) -> FastAPI:
    """Compose the isolated browser smoke application."""
    asyncio.run(initialize_pyrit_async(memory_db_type=IN_MEMORY, load_defaults=False, silent=True))
    temporary = TemporaryDirectory(prefix="harass-browser-")
    engine = create_engine(f"sqlite:///{Path(temporary.name) / 'browser.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    connections = ManageConnections(
        SqlAlchemyConnectionStore(factory),
        FernetSecretCipher(Fernet.generate_key().decode("ascii")),
        BrowserVerifier(),
    )
    moderator = GuardModerator(
        httpx.AsyncClient(
            base_url="http://judge.test", transport=httpx.MockTransport(browser_guard)
        )
    )
    evaluation = RunEvaluation(
        BrowserSeeds(case_count),
        BaselineEngine(
            PyritAttemptExecutor(
                lambda connection: BrowserTarget(),
                GuardCategoryScorer(moderator=moderator),
                GuardAttackScorer(moderator=moderator),
            )
        ),
    )
    queue = SqlAlchemyRunQueue(factory, "browser-profile", "browser-judge")
    worker = ProcessRuns(queue, connections, evaluation, None, poll_seconds=0.1)
    app = create_app(
        connections,
        ManageRuns(
            SqlAlchemyRunStore(factory),
            connections,
            queue=queue,
            generated=SqlAlchemyGeneratedEvidence(factory),
        ),
        authentication=ManageAuthentication(
            SqlAlchemyAuthenticationStore(factory),
            JwtAuthenticationSecurity("browser-fixture-only-signing-key-" + "x" * 32),
        ),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(worker.serve())
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            engine.dispose()
            temporary.cleanup()

    app.router.lifespan_context = lifespan
    app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
    return app


if __name__ == "__main__":
    uvicorn.run(build_smoke_app(), host="127.0.0.1", port=8765)
