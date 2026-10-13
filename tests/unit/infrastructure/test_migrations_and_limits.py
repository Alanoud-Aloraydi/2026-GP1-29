"""Migration preservation and shared admission control on isolated relational storage."""

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from harass.infrastructure.persistence.schema import migration_config, require_current_schema
from harass.infrastructure.persistence.sqlalchemy_request_limiter import SqlAlchemyRequestLimiter
from harass.infrastructure.persistence.tables import Base


def test_migrations_match_models_preserve_data_and_reverse(tmp_path: Path) -> None:
    """Explicit revisions match metadata and leave account data intact across archive changes."""
    engine = create_engine(f"sqlite:///{tmp_path / 'migrations.sqlite'}")
    config = migration_config()
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        require_current_schema(engine)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001_accounts_runs")
        connection.execute(
            text(
                "INSERT INTO users (user_id, full_name, email, password_hash) "
                "VALUES ('u1', 'Test User', 'user@example.invalid', 'synthetic-hash')"
            )
        )
        command.upgrade(config, "head")
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        assert (
            connection.scalar(text("SELECT full_name FROM users WHERE user_id = 'u1'"))
            == "Test User"
        )
        command.downgrade(config, "0001_accounts_runs")
        assert "generated_prompts" not in inspect(connection).get_table_names()
        assert connection.scalar(text("SELECT count(*) FROM users")) == 1
        command.upgrade(config, "head")
    require_current_schema(engine)
    engine.dispose()


def test_shared_limiter_counts_across_instances_and_resets(tmp_path: Path) -> None:
    """Two worker instances share one budget and reset at the next fixed window."""
    engine = create_engine(f"sqlite:///{tmp_path / 'limits.sqlite'}")
    Base.metadata.create_all(engine)
    now = [120.0]
    first = SqlAlchemyRequestLimiter(sessionmaker(engine), "test-secret", lambda: now[0])
    second = SqlAlchemyRequestLimiter(sessionmaker(engine), "test-secret", lambda: now[0])
    assert first.consume("auth:client", 2) == 0
    assert second.consume("auth:client", 2) == 0
    assert first.consume("auth:client", 2) == 60
    assert second.consume("verify:client", 2) == 0
    now[0] = 181
    assert second.consume("auth:client", 2) == 0
    engine.dispose()


def test_shared_limiter_admits_only_the_budget_under_concurrent_requests(tmp_path: Path) -> None:
    """Atomic increments prevent workers from each admitting the full request budget."""
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent.sqlite'}")
    Base.metadata.create_all(engine)
    limiter = SqlAlchemyRequestLimiter(sessionmaker(engine), "test-secret", lambda: 120)
    with ThreadPoolExecutor(max_workers=4) as pool:
        waits = list(pool.map(lambda _: limiter.consume("runs:user", 3), range(12)))
    assert waits.count(0) == 3
    assert waits.count(60) == 9
    engine.dispose()


def test_postgresql_migrations_render_without_credentials_or_a_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production dialect compiles both revisions without connecting to a database."""
    monkeypatch.setenv("HARASS_DATABASE_URL", "postgresql+psycopg://localhost/harass")
    config = migration_config()
    buffer = StringIO()
    config.output_buffer = buffer
    command.upgrade(config, "head", sql=True)
    sql = buffer.getvalue()
    assert "CREATE TABLE generated_prompts" in sql
    assert "CREATE TABLE prompt_findings" in sql
    assert "UNIQUE (run_id, case_id, variant_id, attempt_number)" in sql
