"""Composition root of the HTTP API."""

import hashlib
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from harass.application.connections import ManageConnections
from harass.application.evaluation.run_service import ManageRuns
from harass.bootstrap.accounts import build_accounts
from harass.bootstrap.evaluation import TEMPLATES_DIR
from harass.bootstrap.execution_profile import execution_profile
from harass.infrastructure.dataset.yaml_variant_catalog import (
    YamlVariantCatalog,
)
from harass.infrastructure.http.endpoint_policy import EndpointPolicy
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
from harass.infrastructure.persistence.sqlalchemy_request_limiter import (
    SqlAlchemyRequestLimiter,
)
from harass.infrastructure.persistence.sqlalchemy_runs import (
    SqlAlchemyRunStore,
)
from harass.infrastructure.security.fernet_secret_cipher import (
    FernetSecretCipher,
)
from harass.infrastructure.settings import BackendSettings, Settings
from harass.interfaces.api.app import create_app

FRONTEND_DIR = Path("frontend")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def build_api() -> FastAPI:
    """Load settings, wire the HTTP adapters and return the app."""
    load_dotenv(Path(".env"))
    settings = Settings.for_admission(os.environ)
    backend = BackendSettings.from_environment(os.environ)

    engine = create_engine(
        backend.database_url,
        connect_args={"connect_timeout": 10},
        pool_pre_ping=True,
    )
    try:
        require_current_schema(engine)
    except Exception:
        engine.dispose()
        raise
    session_factory = sessionmaker(engine)

    connections = ManageConnections(
        SqlAlchemyConnectionStore(session_factory),
        FernetSecretCipher(backend.encryption_key),
        OpenAIConnectionVerifier(
            endpoint_policy=EndpointPolicy(
                settings.target_private_hosts, settings.target_allow_http
            )
        ),
    )
    catalog = YamlVariantCatalog(TEMPLATES_DIR)
    queue = SqlAlchemyRunQueue(
        session_factory,
        execution_profile(settings),
        hashlib.sha256(settings.judge.base_url.encode("utf-8")).hexdigest(),
    )
    runs = ManageRuns(
        SqlAlchemyRunStore(session_factory), connections, queue=queue
    )
    authentication, recovery = build_accounts(session_factory, backend)
    app = create_app(
        connections,
        runs,
        catalog,
        authentication=authentication,
        recovery=recovery,
        secure_cookie=backend.secure_cookie,
        session_seconds=backend.session_seconds,
        request_limiter=SqlAlchemyRequestLimiter(
            session_factory, backend.jwt_secret
        ),
        allowed_hosts=os.environ.get(
            "HARASS_ALLOWED_HOSTS", "localhost,127.0.0.1"
        ).split(","),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Release the database engine when the API lifecycle ends."""
        try:
            yield
        finally:
            engine.dispose()

    app.router.lifespan_context = lifespan
    if FRONTEND_DIR.is_dir():
        # Use one origin for the frontend and API.
        app.mount(
            "/",
            StaticFiles(directory=FRONTEND_DIR, html=True),
            name="frontend",
        )
    return app


def run() -> None:
    """Serve the configured HTTP application."""
    import uvicorn

    load_dotenv(Path(".env"))
    host = os.environ.get("HARASS_API_HOST", DEFAULT_HOST)
    port = int(os.environ.get("HARASS_API_PORT", DEFAULT_PORT))
    uvicorn.run(build_api(), host=host, port=port)


if __name__ == "__main__":
    run()
