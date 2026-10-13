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

from harass.application.use_cases.manage_authentication import ManageAuthentication
from harass.application.use_cases.manage_connections import ManageConnections
from harass.application.use_cases.manage_runs import ManageRuns
from harass.bootstrap.evaluation import TEMPLATES_DIR, execution_profile
from harass.infrastructure.dataset.yaml_variant_catalog import YamlVariantCatalog
from harass.infrastructure.http.endpoint_policy import EndpointPolicy
from harass.infrastructure.http.openai_connection_verifier import OpenAIConnectionVerifier
from harass.infrastructure.persistence.schema import require_current_schema
from harass.infrastructure.persistence.sqlalchemy_authentication import (
    SqlAlchemyAuthenticationStore,
)
from harass.infrastructure.persistence.sqlalchemy_jobs import SqlAlchemyRunQueue
from harass.infrastructure.persistence.sqlalchemy_request_limiter import SqlAlchemyRequestLimiter
from harass.infrastructure.persistence.sqlalchemy_stores import (
    SqlAlchemyConnectionStore,
    SqlAlchemyRunStore,
)
from harass.infrastructure.security.fernet_secret_cipher import FernetSecretCipher
from harass.infrastructure.security.jwt_authentication import JwtAuthenticationSecurity
from harass.infrastructure.security.password_blocklist import password_hashes
from harass.infrastructure.settings import BackendSettings, Settings
from harass.interfaces.api.app import create_app

FRONTEND_DIR = Path("frontend")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def build_api() -> FastAPI:
    """Load settings, wire the HTTP adapters and return the app."""
    load_dotenv(Path(".env"))
    settings = Settings.from_environment(os.environ)
    backend = BackendSettings.from_environment(os.environ)

    engine = create_engine(backend.database_url)
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
    runs = ManageRuns(SqlAlchemyRunStore(session_factory), connections, None, queue=queue)
    authentication = ManageAuthentication(
        SqlAlchemyAuthenticationStore(session_factory),
        JwtAuthenticationSecurity(backend.jwt_secret, previous_keys=backend.previous_jwt_secrets),
        backend.session_seconds,
        blocked_password_hashes=password_hashes(os.environ.get("HARASS_PASSWORD_BLOCKLIST_PATH")),
    )
    app = create_app(
        connections,
        runs,
        catalog,
        authentication=authentication,
        secure_cookie=backend.secure_cookie,
        session_seconds=backend.session_seconds,
        request_limiter=SqlAlchemyRequestLimiter(session_factory, backend.jwt_secret),
        allowed_hosts=os.environ.get("HARASS_ALLOWED_HOSTS", "localhost,127.0.0.1").split(","),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            engine.dispose()

    app.router.lifespan_context = lifespan
    if FRONTEND_DIR.is_dir():
        # Serve the static frontend from the same origin, so its API calls need no CORS setup.
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app


def run() -> None:
    """Entry point of the ``harass-api`` command: serve the app with uvicorn."""
    import uvicorn

    load_dotenv(Path(".env"))
    host = os.environ.get("HARASS_API_HOST", DEFAULT_HOST)
    port = int(os.environ.get("HARASS_API_PORT", DEFAULT_PORT))
    uvicorn.run(build_api(), host=host, port=port)


if __name__ == "__main__":
    run()
