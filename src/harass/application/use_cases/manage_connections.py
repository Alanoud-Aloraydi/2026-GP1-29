"""Use case: add, update, list and test clients' model connections."""

import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from harass.application.errors import ConflictError, ConnectionNotReadyError
from harass.application.ports.connection_store import ConnectionStore
from harass.application.ports.connection_verifier import ConnectionVerifier
from harass.application.ports.secret_cipher import SecretCipher
from harass.domain.model_connection import ConnectionStatus, ModelConnection
from harass.domain.target_connection import TargetConnection


class ManageConnections:
    """Keeps API keys encrypted at rest and decrypts them only to contact the endpoint."""

    def __init__(
        self,
        store: ConnectionStore,
        cipher: SecretCipher,
        verifier: ConnectionVerifier,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Store the ports and the clock used to time-stamp connection tests."""
        self._store = store
        self._cipher = cipher
        self._verifier = verifier
        self._clock = clock

    def add(self, owner_id: str, base_url: str, model_name: str, api_key: str) -> ModelConnection:
        """Save a new, untested connection with its key encrypted."""
        connection = ModelConnection(
            connection_id=str(uuid.uuid4()),
            owner_id=owner_id,
            base_url=base_url,
            model_name=model_name,
        )
        _ = _target(connection, api_key)  # validates the key before anything is stored
        self._store.save(connection, self._cipher.encrypt(api_key))
        return connection

    def update(
        self,
        owner_id: str,
        connection_id: str,
        base_url: str,
        model_name: str,
        api_key: str | None,
        *,
        expected_revision: int | None = None,
    ) -> ModelConnection:
        """Change endpoint details; a missing key keeps the stored one. Resets the status."""
        current = self._store.get(connection_id, owner_id)
        if expected_revision is not None and expected_revision != current.revision:
            raise ConflictError("Connection changed; reload before editing it.")
        updated = ModelConnection(
            connection_id=current.connection_id,
            owner_id=owner_id,
            base_url=base_url,
            model_name=model_name,
            revision=current.revision,
            created_at=current.created_at,
            updated_at=self._clock(),
        )
        if api_key is not None:
            _ = _target(updated, api_key)
        self._store.save(updated, self._cipher.encrypt(api_key) if api_key is not None else None)
        return self._store.get(connection_id, owner_id)

    def list_for_owner(self, owner_id: str) -> list[ModelConnection]:
        """Return the owner's connections; keys are never part of the result."""
        return self._store.list_for_owner(owner_id)

    def get(self, owner_id: str, connection_id: str) -> ModelConnection:
        """Read connection metadata without decrypting the key."""
        return self._store.get(connection_id, owner_id)

    def page_for_owner(
        self, owner_id: str, offset: int, limit: int
    ) -> tuple[list[ModelConnection], dict[str, int]]:
        """Return a bounded owner-scoped page with whole-inventory status counts."""
        return self._store.page_for_owner(owner_id, offset, limit), self._store.counts_for_owner(
            owner_id
        )

    async def verify(self, owner_id: str, connection_id: str) -> ModelConnection:
        """Test the endpoint and record the outcome, which is technical, not a safety verdict."""
        connection, key = self._store.snapshot(connection_id, owner_id)
        failure = await self._verifier.verify(_target(connection, self._cipher.decrypt(key)))
        tested = replace(
            connection,
            status=ConnectionStatus.FAILED if failure else ConnectionStatus.CONNECTED,
            failure_reason=failure,
            last_tested_at=self._clock(),
        )
        self._store.save(tested, None)
        return self._store.get(connection_id, owner_id)

    def target_for_evaluation(
        self, owner_id: str, connection_id: str, max_requests_per_minute: int | None = None
    ) -> TargetConnection:
        """Return the decrypted target of a connection that passed its last test.

        Raises:
            ConnectionNotReadyError: If the connection is untested or its last test failed.
        """
        connection, key = self._store.snapshot(connection_id, owner_id)
        if connection.status is not ConnectionStatus.CONNECTED:
            raise ConnectionNotReadyError(
                f"Connection {connection_id} must pass its connection test before evaluation."
            )
        return _target(connection, self._cipher.decrypt(key), max_requests_per_minute)


def _target(
    connection: ModelConnection, api_key: str, max_requests_per_minute: int | None = None
) -> TargetConnection:
    """Build the target connection, which validates the key."""
    return TargetConnection(
        base_url=connection.base_url,
        model_name=connection.model_name,
        api_key=api_key,
        max_requests_per_minute=max_requests_per_minute,
        connection_revision=connection.revision,
    )
