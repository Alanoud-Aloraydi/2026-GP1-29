"""Tests for migrations and limits."""

import json
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from harass.infrastructure.persistence.schema import migration_config, require_current_schema
from harass.infrastructure.persistence.sqlalchemy_request_limiter import SqlAlchemyRequestLimiter
from harass.infrastructure.persistence.tables import Base


def test_migrations_match_models_preserve_data_and_reverse(database_engine: Engine) -> None:
    """Verify migrations match models preserve data and reverse."""
    engine = database_engine
    config = migration_config()
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        require_current_schema(engine)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001_accounts_runs")
        connection.execute(
            text(
                "INSERT INTO users (user_id, full_name, email, "
                "password_hash) VALUES "
                "('10000000-0000-4000-8000-000000000001', "
                "'Test User', 'user@example.invalid', "
                "'synthetic-hash')"
            )
        )
        command.upgrade(config, "head")
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        assert (
            connection.scalar(
                text(
                    "SELECT full_name FROM users WHERE user_id = "
                    "'10000000-0000-4000-8000-000000000001'"
                )
            )
            == "Test User"
        )
        assert (
            connection.scalar(
                text(
                    "SELECT role FROM users WHERE user_id = '10000000-0000-4000-8000-000000000001'"
                )
            )
            == "user"
        )
        command.downgrade(config, "0001_accounts_runs")
        assert "generated_prompts" not in inspect(connection).get_table_names()
        assert "role" not in {column["name"] for column in inspect(connection).get_columns("users")}
        assert connection.scalar(text("SELECT count(*) FROM users")) == 1
        command.upgrade(config, "head")
    require_current_schema(engine)
    engine.dispose()


def test_template_attempts_are_dropped_and_reports_keep_baseline_metrics(
    database_engine: Engine,
) -> None:
    """Verify 0014 keeps original-request attempts and rebuilds their report."""
    config = migration_config()
    user, connection_id, run = (f"{digit}0000000-0000-4000-8000-000000000001" for digit in "123")
    attempts = [
        (0, {"axis": "AT", "response_category": "REF", "attack_succeeded": False}),
        (1, {"axis": "AT", "response_category": "FUL", "attack_succeeded": True}),
    ]
    report = {
        "format_version": 3,
        "run_type": "agentic",
        "baseline_metrics": {"adversarial_breakdowns": {"variant": {}, "variety": {}}},
        "primary_metrics": {},
        "metrics": {},
    }
    with database_engine.begin() as database:
        config.attributes["connection"] = database
        command.upgrade(config, "0013_generation_attacks")
        database.execute(
            text(
                "INSERT INTO users (user_id, full_name, email, password_hash) "
                "VALUES (:user, 'Test User', 'user@example.invalid', 'synthetic-hash')"
            ),
            {"user": user},
        )
        database.execute(
            text(
                "INSERT INTO connections (connection_id, owner_id, base_url, model_name, "
                "status, encrypted_api_key) VALUES (:connection, :user, "
                "'https://target.invalid/v1', 'model', 'connected', 'secret')"
            ),
            {"connection": connection_id, "user": user},
        )
        database.execute(
            text(
                "INSERT INTO runs (run_id, owner_id, connection_id, target_model, status, "
                "created_at, completed_attempts) VALUES (:run, :user, :connection, 'model', "
                "'completed', '2026-01-01T00:00:00+00:00', 2)"
            ),
            {"run": run, "user": user, "connection": connection_id},
        )
        for attempt, document in attempts:
            database.execute(
                text(
                    "INSERT INTO run_outcomes (run_id, case_index, attempt_number, document, "
                    "metric_document) VALUES (:run, 0, :attempt, :document, :document)"
                ),
                {"run": run, "attempt": attempt, "document": json.dumps(document)},
            )
        database.execute(
            text("INSERT INTO reports (run_id, document) VALUES (:run, :document)"),
            {"run": run, "document": json.dumps(report)},
        )
        command.upgrade(config, "head")
        assert database.scalar(text("SELECT count(*) FROM run_outcomes")) == 1
        stored = database.scalar(text("SELECT document FROM reports"))
    rebuilt = json.loads(stored) if isinstance(stored, str) else stored
    assert rebuilt["format_version"] == 4 and "run_type" not in rebuilt
    assert rebuilt["metrics"]["adversarial_breakdowns"] == {"variety": {}}
    assert rebuilt["response_categories"] == {"AT": {"REF": 1}}


def test_generator_rows_gain_their_target_and_axis_and_reverse(database_engine: Engine) -> None:
    """Verify 0015 attributes prompts to their target and scopes lessons, and reverses."""
    config = migration_config()
    prompt = "40000000-0000-4000-8000-000000000001"
    with database_engine.begin() as database:
        config.attributes["connection"] = database
        command.upgrade(config, "0014_baseline_only_runs")
        database.execute(
            text(
                "INSERT INTO generator_cards (card_id, source, domain, risk, form, target, "
                "harmless, shape, created_at) VALUES ('C-1', 'baseline', 'DIN', 'VIO', "
                "'EXPLAIN', 'NONE', 'homonym', 'shape', '2026-01-01T00:00:00+00:00')"
            )
        )
        database.execute(
            text(
                "INSERT INTO generator_prompts (prompt_id, case_id, axis, cell_key, mechanism, "
                "card_id, round_index, written_text, localized_text, sent_text, objective, "
                "transform_names, content_sha256, reviewer_passed, reviewer_notes, intent_safe, "
                "attempts, created_at) VALUES (:prompt, 'OR-DIN-VIO-MSA-00001', 'OR', "
                "'OR-DIN-VIO-MSA', 'homonym', 'C-1', 0, 'w', 'l', 's', '', '[]', 'sha', "
                "TRUE, '{}', TRUE, 1, '2026-01-01T00:00:00+00:00')"
            ),
            {"prompt": prompt},
        )
        database.execute(
            text(
                "INSERT INTO generator_outcomes (prompt_id, target_model, response_category, "
                "response_text, category_rationale, attack_rationale, created_at) VALUES "
                "(:prompt, 'model', 'REF', '', '', '', '2026-01-01T00:00:00+00:00')"
            ),
            {"prompt": prompt},
        )
        for lesson, scope in (("L-1", "cell"), ("L-2", "risk_mechanism"), ("L-3", "risk")):
            database.execute(
                text(
                    "INSERT INTO generator_lessons (lesson_id, scope, scope_key, text, "
                    "target_model, uses, successes, created_at) VALUES (:lesson, :scope, 'k', "
                    "'t', 'model', 2, 1, '2026-01-01T00:00:00+00:00')"
                ),
                {"lesson": lesson, "scope": scope},
            )
        command.upgrade(config, "head")
        assert database.execute(
            text("SELECT target_model, device, lesson_ids FROM generator_prompts")
        ).one()[:2] == ("model", "homonym")
        assert database.execute(text("SELECT axis, device FROM generator_cards")).one() == (
            "OR",
            "homonym",
        )
        lessons = database.execute(
            text("SELECT lesson_id, scope, axis FROM generator_lessons ORDER BY lesson_id")
        ).all()
        assert [tuple(row) for row in lessons] == [("L-1", "cell", "OR"), ("L-2", "group", "OR")]
        assert database.scalar(text("SELECT kind FROM runs")) is None
        command.downgrade(config, "0014_baseline_only_runs")
        assert database.scalar(text("SELECT mechanism FROM generator_prompts")) == "homonym"
        assert database.scalar(text("SELECT harmless FROM generator_cards")) == "homonym"
        assert (
            database.scalar(text("SELECT scope FROM generator_lessons WHERE lesson_id = 'L-2'"))
            == "risk_mechanism"
        )
        command.upgrade(config, "head")


def test_shared_limiter_counts_across_instances_and_resets(tmp_path: Path) -> None:
    """Verify shared limiter counts across instances and resets."""
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
    """Verify shared limiter admits only budget under concurrent requests."""
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
    """Verify postgresql migrations render without credentials or server."""
    monkeypatch.setenv("HARASS_DATABASE_URL", "postgresql+psycopg://localhost/harass")
    config = migration_config()
    buffer = StringIO()
    config.output_buffer = buffer
    command.upgrade(config, "head", sql=True)
    sql = buffer.getvalue()
    assert "CREATE TABLE generated_prompts" in sql
    assert "DROP TABLE prompt_findings" in sql
    assert "PRIMARY KEY (run_id, case_index)" in sql
