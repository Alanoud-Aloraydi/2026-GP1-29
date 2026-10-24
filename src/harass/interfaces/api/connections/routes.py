"""Owner-scoped model connection endpoints."""

import json

from fastapi import Depends, FastAPI, HTTPException, Query
from starlette.responses import Response

from harass.application.connections import ManageConnections
from harass.application.errors import (
    UnknownConnectionError,
)
from harass.domain.model_connection import ModelConnection
from harass.interfaces.api.accounts.dependencies import authenticated_owner
from harass.interfaces.api.connections.schemas import (
    ConnectionRequest,
    ConnectionResponse,
)
from harass.interfaces.api.evaluations.mapping import validated_identifier


def install_connection_routes(
    app: FastAPI, connections: ManageConnections
) -> None:
    """Register the endpoints with their injected application service."""

    @app.post(
        "/connections", response_model=ConnectionResponse, status_code=201
    )
    def add_connection(
        body: ConnectionRequest, owner: str = Depends(authenticated_owner)
    ) -> ModelConnection:
        """Persist an owned model connection with encrypted credentials."""
        if body.api_key is None:
            raise HTTPException(
                status_code=400,
                detail="An API key is required to add a connection.",
            )
        return connections.add(
            owner, body.base_url, body.model_name, body.api_key
        )

    @app.get("/connections", response_model=list[ConnectionResponse])
    def list_connections(
        response: Response,
        owner: str = Depends(authenticated_owner),
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
    ) -> list[ModelConnection]:
        """Return a bounded connection page and aggregate status counts."""
        items, counts = connections.page_for_owner(owner, offset, limit)
        response.headers["X-Status-Counts"] = json.dumps(counts)
        return items

    @app.get("/connections/{connection_id}", response_model=ConnectionResponse)
    def get_connection(
        connection_id: str, owner: str = Depends(authenticated_owner)
    ) -> ModelConnection:
        """Read owned metadata without exposing an API key."""
        return connections.get(
            owner, validated_identifier(connection_id, UnknownConnectionError)
        )

    @app.put("/connections/{connection_id}", response_model=ConnectionResponse)
    def update_connection(
        connection_id: str,
        body: ConnectionRequest,
        owner: str = Depends(authenticated_owner),
    ) -> ModelConnection:
        """Replace an owned connection using its expected revision."""
        return connections.update(
            owner,
            validated_identifier(connection_id, UnknownConnectionError),
            body.base_url,
            body.model_name,
            body.api_key,
            expected_revision=body.revision,
        )

    @app.post(
        "/connections/{connection_id}/verify",
        response_model=ConnectionResponse,
    )
    async def verify_connection(
        connection_id: str, owner: str = Depends(authenticated_owner)
    ) -> ModelConnection:
        """Check model discovery and bounded generation for the owner."""
        return await connections.verify(
            owner, validated_identifier(connection_id, UnknownConnectionError)
        )
