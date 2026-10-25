# HARASS

**Hardened Arabic Red-Teaming and Safety Shield**

King Saud University  
College of Computer and Information Sciences  
Department of Information Technology  
Information Technology (IT) 496: Graduation Project-1  
First Semester 1448H - Fall 2026

---

## Introduction

HARASS is a web-based platform for evaluating the safety of
Arabic-supporting large language models (LLMs). It examines Adversarial
Attacks and Over-refusal across Modern Standard Arabic (MSA), Najdi,
Hijazi, Egyptian, and Levantine Arabic.

The HARASS Safety Dataset supports standardized baseline evaluation and
provides seed cases for HARASS Agent. The agent generates and adapts
single-turn and multi-turn test cases using assessment feedback from
previous model responses.

The results form the HARASS Benchmark for comparing six selected models
and guide HARASS Shield, which measures model safety before and after a
defensive intervention. HARASS aims to provide developers and model owners
with a systematic framework for identifying, measuring, and comparing
safety weaknesses in Arabic-supporting LLMs.

## Technologies Used

- **Frontend:** HyperText Markup Language (HTML), Cascading Style Sheets
  (CSS), and JavaScript
- **Model Connectivity:** OpenAI-compatible application programming
  interfaces (APIs)
- **Backend:** Python and FastAPI
- **Agentic Evaluation:** Python Risk Identification Tool for generative
  artificial intelligence (PyRIT) and HARASS evaluation components
- **Database:** PostgreSQL, SQLAlchemy, and Alembic
- **Authentication:** JSON Web Tokens (JWTs)
- **Containerization:** Docker Compose
- **Testing and Code Quality:** pytest, Ruff, mypy, and Import Linter
- **Continuous Integration:** GitHub Actions

## Launch Instructions

Create the environment configuration file:

```powershell
Copy-Item .env.example .env
```

Add the required configuration values to `.env`, then build and start the
services:

```powershell
docker compose up --build -d
```

Open the platform at `http://127.0.0.1:8000`.

Stop the services without deleting stored data:

```powershell
docker compose down
```

## Repository Structure

The project directories and file responsibilities are documented in
[`doc/file-structure.md`](doc/file-structure.md).

## Supervisor

**Prof. Hend Al-Khalifa**

## Authors

Project authors are listed in the [AUTHORS](AUTHORS) file.
