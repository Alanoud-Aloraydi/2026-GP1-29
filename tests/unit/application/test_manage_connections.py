"""Tests for the connection-management use case with in-memory fakes."""

from datetime import UTC, datetime

import pytest

from harass.application.connections import ManageConnections
from harass.application.errors import (
    ConnectionNotReadyError,
    UnknownConnectionError,
)
from harass.application.ports.connection_store import ConnectionStore
from harass.application.ports.connection_verifier import ConnectionVerifier
from harass.application.ports.secret_cipher import SecretCipher
from harass.domain.model_connection import ConnectionStatus, ModelConnection
from harass.domain.target_connection import TargetConnection

OWNER = "user-1"


class ReversingCipher(SecretCipher):
    """A reversible stand-in whose token is clearly not the plaintext."""

    def encrypt(self, secret: str) -> str:
        """Return a reversible non-plaintext token."""
        return "enc:" + secret[::-1]

    def decrypt(self, token: str) -> str:
        """Return the plaintext behind a token."""
        return token.removeprefix("enc:")[::-1]


class InMemoryConnectionStore(ConnectionStore):
    """Holds connections and encrypted keys in dictionaries."""

    def __init__(self) -> None:
        """Start empty."""
        self.connections: dict[str, ModelConnection] = {}
        self.keys: dict[str, str] = {}

    def save(
        self, connection: ModelConnection, encrypted_api_key: str | None
    ) -> None:
        """Insert or update a connection."""
        if (
            encrypted_api_key is None
            and connection.connection_id not in self.keys
        ):
            raise UnknownConnectionError("No stored key to keep.")
        self.connections[connection.connection_id] = connection
        if encrypted_api_key is not None:
            self.keys[connection.connection_id] = encrypted_api_key

    def get(self, connection_id: str, owner_id: str) -> ModelConnection:
        """Return the owner's connection or raise."""
        connection = self.connections.get(connection_id)
        if connection is None or connection.owner_id != owner_id:
            raise UnknownConnectionError(connection_id)
        return connection

    def list_for_owner(self, owner_id: str) -> list[ModelConnection]:
        """Return the owner's connections."""
        return sorted(
            (c for c in self.connections.values() if c.owner_id == owner_id),
            key=lambda c: c.connection_id,
        )

    def encrypted_api_key(self, connection_id: str, owner_id: str) -> str:
        """Return the stored encrypted key."""
        self.get(connection_id, owner_id)
        return self.keys[connection_id]


class ScriptedVerifier(ConnectionVerifier):
    """Returns a preset failure reason and records the targets it saw."""

    def __init__(self, failure: str | None = None) -> None:
        """Remember the failure to return."""
        self.failure = failure
        self.seen: list[TargetConnection] = []

    async def verify(self, target: TargetConnection) -> str | None:
        """Record the target and return the preset failure."""
        self.seen.append(target)
        return self.failure


def make_use_case(
    verifier: ConnectionVerifier | None = None,
) -> tuple[ManageConnections, InMemoryConnectionStore]:
    """Return a use case and its store, with the clock fixed."""
    store = InMemoryConnectionStore()
    use_case = ManageConnections(
        store,
        ReversingCipher(),
        verifier or ScriptedVerifier(),
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    return use_case, store


def test_added_key_is_stored_only_encrypted() -> None:
    """The plaintext key never reaches the store."""
    use_case, store = make_use_case()

    connection = use_case.add(
        OWNER, "https://api.invalid/v1", "model", "secret-key"
    )

    assert connection.status is ConnectionStatus.NOT_TESTED
    assert "secret-key" not in store.keys[connection.connection_id]


def test_update_without_a_key_keeps_the_stored_one() -> None:
    """Verify update without key keeps stored one."""
    use_case, store = make_use_case(ScriptedVerifier(failure=None))
    connection = use_case.add(
        OWNER, "https://api.invalid/v1", "model", "secret-key"
    )
    stored_key = store.keys[connection.connection_id]

    use_case.update(
        OWNER,
        connection.connection_id,
        "https://api.invalid/v2",
        "model",
        None,
    )

    assert store.keys[connection.connection_id] == stored_key
    assert (
        store.connections[connection.connection_id].status
        is ConnectionStatus.NOT_TESTED
    )


async def test_successful_verification_records_connected() -> None:
    """Verify successful verification records connected."""
    verifier = ScriptedVerifier(failure=None)
    use_case, _ = make_use_case(verifier)
    connection = use_case.add(
        OWNER, "https://api.invalid/v1", "model", "secret-key"
    )

    tested = await use_case.verify(OWNER, connection.connection_id)

    assert tested.status is ConnectionStatus.CONNECTED
    assert verifier.seen[-1].api_key == "secret-key"


async def test_failed_verification_records_the_reason() -> None:
    """A failing test stores the technical reason."""
    use_case, _ = make_use_case(ScriptedVerifier(failure="401 Unauthorized"))
    connection = use_case.add(
        OWNER, "https://api.invalid/v1", "model", "secret-key"
    )

    tested = await use_case.verify(OWNER, connection.connection_id)

    assert tested.status is ConnectionStatus.FAILED
    assert tested.failure_reason == "401 Unauthorized"


async def test_evaluation_target_requires_a_passed_test() -> None:
    """Verify evaluation target requires passed test."""
    use_case, _ = make_use_case(ScriptedVerifier(failure=None))
    connection = use_case.add(
        OWNER, "https://api.invalid/v1", "model", "secret-key"
    )

    with pytest.raises(ConnectionNotReadyError):
        use_case.target_for_evaluation(OWNER, connection.connection_id)

    await use_case.verify(OWNER, connection.connection_id)
    target = use_case.target_for_evaluation(OWNER, connection.connection_id)
    assert target.api_key == "secret-key"


def test_another_owner_cannot_reach_the_connection() -> None:
    """Connections are scoped to their owner."""
    use_case, _ = make_use_case()
    connection = use_case.add(
        OWNER, "https://api.invalid/v1", "model", "secret-key"
    )

    with pytest.raises(UnknownConnectionError):
        use_case.target_for_evaluation("user-2", connection.connection_id)
