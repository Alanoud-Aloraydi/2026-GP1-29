"""Tests for the administrator-only judge benchmark endpoints."""

from collections.abc import Iterator
from typing import Any, cast
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from harass.application.accounts.administrators import ManageAdministrators
from harass.application.accounts.authentication import ManageAuthentication
from harass.application.accounts.password_policy import PasswordPolicy
from harass.application.connections import ManageConnections
from harass.application.evaluation.run_service import ManageRuns
from harass.application.judge_benchmark_reports import JudgeBenchmarkReports
from harass.infrastructure.persistence.sqlalchemy_authentication import (
    SqlAlchemyAuthenticationStore,
)
from harass.infrastructure.persistence.sqlalchemy_judge_benchmarks import (
    SqlAlchemyJudgeBenchmarkStore,
)
from harass.infrastructure.security.jwt_authentication import (
    JwtAuthenticationSecurity,
)
from harass.interfaces.api.app import create_app

SIGNING_KEY = "isolated-admin-test-signing-key-at-least-48-bytes-long"
PASSWORD = "test-only-long-password-2026"
MUTATION = {"X-Harass-Request": "1"}
LIST_URL = "/admin/judge-benchmarks"


class Site:
    """The app under test with the services its tests also drive."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        """Wire the API to an isolated database."""
        self.accounts = SqlAlchemyAuthenticationStore(factory)
        self.administrators = ManageAdministrators(
            self.accounts,
            JwtAuthenticationSecurity(SIGNING_KEY),
            PasswordPolicy(),
        )
        self.reports = JudgeBenchmarkReports(
            SqlAlchemyJudgeBenchmarkStore(factory)
        )
        self.app = create_app(
            cast(ManageConnections, Mock()),
            cast(ManageRuns, Mock()),
            authentication=ManageAuthentication(
                self.accounts, JwtAuthenticationSecurity(SIGNING_KEY)
            ),
            judge_benchmarks=self.reports,
        )

    def member(self, email: str) -> TestClient:
        """Return a client signed in as a new plain user."""
        client = TestClient(self.app)
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
        return client

    def administrator(self, email: str) -> TestClient:
        """Return a client signed in as a new administrator."""
        client = self.member(email)
        self.administrators.grant(email)
        return client


@pytest.fixture
def site(database_factory: sessionmaker[Session]) -> Iterator[Site]:
    """Provide the app over an isolated database."""
    yield Site(database_factory)


def document() -> dict[str, Any]:
    """Build a minimal valid benchmark report."""
    return {
        "judge": {"model": "m", "rubric_fingerprint": "f"},
        "split": "dev",
        "trials": 1,
        "cases": 4,
    }


@pytest.mark.parametrize("path", [LIST_URL, f"{LIST_URL}/{uuid4()}"])
def test_anonymous_visitors_are_turned_away(site: Site, path: str) -> None:
    """Without a session there is no access, not even to know it exists."""
    assert TestClient(site.app).get(path).status_code == 401


@pytest.mark.parametrize("path", [LIST_URL, f"{LIST_URL}/{uuid4()}"])
def test_plain_users_are_forbidden(site: Site, path: str) -> None:
    """A signed-in user without the role cannot read benchmark data."""
    member = site.member("member@example.test")

    assert member.get(path).status_code == 403


def test_administrators_list_and_read_reports(site: Site) -> None:
    """An administrator sees summaries and then one full report."""
    admin = site.administrator("admin@example.test")
    assert admin.get(LIST_URL).json() == []
    report_id = site.reports.publish(document())

    listed = admin.get(LIST_URL).json()
    detail = admin.get(f"{LIST_URL}/{report_id}")

    assert [item["report_id"] for item in listed] == [report_id]
    assert detail.status_code == 200
    assert detail.json()["report"] == document()


@pytest.mark.parametrize("identifier", [str(uuid4()), "not-a-uuid"])
def test_unknown_or_malformed_report_ids_are_not_found(
    site: Site, identifier: str
) -> None:
    """Bad identifiers get a not-found, never a server error."""
    admin = site.administrator("admin@example.test")

    assert admin.get(f"{LIST_URL}/{identifier}").status_code == 404


def test_revoking_the_role_applies_to_the_open_session(site: Site) -> None:
    """The next request after a revocation is refused, with no re-login."""
    admin = site.administrator("admin@example.test")
    assert admin.get(LIST_URL).status_code == 200

    site.administrators.revoke("admin@example.test")

    assert admin.get(LIST_URL).status_code == 403


def test_account_details_show_the_role(site: Site) -> None:
    """The browser can learn the role, but it cannot set it."""
    member = site.member("member@example.test")
    admin = site.administrator("admin@example.test")

    assert member.get("/auth/me").json()["role"] == "user"
    assert admin.get("/auth/me").json()["role"] == "admin"


def test_signup_cannot_claim_the_role(site: Site) -> None:
    """A role in the signup body is rejected, not ignored."""
    response = TestClient(site.app).post(
        "/auth/signup",
        headers=MUTATION,
        json={
            "full_name": "مستخدم اختبار",
            "email": "sneaky@example.test",
            "password": PASSWORD,
            "role": "admin",
        },
    )

    assert response.status_code == 422
