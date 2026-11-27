"""Independent durable evaluation worker sharing the API's PostgreSQL queue."""

import asyncio
import logging
import os
from contextlib import suppress

import httpx
from pyrit.setup import SQLITE, initialize_pyrit_async
from sqlalchemy.orm import Session, sessionmaker

from harass.application.connections import ManageConnections
from harass.application.evaluation.worker import ProcessRuns
from harass.application.generation.agentic_run import RunAgenticEvaluation
from harass.application.ports.evaluation import AttemptExecutor
from harass.application.ports.runs import RunAdmission
from harass.bootstrap.database import database_sessions, judge_slot, load_environment
from harass.bootstrap.evaluation import build_attempt_executor, build_evaluation
from harass.bootstrap.execution_profile import execution_profile
from harass.bootstrap.generation import GATEWAY_TIMEOUT_SECONDS, build_agentic
from harass.infrastructure.http.model_gateway import ModelGateway
from harass.infrastructure.http.openai_connection_verifier import OpenAIConnectionVerifier
from harass.infrastructure.persistence.sqlalchemy_connections import SqlAlchemyConnectionStore
from harass.infrastructure.persistence.sqlalchemy_jobs import SqlAlchemyRunQueue
from harass.infrastructure.security.fernet_secret_cipher import FernetSecretCipher
from harass.infrastructure.settings import BackendSettings, GenerationSettings, Settings

logger = logging.getLogger(__name__)


async def _serve() -> None:
    """Initialize durable evaluation dependencies and process queued runs."""
    load_environment()
    settings = Settings.from_environment(os.environ)
    backend = BackendSettings.from_environment(os.environ)
    with database_sessions(backend.database_url) as factory:
        queue = SqlAlchemyRunQueue(
            factory, execution_profile(settings), judge_slot(settings.judge_server_url)
        )
        connections = ManageConnections(
            SqlAlchemyConnectionStore(factory),
            FernetSecretCipher(backend.encryption_key),
            OpenAIConnectionVerifier(),
        )
        await initialize_pyrit_async(memory_db_type=SQLITE, load_defaults=False, silent=True)
        executor, judge = build_attempt_executor(settings)
        async with httpx.AsyncClient() as client:
            try:
                agentic = _agentic(factory, client, executor, queue)
                await ProcessRuns(queue, connections, build_evaluation(executor), agentic).serve()
            finally:
                await judge.aclose()


def _agentic(
    factory: sessionmaker[Session],
    client: httpx.AsyncClient,
    executor: AttemptExecutor,
    evidence: RunAdmission,
) -> RunAgenticEvaluation | None:
    """Build the agentic run, or None when the generator models are not configured."""
    try:
        generation = GenerationSettings.from_environment(os.environ)
    except ValueError:
        logger.warning("Generator models are not configured; agentic runs will fail.")
        return None
    gateway = ModelGateway(client, GATEWAY_TIMEOUT_SECONDS)
    return build_agentic(factory, gateway, generation, executor, evidence)


def main() -> None:
    """Process queued evaluations with durable recovery checkpoints."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    with suppress(KeyboardInterrupt):
        asyncio.run(_serve())


if __name__ == "__main__":
    main()
