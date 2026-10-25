"""Independent durable evaluation worker sharing the API's PostgreSQL queue."""

import asyncio
import hashlib
import logging
import os
from contextlib import suppress
from pathlib import Path

from dotenv import load_dotenv
from pyrit.setup import SQLITE, initialize_pyrit_async
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from harass.application.connections import ManageConnections
from harass.application.evaluation.worker import ProcessRuns
from harass.bootstrap.evaluation import build_evaluation
from harass.bootstrap.execution_profile import execution_profile
from harass.infrastructure.http.openai_connection_verifier import (
    OpenAIConnectionVerifier,
)
from harass.infrastructure.persistence.schema import require_current_schema
from harass.infrastructure.persistence.sqlalchemy_connections import (
    SqlAlchemyConnectionStore,
)
from harass.infrastructure.persistence.sqlalchemy_jobs import (
    SqlAlchemyRunQueue,
)
from harass.infrastructure.pyrit.target_builder import close_target
from harass.infrastructure.security.fernet_secret_cipher import (
    FernetSecretCipher,
)
from harass.infrastructure.settings import BackendSettings, Settings


async def _serve() -> None:
    """Initialize durable evaluation dependencies and process queued runs."""
    load_dotenv(Path(".env"))
    settings = Settings.from_environment(os.environ)
    backend = BackendSettings.from_environment(os.environ)
    engine = create_engine(
        backend.database_url, connect_args={"connect_timeout": 10}
    )
    judge = None
    try:
        require_current_schema(engine)
        factory = sessionmaker(engine)
        queue = SqlAlchemyRunQueue(
            factory,
            execution_profile(settings),
            hashlib.sha256(
                settings.judge.base_url.encode("utf-8")
            ).hexdigest(),
        )
        connections = ManageConnections(
            SqlAlchemyConnectionStore(factory),
            FernetSecretCipher(backend.encryption_key),
            OpenAIConnectionVerifier(),
        )
        await initialize_pyrit_async(
            memory_db_type=SQLITE, load_defaults=False, silent=True
        )
        evaluation, judge = build_evaluation(settings)
        await ProcessRuns(queue, connections, evaluation).serve()
    finally:
        if judge is not None:
            await close_target(judge)
        engine.dispose()


def main() -> None:
    """Process queued evaluations with durable recovery checkpoints."""
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )
    with suppress(KeyboardInterrupt):
        asyncio.run(_serve())


if __name__ == "__main__":
    main()
