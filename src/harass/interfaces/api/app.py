"""FastAPI application exposing connection and run management over HTTP."""

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from harass.application.errors import (
    ActiveRunError,
    ApplicationError,
    ConflictError,
    ConnectionNotReadyError,
    UnknownConnectionError,
    UnknownRunError,
)
from harass.application.ports.request_limiter import RequestLimiter
from harass.application.ports.run_queue import StorageUnavailableError
from harass.application.ports.variant_catalog import VariantCatalog
from harass.application.use_cases.manage_authentication import ManageAuthentication
from harass.application.use_cases.manage_connections import ManageConnections
from harass.application.use_cases.manage_runs import ManageRuns, RunParameters
from harass.domain.case_selection import CaseSelection
from harass.domain.errors import DomainError
from harass.domain.evaluation_run import EvaluationRun
from harass.domain.model_connection import ModelConnection
from harass.domain.prompt_variant import AdaptiveSettings, EvaluationMode, VariantSelection
from harass.domain.taxonomy import (
    ArabicVariety,
    Axis,
    BypassStrategy,
    RiskCategory,
    SubjectDomain,
)
from harass.interfaces.api.authentication import authenticated_owner, install_auth
from harass.interfaces.api.request_body_limit import RequestBodyLimit
from harass.interfaces.api.schemas import (
    ConnectionRequest,
    ConnectionResponse,
    RunRequest,
    RunResponse,
    SelectionModel,
)

owner_id = authenticated_owner


def create_app(
    connections: ManageConnections,
    runs: ManageRuns,
    catalog: VariantCatalog | None = None,
    *,
    authentication: ManageAuthentication | None = None,
    secure_cookie: bool = False,
    session_seconds: int = 3600,
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

    @app.get("/evaluation-options")
    def evaluation_options(owner: str = Depends(owner_id)) -> dict[str, Any]:
        return {
            "varieties": [member.value for member in ArabicVariety],
            "subject_domains": [member.value for member in SubjectDomain],
            "risk_categories": [member.value for member in RiskCategory],
            "strategies": [member.value for member in BypassStrategy],
            "templates": [asdict(template) for template in catalog.templates()] if catalog else [],
            "transforms": [asdict(transform) for transform in catalog.transforms()]
            if catalog
            else [],
        }

    @app.post("/connections", response_model=ConnectionResponse, status_code=201)
    def add_connection(body: ConnectionRequest, owner: str = Depends(owner_id)) -> ModelConnection:
        if body.api_key is None:
            raise HTTPException(
                status_code=400, detail="An API key is required to add a connection."
            )
        return connections.add(owner, body.base_url, body.model_name, body.api_key)

    @app.get("/connections", response_model=list[ConnectionResponse])
    def list_connections(
        response: Response,
        owner: str = Depends(owner_id),
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
    ) -> list[ModelConnection]:
        items, counts = connections.page_for_owner(owner, offset, limit)
        response.headers["X-Status-Counts"] = json.dumps(counts)
        return items

    @app.get("/connections/{connection_id}", response_model=ConnectionResponse)
    def get_connection(connection_id: str, owner: str = Depends(owner_id)) -> ModelConnection:
        """Read owned metadata without exposing an API key."""
        return connections.get(owner, _identifier(connection_id, UnknownConnectionError))

    @app.put("/connections/{connection_id}", response_model=ConnectionResponse)
    def update_connection(
        connection_id: str, body: ConnectionRequest, owner: str = Depends(owner_id)
    ) -> ModelConnection:
        return connections.update(
            owner,
            _identifier(connection_id, UnknownConnectionError),
            body.base_url,
            body.model_name,
            body.api_key,
            expected_revision=body.revision,
        )

    @app.post("/connections/{connection_id}/verify", response_model=ConnectionResponse)
    async def verify_connection(
        connection_id: str, owner: str = Depends(owner_id)
    ) -> ModelConnection:
        return await connections.verify(owner, _identifier(connection_id, UnknownConnectionError))

    @app.post("/runs", response_model=RunResponse, status_code=201)
    def start_run(
        body: RunRequest, background: BackgroundTasks, owner: str = Depends(owner_id)
    ) -> EvaluationRun:
        parameters = _parameters(body)
        run = runs.start(
            owner, _identifier(body.connection_id, UnknownConnectionError), parameters
        )
        if not runs.durable:
            background.add_task(runs.execute, run, parameters)
        return run

    @app.get("/runs", response_model=list[RunResponse])
    def list_runs(
        response: Response,
        owner: str = Depends(owner_id),
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
    ) -> list[EvaluationRun]:
        items, counts = runs.page_for_owner(owner, offset, limit)
        response.headers["X-Status-Counts"] = json.dumps(counts)
        return items

    @app.post("/runs/{run_id}/resume", response_model=RunResponse)
    def resume_run(run_id: str, owner: str = Depends(owner_id)) -> EvaluationRun:
        return runs.resume(owner, _identifier(run_id, UnknownRunError))

    @app.post("/runs/{run_id}/cancel", response_model=RunResponse)
    def cancel_run(run_id: str, owner: str = Depends(owner_id)) -> EvaluationRun:
        """Cancel this owner's run without deleting its evidence."""
        return runs.cancel(owner, _identifier(run_id, UnknownRunError))

    @app.get("/runs/{run_id}", response_model=RunResponse)
    def get_run(run_id: str, owner: str = Depends(owner_id)) -> EvaluationRun:
        return runs.get(owner, _identifier(run_id, UnknownRunError))

    @app.get("/runs/{run_id}/report")
    def get_report(run_id: str, owner: str = Depends(owner_id)) -> dict[str, Any]:
        document: dict[str, Any] = runs.get_report(owner, _identifier(run_id, UnknownRunError))
        return document

    @app.get("/runs/{run_id}/outcomes")
    def get_outcomes(
        run_id: str,
        owner: str = Depends(owner_id),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        return runs.outcome_page(owner, _identifier(run_id, UnknownRunError), offset, limit)

    @app.get("/runs/{run_id}/report/export")
    def export_report(run_id: str, owner: str = Depends(owner_id)) -> StreamingResponse:
        run_id = _identifier(run_id, UnknownRunError)
        runs.get_report(owner, run_id)
        filename = "harass-" + re.sub(r"[^A-Za-z0-9_-]", "", run_id) + ".json"
        return StreamingResponse(
            runs.export_report(owner, run_id),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path not in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                "connect-src 'self'; frame-ancestors 'none'; object-src 'none'; "
                "base-uri 'self'; form-action 'self'"
            )
        if secure_cookie:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    app.add_middleware(RequestBodyLimit)
    if allowed_hosts is not None:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    return app


def _parameters(body: RunRequest) -> RunParameters:
    """Translate a run request into domain run parameters."""
    if body.run_type is not None:
        # Product choices fix the protocol centrally. Library filters and budgets remain
        # available only through the separate advanced request contract (run_type omitted).
        selection = CaseSelection(
            axis=body.selection.axis,
            varieties=frozenset(body.selection.varieties),
        )
        return RunParameters(
            selection=selection,
            include_baseline=True,
            variant_selection=VariantSelection((), ())
            if body.run_type == "baseline"
            else VariantSelection(),
            adaptive_settings=AdaptiveSettings(
                EvaluationMode.STATIC if body.run_type == "baseline" else EvaluationMode.ADAPTIVE,
                8,
                0,
            ),
        )
    return RunParameters(
        selection=_selection(body.selection),
        include_baseline=body.include_baseline,
        max_base_cases_per_axis=body.max_base_cases_per_axis,
        sampling_seed=body.sampling_seed,
        variant_selection=VariantSelection(
            tuple(body.template_names) if body.template_names is not None else None,
            tuple(body.transform_names) if body.transform_names is not None else None,
        ),
        adaptive_settings=AdaptiveSettings(
            body.evaluation_mode, body.attempt_budget, body.sampling_seed
        ),
    )


def _identifier(value: str, error_type: type[ApplicationError]) -> str:
    """Reject malformed entity IDs before PostgreSQL attempts to cast them."""
    try:
        return str(UUID(value))
    except ValueError as error:
        raise error_type("Record not found.") from error


def _selection(model: SelectionModel) -> CaseSelection:
    """Translate the selection model into the domain selection."""
    return CaseSelection(
        axis=Axis(model.axis) if model.axis else None,
        subject_domains=frozenset(map(SubjectDomain, model.subject_domains)),
        risk_categories=frozenset(map(RiskCategory, model.risk_categories)),
        varieties=frozenset(map(ArabicVariety, model.varieties)),
        strategies=frozenset(map(BypassStrategy, model.strategies)),
    )


def _install_error_handlers(app: FastAPI) -> None:
    """Map application and domain errors to HTTP status codes."""

    @app.exception_handler(ActiveRunError)
    async def _active_run(_: object, error: ActiveRunError) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"code": "active_run", "active_run_id": error.run_id}
        )

    @app.exception_handler(StorageUnavailableError)
    async def _unavailable(_: object, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": "Run storage is unavailable."})

    @app.exception_handler(UnknownConnectionError)
    @app.exception_handler(UnknownRunError)
    async def _not_found(_: object, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(ConnectionNotReadyError)
    @app.exception_handler(ConflictError)
    async def _conflict(_: object, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(DomainError)
    @app.exception_handler(ApplicationError)
    async def _bad_request(_: object, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(error)})
