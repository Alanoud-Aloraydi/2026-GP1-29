"""Tests for authentication."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import Mock

import jwt
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from harass.application.accounts.authentication import (
    ManageAuthentication,
)
from harass.application.connections import ManageConnections
from harass.application.evaluation.run_service import ManageRuns
from harass.application.ports.connection_verifier import ConnectionVerifier
from harass.infrastructure.persistence.sqlalchemy_authentication import (
    SqlAlchemyAuthenticationStore,
)
from harass.infrastructure.persistence.sqlalchemy_connections import (
    SqlAlchemyConnectionStore,
)
from harass.infrastructure.persistence.sqlalchemy_request_limiter import (
    SqlAlchemyRequestLimiter,
)
from harass.infrastructure.security.fernet_secret_cipher import (
    FernetSecretCipher,
)
from harass.infrastructure.security.jwt_authentication import (
    JwtAuthenticationSecurity,
)
from harass.interfaces.api.app import create_app

SIGNING_KEY = "isolated-auth-test-signing-key-at-least-48-bytes-long"
PASSWORD = "test-only-long-password-2026"
MUTATION = {"X-Harass-Request": "1"}


@pytest.fixture
def client(
    request: pytest.FixtureRequest, database_factory: sessionmaker[Session]
) -> Iterator[TestClient]:
    """Provide isolated client."""
    factory = database_factory
    authentication = ManageAuthentication(
        SqlAlchemyAuthenticationStore(factory),
        JwtAuthenticationSecurity(SIGNING_KEY),
    )
    connections = ManageConnections(
        SqlAlchemyConnectionStore(factory),
        FernetSecretCipher(Fernet.generate_key().decode()),
        cast(ConnectionVerifier, Mock()),
    )
    with TestClient(
        create_app(
            connections,
            cast(ManageRuns, Mock()),
            authentication=authentication,
            request_limiter=SqlAlchemyRequestLimiter(factory, SIGNING_KEY)
            if getattr(request, "param", False)
            else None,
        )
    ) as http:
        yield http


def signup(client: TestClient, email: str = "first@example.test") -> str:
    """Create an isolated account."""
    response = client.post(
        "/auth/signup",
        headers=MUTATION,
        json={
            "full_name": "مستخدم اختبار",
            "email": email,
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201
    assert set(response.json()) == {
        "user_id",
        "full_name",
        "email",
        "email_verified",
    }
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert response.headers["cache-control"] == "no-store"
    return cast(str, client.cookies.get("harass_session"))


@pytest.mark.parametrize("client", [True], indirect=True)
def test_shared_limiter_rejects_requests_before_password_validation(
    client: TestClient,
) -> None:
    """Production admission control also counts malformed login bodies."""
    for _ in range(10):
        assert (
            client.post("/auth/login", headers=MUTATION, json={}).status_code
            == 422
        )
    response = client.post("/auth/login", headers=MUTATION, json={})
    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 60


def test_cookie_login_and_logout_revokes_replayed_token(
    client: TestClient,
) -> None:
    """Verify cookie login and logout revokes replayed token."""
    token = signup(client)
    assert client.get("/auth/me").status_code == 200
    assert client.post("/auth/logout", headers=MUTATION).status_code == 204
    client.cookies.set("harass_session", token)
    assert client.get("/auth/me").status_code == 401
    client.cookies.clear()
    response = client.post(
        "/auth/login",
        headers=MUTATION,
        json={"email": "FIRST@EXAMPLE.TEST", "password": PASSWORD},
    )
    assert response.status_code == 200


def test_connections_are_isolated_between_signed_in_accounts(
    client: TestClient,
) -> None:
    """Verify connections are isolated between signed in accounts."""
    signup(client)
    response = client.post(
        "/connections",
        headers=MUTATION,
        json={
            "base_url": "https://fixture.invalid/v1",
            "model_name": "fixture",
            "api_key": "fixture-key",
        },
    )
    assert response.status_code == 201
    first_id = client.get("/auth/me").json()["user_id"]
    assert response.headers["cache-control"] == "no-store"
    client.post("/auth/logout", headers=MUTATION)
    signup(client, "second@example.test")
    assert (
        client.get("/connections", headers={"X-Owner-Id": first_id}).json()
        == []
    )
    connection_id = response.json()["connection_id"]
    assert (
        client.put(
            f"/connections/{connection_id}",
            headers=MUTATION,
            json={
                "base_url": "https://fixture.invalid/v1",
                "model_name": "fixture",
            },
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "mutation_headers",
    [
        {},
        {**MUTATION, "Origin": "https://foreign.invalid"},
        {**MUTATION, "Sec-Fetch-Site": "cross-site"},
    ],
)
def test_cross_origin_or_unmarked_mutation_is_rejected(
    client: TestClient,
    mutation_headers: dict[str, str],
) -> None:
    """Verify cross origin or unmarked mutation is rejected."""
    assert (
        client.post(
            "/auth/login",
            headers=mutation_headers,
            json={"email": "a@b.test", "password": PASSWORD},
        ).status_code
        == 403
    )


def test_validation_never_echoes_credentials(client: TestClient) -> None:
    """Verify validation never echoes credentials."""
    response = client.post(
        "/auth/signup",
        headers=MUTATION,
        json={"full_name": "a", "email": "a@b.test", "password": "SECRET"},
    )
    assert response.status_code == 422 and "SECRET" not in response.text
    assert all("input" not in item for item in response.json()["detail"])


def test_tampered_expired_and_wrong_algorithm_tokens_are_rejected(
    client: TestClient,
) -> None:
    """Verify tampered expired and wrong algorithm tokens are rejected."""
    token = signup(client)
    claims = jwt.decode(
        token, SIGNING_KEY, algorithms=["HS256"], audience="harass-web"
    )
    claims["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    expired = jwt.encode(claims, SIGNING_KEY, algorithm="HS256")
    claims["exp"] = datetime.now(UTC) + timedelta(seconds=60)
    wrong_algorithm = jwt.encode(claims, SIGNING_KEY, algorithm="HS384")
    invalid_signature = jwt.encode(
        claims, "different-fixture-secret-32-bytes-long", algorithm="HS256"
    )
    for invalid in (expired, wrong_algorithm, invalid_signature):
        client.cookies.clear()
        client.cookies.set("harass_session", invalid)
        assert client.get("/connections").status_code == 401


def test_rate_limit_precedes_repeated_password_work(
    client: TestClient,
) -> None:
    """Even malformed repeated auth requests are bounded per client."""
    for _ in range(10):
        assert (
            client.post("/auth/login", headers=MUTATION, json={}).status_code
            == 422
        )
    response = client.post("/auth/login", headers=MUTATION, json={})
    assert (
        response.status_code == 429 and response.headers["Retry-After"] == "60"
    )


def test_wrong_credentials_and_duplicate_registration(
    client: TestClient,
) -> None:
    """Verify wrong credentials and duplicate registration."""
    signup(client)
    response = client.post(
        "/auth/login",
        headers=MUTATION,
        json={"email": "first@example.test", "password": "incorrect"},
    )
    assert response.status_code == 401
    duplicate = client.post(
        "/auth/signup",
        headers=MUTATION,
        json={
            "full_name": "مستخدم آخر",
            "email": "FIRST@EXAMPLE.TEST",
            "password": PASSWORD,
        },
    )
    assert duplicate.status_code == 400


def test_key_rotation_canonicalizes_legacy_ids_and_rejects_expiry() -> None:
    """Verify key rotation canonicalizes legacy ids and rejects expiry."""
    from harass.application.accounts.errors import (
        AuthenticationError,
    )
    from harass.domain.authentication import AuthenticationSession

    previous = "previous-test-key-32-bytes-minimum-material"
    old = JwtAuthenticationSecurity(previous)
    current = JwtAuthenticationSecurity(SIGNING_KEY, previous_keys=(previous,))
    session = AuthenticationSession(
        "10000000000040008000000000000001",
        "20000000000040008000000000000001",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    decoded = current.decode_session(old.encode_session(session))
    assert decoded.session_id == "10000000-0000-4000-8000-000000000001"
    assert decoded.user_id == "20000000-0000-4000-8000-000000000001"
    expired = AuthenticationSession(
        session.session_id,
        session.user_id,
        datetime.now(UTC) - timedelta(seconds=1),
    )
    with pytest.raises(AuthenticationError):
        current.decode_session(old.encode_session(expired))
    with pytest.raises(AuthenticationError):
        JwtAuthenticationSecurity(SIGNING_KEY).decode_session(
            old.encode_session(session)
        )


def test_body_limit_applies_before_parsing_and_security_headers(
    client: TestClient,
) -> None:
    """Verify body limit applies before parsing and security headers."""
    response = client.post(
        "/auth/login", headers=MUTATION, content=b"x" * 65537
    )
    assert response.status_code == 413
    response = client.get("/auth/me")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_weak_password_feedback_and_forbidden_ownership(
    client: TestClient,
) -> None:
    """Verify weak password feedback and forbidden ownership."""
    response = client.post(
        "/auth/signup",
        headers=MUTATION,
        json={
            "full_name": "Test User",
            "email": "weak@example.test",
            "password": "a" * 20,
        },
    )
    assert (
        response.status_code == 400
        and response.json()["code"] == "password_rejected"
    )
    response = client.post(
        "/auth/signup",
        headers=MUTATION,
        json={
            "full_name": "Test User",
            "email": "extra@example.test",
            "password": PASSWORD,
            "user_id": "attacker-supplied",
        },
    )
    assert response.status_code == 422


def test_refresh_rotation_replay_revokes_the_family(
    client: TestClient,
) -> None:
    """Replayed refresh credentials invalidate their session family."""
    signup(client)
    original = client.cookies.get("harass_refresh")
    assert original
    response = client.post("/auth/refresh", headers=MUTATION)
    assert response.status_code == 200
    successor = client.cookies.get("harass_refresh")
    access = client.cookies.get("harass_session")
    assert successor and successor != original and access
    replay = client.post(
        "/auth/refresh",
        headers={**MUTATION, "Cookie": "harass_refresh=" + original},
    )
    assert replay.status_code == 401
    client.cookies.clear()
    client.cookies.set("harass_session", access)
    assert client.get("/auth/me").status_code == 401


def test_forged_refresh_cannot_revoke_a_known_session(
    client: TestClient,
) -> None:
    """Knowing a session UUID alone cannot sign another session out."""
    access = signup(client)
    refresh = client.cookies.get("harass_refresh")
    assert refresh
    forged = refresh.split(".")[0] + "." + "x" * 43
    assert (
        client.post(
            "/auth/refresh",
            headers={**MUTATION, "Cookie": "harass_refresh=" + forged},
        ).status_code
        == 401
    )
    client.cookies.clear()
    client.cookies.set("harass_session", access)
    assert client.get("/auth/me").status_code == 200


def test_password_change_revokes_previous_access_and_refresh(
    client: TestClient,
) -> None:
    """Password replacement revokes every previous credential."""
    old_access = signup(client)
    old_refresh = client.cookies.get("harass_refresh")
    response = client.post(
        "/auth/password",
        headers=MUTATION,
        json={
            "current_password": PASSWORD,
            "new_password": "replacement-long-test-password-2026",
        },
    )
    assert response.status_code == 200
    assert client.get("/auth/me").status_code == 200
    assert len(client.get("/auth/sessions").json()) == 1
    client.cookies.clear()
    client.cookies.set("harass_session", old_access)
    assert client.get("/auth/me").status_code == 401
    assert (
        client.post(
            "/auth/refresh",
            headers={
                **MUTATION,
                "Cookie": "harass_refresh=" + str(old_refresh),
            },
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login",
            headers=MUTATION,
            json={"email": "first@example.test", "password": PASSWORD},
        ).status_code
        == 401
    )


def test_sessions_are_owner_scoped_and_logout_all_revokes_refresh(
    client: TestClient,
) -> None:
    """Scope session revocation to its owner and support global logout."""
    access = signup(client)
    first = client.get("/auth/sessions").json()[0]["session_id"]
    client.cookies.clear()
    signup(client, "second@example.test")
    assert (
        client.delete("/auth/sessions/" + first, headers=MUTATION).status_code
        == 204
    )
    assert (
        client.get(
            "/auth/me", headers={"Cookie": "harass_session=" + access}
        ).status_code
        == 200
    )
    refresh = client.cookies.get("harass_refresh")
    assert client.post("/auth/logout-all", headers=MUTATION).status_code == 204
    assert (
        client.post(
            "/auth/refresh",
            headers={**MUTATION, "Cookie": "harass_refresh=" + str(refresh)},
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "claim,value",
    [
        ("iss", "foreign"),
        ("aud", "foreign"),
        ("token_type", "refresh"),
        ("iat", True),
        ("nbf", 4102444800),
    ],
)
def test_access_claim_boundaries(
    client: TestClient, claim: str, value: object
) -> None:
    """Reject signed tokens with invalid identity or temporal claims."""
    token = signup(client)
    claims = jwt.decode(
        token, SIGNING_KEY, algorithms=["HS256"], audience="harass-web"
    )
    claims[claim] = value
    forged = jwt.encode(claims, SIGNING_KEY, algorithm="HS256")
    client.cookies.clear()
    client.cookies.set("harass_session", forged)
    assert client.get("/auth/me").status_code == 401
