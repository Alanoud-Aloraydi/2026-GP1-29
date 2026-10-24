"""Shared test fixtures."""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
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


@pytest.fixture(
    params=["sqlite"]
    + (["postgresql"] if os.environ.get("HARASS_TEST_DATABASE_URL") else [])
)
def database_engine(
    request: pytest.FixtureRequest, tmp_path: Path
) -> Iterator[Engine]:
    """Provide an isolated disposable database namespace."""
    schema = "harass_test_" + uuid.uuid4().hex
    admin = None
    if request.param == "postgresql":
        url = os.environ["HARASS_TEST_DATABASE_URL"]
        admin = create_engine(url, connect_args={"connect_timeout": 5})
        with admin.begin() as connection:
            connection.execute(CreateSchema(schema))
        engine = create_engine(
            url,
            connect_args={
                "options": "-c search_path=" + schema,
                "connect_timeout": 5,
            },
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
