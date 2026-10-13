"""Local browser fixture using the real API, stores, catalogue and PyRIT, without external models.

Run this file directly for browser QA. The synthetic verifier and model/judge are deliberately
test-only; no .env credentials or production database are loaded.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

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

from harass.application.ports.connection_verifier import ConnectionVerifier
from harass.application.ports.seed_source import SeedSource
from harass.application.use_cases.manage_authentication import ManageAuthentication
from harass.application.use_cases.manage_connections import ManageConnections
from harass.application.use_cases.manage_runs import ManageRuns
from harass.application.use_cases.process_runs import ProcessRuns
from harass.application.use_cases.run_evaluation import RunEvaluation
from harass.application.variant_evaluation_engine import VariantEvaluationEngine
from harass.domain.case_selection import CaseSelection
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.target_connection import TargetConnection
from harass.infrastructure.dataset.spreadsheet_seed_source import SpreadsheetSeedSource
from harass.infrastructure.dataset.yaml_variant_catalog import YamlVariantCatalog
from harass.infrastructure.persistence.sqlalchemy_authentication import (
    SqlAlchemyAuthenticationStore,
)
from harass.infrastructure.persistence.sqlalchemy_jobs import SqlAlchemyRunQueue
from harass.infrastructure.persistence.sqlalchemy_stores import (
    SqlAlchemyConnectionStore,
    SqlAlchemyRunStore,
)
from harass.infrastructure.persistence.tables import Base
from harass.infrastructure.pyrit.scoring.scorer_builder import (
    build_attack_success_scorer,
    build_response_category_scorer,
)
from harass.infrastructure.pyrit.variant_attempt_executor import PyritAttemptExecutor
from harass.infrastructure.security.fernet_secret_cipher import FernetSecretCipher
from harass.infrastructure.security.jwt_authentication import JwtAuthenticationSecurity
from harass.interfaces.api.app import create_app

ROOT = Path(__file__).resolve().parents[2]
REFUSAL = "رفض اصطناعي لاختبار الواجهة."


class BrowserTarget(PromptTarget):
    """Synthetic model that refuses a wrapped request to exercise early-stop reporting."""

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


class BrowserJudge(BrowserTarget):
    """Synthetic rubric-compatible judge; never interpreted as human ground truth."""

    async def _send_prompt_to_target_async(
        self, *, normalized_conversation: list[Message]
    ) -> list[Message]:
        pieces = [piece for message in normalized_conversation for piece in message.message_pieces]
        request = pieces[-1]
        category_rubric = any("PRF" in piece.converted_value for piece in pieces[:-1])
        refused = REFUSAL in request.converted_value
        verdict = (
            {"category": "REF" if refused else "FUL", "score_value": refused}
            if category_rubric
            else {"score_value": False, "metadata": ""}
        )
        verdict.update(
            {
                "description": "Synthetic browser fixture",
                "rationale": "Synthetic test-only verdict.",
            }
        )
        return [
            construct_response_from_request(
                request=request, response_text_pieces=[json.dumps(verdict)]
            )
        ]


class BrowserVerifier(ConnectionVerifier):
    """Accept test fixture connections without contacting their addresses."""

    async def verify(self, target: TargetConnection) -> str | None:
        """Declare the synthetic model ready for browser testing."""
        return None


class BrowserSeeds(SeedSource):
    """Expand neutral fixture seeds to exercise paginated reports without model traffic."""

    def __init__(self, count: int | None) -> None:
        """Retain an optional synthetic fixture size."""
        self._count = count

    def load_cases(self, selection: CaseSelection) -> list[EvaluationCase]:
        """Return the original fixtures or distinct copies under the same selected codes."""
        original = SpreadsheetSeedSource(ROOT / "data/test_dataset.xlsx").load_cases(selection)
        if self._count is None or not original:
            return original
        return [
            replace(
                original[index % len(original)],
                identifier=replace(
                    original[index % len(original)].identifier,
                    case_number=original[
                        index % len(original)
                    ].identifier.variety.case_number_digit
                    + f"{index:04d}",
                ),
            )
            for index in range(self._count)
        ]


def build_smoke_app(*, case_count: int | None = None) -> FastAPI:
    """Wire the full local flow to an isolated SQLite database and scripted models."""
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
    catalogue = YamlVariantCatalog(ROOT / "config" / "templates")
    judge = BrowserJudge()
    evaluation = RunEvaluation(
        BrowserSeeds(case_count),
        VariantEvaluationEngine(
            catalogue,
            PyritAttemptExecutor(
                lambda connection: BrowserTarget(),
                build_response_category_scorer(judge, votes=1),
                build_attack_success_scorer(judge, votes=1),
            ),
        ),
    )
    queue = SqlAlchemyRunQueue(factory, "browser-profile", "browser-judge")
    worker = ProcessRuns(queue, connections, evaluation, poll_seconds=0.1)
    app = create_app(
        connections,
        ManageRuns(SqlAlchemyRunStore(factory), connections, None, queue=queue),
        catalogue,
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
