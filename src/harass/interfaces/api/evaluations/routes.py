"""Evaluation admission, lifecycle control and streamed evidence endpoints."""

import json
import re
from typing import Any

from fastapi import Depends, FastAPI, Query
from fastapi.responses import StreamingResponse
from starlette.responses import Response

from harass.application.errors import (
    UnknownConnectionError,
    UnknownRunError,
)
from harass.application.evaluation.run_service import ManageRuns
from harass.domain.evaluation_run import EvaluationRun
from harass.interfaces.api.accounts.dependencies import authenticated_owner
from harass.interfaces.api.evaluations.mapping import (
    run_parameters,
    validated_identifier,
)
from harass.interfaces.api.evaluations.schemas import RunRequest, RunResponse


def install_run_routes(app: FastAPI, runs: ManageRuns) -> None:
    """Register the endpoints with their injected application service."""

    @app.post("/runs", response_model=RunResponse, status_code=201)
    def start_run(
        body: RunRequest,
        owner: str = Depends(authenticated_owner),
    ) -> EvaluationRun:
        """Admit an evaluation using the authenticated owner's connection."""
        parameters = run_parameters(body)
        run = runs.start(
            owner,
            validated_identifier(body.connection_id, UnknownConnectionError),
            parameters,
        )
        return run

    @app.get("/runs", response_model=list[RunResponse])
    def list_runs(
        response: Response,
        owner: str = Depends(authenticated_owner),
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
    ) -> list[EvaluationRun]:
        """Return a bounded history page with whole-account lifecycle."""
        items, counts = runs.page_for_owner(owner, offset, limit)
        response.headers["X-Status-Counts"] = json.dumps(counts)
        return items

    @app.post("/runs/{run_id}/resume", response_model=RunResponse)
    def resume_run(
        run_id: str, owner: str = Depends(authenticated_owner)
    ) -> EvaluationRun:
        """Requeue an owned suspended evaluation without resetting progress."""
        return runs.resume(
            owner, validated_identifier(run_id, UnknownRunError)
        )

    @app.post("/runs/{run_id}/cancel", response_model=RunResponse)
    def cancel_run(
        run_id: str, owner: str = Depends(authenticated_owner)
    ) -> EvaluationRun:
        """Cancel this owner's run without deleting its evidence."""
        return runs.cancel(
            owner, validated_identifier(run_id, UnknownRunError)
        )

    @app.get("/runs/{run_id}", response_model=RunResponse)
    def get_run(
        run_id: str, owner: str = Depends(authenticated_owner)
    ) -> EvaluationRun:
        """Return owner-scoped lifecycle and progress information."""
        return runs.get(owner, validated_identifier(run_id, UnknownRunError))

    @app.get("/runs/{run_id}/report")
    def get_report(
        run_id: str, owner: str = Depends(authenticated_owner)
    ) -> dict[str, Any]:
        """Return the stored summary and explicit execution lifecycle."""
        document: dict[str, Any] = runs.get_report(
            owner, validated_identifier(run_id, UnknownRunError)
        )
        return document

    @app.get("/runs/{run_id}/outcomes")
    def get_outcomes(
        run_id: str,
        owner: str = Depends(authenticated_owner),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        """Return one bounded page of owned attempt evidence."""
        return runs.outcome_page(
            owner, validated_identifier(run_id, UnknownRunError), offset, limit
        )

    @app.get("/runs/{run_id}/report/export")
    def export_report(
        run_id: str, owner: str = Depends(authenticated_owner)
    ) -> StreamingResponse:
        """Stream the complete owned report as a downloadable JSON document."""
        run_id = validated_identifier(run_id, UnknownRunError)
        runs.get_report(owner, run_id)
        filename = "harass-" + re.sub(r"[^A-Za-z0-9_-]", "", run_id) + ".json"
        return StreamingResponse(
            runs.export_report(owner, run_id),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )
