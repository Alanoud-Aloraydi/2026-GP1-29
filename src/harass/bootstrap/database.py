"""Shared startup steps: the environment file, the database and the judge slot."""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from harass.infrastructure.persistence.schema import require_current_schema

ENVIRONMENT_FILE = Path(".env")
DEFAULT_API_PORT = 8000


def load_environment() -> None:
    """Read local settings without overriding variables already set."""
    load_dotenv(ENVIRONMENT_FILE)


def open_engine(database_url: str) -> Engine:
    """Connect to the database, refusing a schema that needs a migration."""
    engine = create_engine(database_url, connect_args={"connect_timeout": 10}, pool_pre_ping=True)
    try:
        require_current_schema(engine)
    except Exception:
        engine.dispose()
        raise
    return engine


@contextmanager
def database_sessions(database_url: str) -> Iterator[sessionmaker[Session]]:
    """Provide sessions for one command and release the connections after it."""
    engine = open_engine(database_url)
    try:
        yield sessionmaker(engine)
    finally:
        engine.dispose()


def judge_slot(judge_server_url: str) -> str:
    """Name the shared judge slot by its server, without storing the address."""
    return hashlib.sha256(judge_server_url.encode("utf-8")).hexdigest()
