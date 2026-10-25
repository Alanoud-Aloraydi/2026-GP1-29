"""FastAPI application exposing connection and run management over HTTP."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from harass.application.accounts.authentication import (
    ManageAuthentication,
)
from harass.application.accounts.recovery import AccountRecovery
from harass.application.connections import ManageConnections
from harass.application.errors import (
    ActiveRunError,
    ApplicationError,
    ConflictError,
    ConnectionNotReadyError,
    UnknownConnectionError,
    UnknownRunError,
)
from harass.application.evaluation.run_service import ManageRuns
from harass.application.ports.request_limiter import RequestLimiter
from harass.application.ports.run_queue import StorageUnavailableError
from harass.application.ports.variant_catalog import VariantCatalog
from harass.domain.errors import DomainError
from harass.interfaces.api.accounts.cookies import SessionCookies
from harass.interfaces.api.accounts.dependencies import authenticated_owner
from harass.interfaces.api.accounts.recovery_routes import (
    install_recovery_routes,
)
from harass.interfaces.api.accounts.routes import install_auth
from harass.interfaces.api.connections.routes import install_connection_routes
from harass.interfaces.api.evaluations.catalogue import (
    install_catalogue_routes,
)
from harass.interfaces.api.evaluations.routes import install_run_routes
from harass.interfaces.api.middleware.body_limit import RequestBodyLimit
from harass.interfaces.api.middleware.security_headers import (
    install_security_headers,
)

owner_id = authenticated_owner


def create_app(
    connections: ManageConnections,
    runs: ManageRuns,
    catalog: VariantCatalog | None = None,
    *,
    authentication: ManageAuthentication | None = None,
    recovery: AccountRecovery | None = None,
    secure_cookie: bool = False,
    session_seconds: int = 900,
    request_limiter: RequestLimiter | None = None,
    allowed_hosts: list[str] | None = None,
) -> FastAPI:
    """Build the API, wiring routes to the injected use cases."""
    app = FastAPI(title="HARASS API")
    _install_error_handlers(app)
    app.state.authentication = authentication
    if authentication is not None:
        install_auth(
            app,
            authentication,
            secure_cookie=secure_cookie,
            session_seconds=session_seconds,
            request_limiter=request_limiter,
        )

    install_recovery_routes(
        app, recovery, SessionCookies(secure_cookie, session_seconds)
    )
    install_catalogue_routes(app, catalog)
    install_connection_routes(app, connections)
    install_run_routes(app, runs)
    install_security_headers(app, secure_cookie)
    app.add_middleware(RequestBodyLimit)
    if allowed_hosts is not None:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    return app


def _install_error_handlers(app: FastAPI) -> None:
    """Map application and domain errors to HTTP status codes."""

    @app.exception_handler(ActiveRunError)
    async def _active_run(_: object, error: ActiveRunError) -> JSONResponse:
        """Return the current owner's active run as a conflict response."""
        return JSONResponse(
            status_code=409,
            content={"code": "active_run", "active_run_id": error.run_id},
        )

    @app.exception_handler(StorageUnavailableError)
    async def _unavailable(_: object, error: Exception) -> JSONResponse:
        """Represent unavailable durable storage without provider details."""
        return JSONResponse(
            status_code=503, content={"detail": "Run storage is unavailable."}
        )

    @app.exception_handler(UnknownConnectionError)
    @app.exception_handler(UnknownRunError)
    async def _not_found(_: object, error: Exception) -> JSONResponse:
        """Map owner-scoped missing records to an HTTP not-found response."""
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(ConnectionNotReadyError)
    @app.exception_handler(ConflictError)
    async def _conflict(_: object, error: Exception) -> JSONResponse:
        """Represent a state conflict without retrying the mutation."""
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(DomainError)
    @app.exception_handler(ApplicationError)
    async def _bad_request(_: object, error: Exception) -> JSONResponse:
        """Expose a validated domain or application rejection."""
        return JSONResponse(status_code=400, content={"detail": str(error)})
