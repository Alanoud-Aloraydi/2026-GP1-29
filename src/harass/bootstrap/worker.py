"""Independent durable evaluation worker sharing the API's PostgreSQL queue."""

import asyncio
import logging
import os
from contextlib import suppress

from pyrit.setup import SQLITE, initialize_pyrit_async

from harass.application.connections import ManageConnections
from harass.application.evaluation.worker import ProcessRuns
from harass.bootstrap.database import database_sessions, judge_slot, load_environment
from harass.bootstrap.evaluation import build_evaluation
from harass.bootstrap.execution_profile import execution_profile
from harass.infrastructure.http.openai_connection_verifier import OpenAIConnectionVerifier
from harass.infrastructure.persistence.sqlalchemy_connections import SqlAlchemyConnectionStore
from harass.infrastructure.persistence.sqlalchemy_jobs import SqlAlchemyRunQueue
from harass.infrastructure.security.fernet_secret_cipher import FernetSecretCipher
from harass.infrastructure.settings import BackendSettings, Settings


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
        evaluation, judge = build_evaluation(settings)
        try:
            await ProcessRuns(queue, connections, evaluation).serve()
        finally:
            await judge.aclose()


def main() -> None:
    """Process queued evaluations with durable recovery checkpoints."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    with suppress(KeyboardInterrupt):
        asyncio.run(_serve())


if __name__ == "__main__":
    main()
