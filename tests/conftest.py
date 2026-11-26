"""Shared test fixtures."""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from harass.infrastructure.persistence.tables import Base

# Limit BLAS memory because these tests do not perform matrix work.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import pytest
from pyrit.setup import IN_MEMORY, initialize_pyrit_async


@pytest.fixture
async def pyrit_memory() -> None:
    """Initialize PyRIT with fresh in-memory storage."""
    await initialize_pyrit_async(memory_db_type=IN_MEMORY, silent=True)


def isolated_database_url() -> str | None:
    """Return the test PostgreSQL URL when its server accepts a connection.

    The isolated PostgreSQL of ``compose.test.yml`` is optional, so its tests
    run only when the variable names a server that answers. A variable left
    behind in a shell therefore skips them instead of failing every
    PostgreSQL test with a connection timeout.
    """
    url = os.environ.get("HARASS_TEST_DATABASE_URL", "").strip()
    if not url:
        return None
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect():
            return url
    except OperationalError:
        return None
    finally:
        engine.dispose()


POSTGRESQL_URL = isolated_database_url()
DIALECTS = ["sqlite", *(["postgresql"] if POSTGRESQL_URL else [])]


def pytest_report_header() -> str:
    """Report which databases this run covers, so a skip is never silent."""
    if POSTGRESQL_URL is None and os.environ.get("HARASS_TEST_DATABASE_URL", "").strip():
        return "databases: sqlite only; the test PostgreSQL server did not answer"
    return "databases: " + ", ".join(DIALECTS)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Run the storage tests on every database the environment offers."""
    for name in ("database_engine", "storage"):
        if name in metafunc.fixturenames:
            metafunc.parametrize(name, DIALECTS, indirect=True)


@pytest.fixture
def database_engine(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Engine]:
    """Provide an isolated disposable database namespace."""
    schema = "harass_test_" + uuid.uuid4().hex
    admin = None
    if request.param == "postgresql":
        url = str(POSTGRESQL_URL)
        admin = create_engine(url, connect_args={"connect_timeout": 5})
        with admin.begin() as connection:
            connection.execute(CreateSchema(schema))
        engine = create_engine(
            url, connect_args={"options": "-c search_path=" + schema, "connect_timeout": 5}
        )
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'isolated.sqlite'}")
    try:
        yield engine
    finally:
        engine.dispose()
        if admin is not None:
            with admin.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
            admin.dispose()


@pytest.fixture
def database_factory(database_engine: Engine) -> sessionmaker[Session]:
    """Create current tables only inside the isolated database namespace."""
    Base.metadata.create_all(database_engine)
    return sessionmaker(database_engine)
