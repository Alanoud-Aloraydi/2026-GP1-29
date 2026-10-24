# HARASS

**Hardened Arabic Red-Teaming and Safety Shield**

HARASS evaluates the safety of Arabic-supporting large language models through baseline and adaptive single-turn testing. It measures adversarial compliance and over-refusal across Modern Standard Arabic, Najdi, Hijazi, Egyptian, and Levantine Arabic.

## Current capabilities

- Baseline evaluation using human-authored cases.
- Adaptive single-turn evaluation using authored prompt variants.
- Independent target and judge endpoints with OpenAI-compatible APIs.
- Repeated judge verdicts combined through majority voting.
- Durable evaluation jobs with checkpoints and recovery.
- Arabic safety reports with coverage, metrics, and judge evidence.
- Encrypted target credentials and revocable user sessions.

Adaptive multi-turn evaluation and generated prompt discovery are planned extensions.

## Architecture

HARASS follows a layered architecture:

```text
Bootstrap
    ↓
Interfaces and Infrastructure
    ↓
Application
    ↓
Domain
```

The API validates and queues evaluations in PostgreSQL. An independent worker processes queued runs through PyRIT and stores their results. PostgreSQL holds application records, while a dedicated Docker volume preserves PyRIT memory.

## Technology

- Python, FastAPI, PyRIT
- PostgreSQL, SQLAlchemy, Alembic
- HTML, CSS, JavaScript
- Docker Compose
- pytest, Ruff, mypy, Import Linter
- GitHub Actions

## Run

Copy the environment template and add the required credentials:

```powershell
Copy-Item .env.example .env
```

Start the application:

```powershell
docker compose up --build -d
```

Open `http://127.0.0.1:8000`, then check the services:

```powershell
docker compose ps
```

Stop the application without deleting stored data:

```powershell
docker compose down
```

Do not use `docker compose down -v` unless the PostgreSQL and PyRIT volumes should be deleted.

## Quality checks

```powershell
python -m pytest -q
ruff format --check src tests
ruff check src tests
mypy --no-incremental src
lint-imports
```

## Repository structure

See [`doc/file-structure.md`](doc/file-structure.md).

## Academic context

IT 496: Graduation Project-1<br>
Department of Information Technology<br>
College of Computer and Information Sciences<br>
King Saud University

**Supervisor:** Prof. Hend Al-Khalifa<br>
**Authors:** See [`AUTHORS`](AUTHORS).
