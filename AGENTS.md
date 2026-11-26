# HARASS Engineering Instructions

## Source of truth

- Follow explicit user decisions first, then the current code of the working
  branch.
- Explain the implementation plan and obtain explicit approval before writing
  product code.
- When a new decision conflicts with an older one, follow the newest decision
  and state the change clearly.

## Change discipline

- Make the smallest coherent change that completes the approved behavior.
- Patch existing files in place. Do not replace whole files for small changes.
- Do not refactor unrelated code in a feature change.
- Do not add dependencies, abstractions, or future-facing placeholders
  without a current requirement.
- Delete code that nothing uses: functions, classes, styles, variables, and
  imports. Never leave dead code behind.
- Preserve user changes. Do not commit or push unless the user explicitly asks.

## Design principles

- Apply KISS, YAGNI, DRY, separation of concerns, and single responsibility.
- Prefer composition and constructor injection over inheritance and hidden
  service location.
- Create an abstraction only at a meaningful boundary or after real reuse.
- Keep functions focused and use early returns to avoid deep nesting.
- Split files by cohesive responsibility; do not enforce one class per file
  blindly.
- Prefer explicit, readable code over clever or compressed code.
- Use descriptive names that state meaning; avoid abbreviations.
- Keep code short: no length without purpose.
- Represent invalid states with types, enums, and database constraints.

## Architecture

- Keep the layers enforced by `lint-imports`: `bootstrap` composes,
  `interfaces` and `infrastructure` adapt, `application` orchestrates,
  `domain` holds rules.
- `domain` and `application` never import PyRIT, FastAPI, SQLAlchemy,
  Pydantic, or cryptography.
- Keep routes limited to transport concerns: parsing, authorization, service
  calls, and response construction.
- Reach every external model, judge, or service through a port in
  `application/ports` and an adapter in `infrastructure`.

## Python style

- Follow PEP 8 as enforced by `ruff`, with lines of at most 100 characters.
- Keep every function at most 79 lines; a test enforces it outside
  migrations, which are applied history and never rewritten.
- Use type hints everywhere; code must pass `mypy` in strict mode.
- Use `snake_case` for functions, variables, and modules, `PascalCase` for
  classes, and `UPPER_CASE` for constants.
- Every module, class, and function has a docstring: a real English sentence
  that states its purpose, not a restatement of its name (Google convention).
- End every file with a single newline. Use spaces, never tabs.
- A file meant to run directly (for example under `tools/`) starts with
  `#!/usr/bin/env python3` and is executable. Package modules run through
  `python -m` and carry no shebang.
- Shell scripts start with `#!/bin/sh` (or `#!/bin/bash` when needed),
  followed by a comment that states the script's purpose, and use
  `set -eu`.

## Complexity (Big-O)

- Choose data structures for the access pattern: sets and dicts for
  membership and lookup, not repeated list scans.
- Avoid quadratic or worse work over unbounded input such as all outcomes of
  a run. Prefer one pass with grouping (`defaultdict`, `Counter`).
- State time and space complexity in the docstring of any non-trivial
  algorithm whose input size is not fixed, for example `O(n * m)` for
  ROUGE-L over two token sequences.
- Do not load unbounded data into memory when streaming or paging is
  possible; reports and evidence stay paginated.
- Count every model call in a judgment: retries, votes, and escalations are
  part of the per-case cost and the 1000-cases-per-hour budget.

## Judge and evaluation rules

- Keep request safety, response safety, refusal, and attack success as
  separate judgments.
- AT verdicts are `TRUE`, `FALSE`, or `ABSTAIN` against the case
  `Criterion`; a missing refusal alone never means attack success.
- OR keeps `Response_Category` (`FUL`, `PRF`, `REF`, `UNC`) separate from
  `Overrefusal_Flag`, and records `Request_Safe`.
- Store human labels and judge verdicts in separate fields with their source;
  never merge them into one value.
- Keep the judge's native output, model version, prompt version, and latency
  with every verdict.
- Never fabricate confidence for a judge that returns no probabilities.
- Unscored and abstained outcomes stay out of rate denominators and are
  reported in coverage.

## Security and privacy

- Never log API keys, tokens, passwords, or prompt and response text.
- Never expose provider exception text, response bodies, or SQL errors to
  users; classify failures instead.
- Keep secrets in `.env` only; `.env.example` holds names and safe defaults.
- Avoid broad exception handling in business logic.

## Database and migrations

- A feature migration includes every schema change the feature needs:
  tables, indexes, constraints, and data backfills.
- Review and correct any Alembic autogenerate output by hand.
- Name every constraint and index consistently.
- Enforce row-local invariants with `NOT NULL`, `CHECK`, `UNIQUE`, and
  foreign keys; the database is the final integrity boundary.
- Test migrations on the isolated PostgreSQL from `compose.test.yml`. Never
  destroy development data to test downgrades.

## Docker

- Keep one non-root application image for `migrate`, `api`, and `worker`;
  do not add a service image without a current requirement.
- Keep the `.dockerignore` allowlist: only files the image needs enter the
  build context, and `.env` files never do.
- Keep containers read-only, with all capabilities dropped and
  `no-new-privileges`.
- Bind published ports to `127.0.0.1` unless the user approves otherwise.
- Required secrets use `${NAME:?message}` so a missing value fails fast.
- Validate changes with `docker build --check .` and
  `docker compose config -q`.

## Frontend

- Plain HTML, CSS, and JavaScript; no framework without user approval.
- Pages are Arabic and right-to-left; escape every dynamic value through the
  shared UI helpers.
- Define every color once as a CSS variable in `styles.css`; JavaScript
  selects styles by class name and never embeds color values.
- When a frontend asset changes, raise the `?v=` query in the HTML pages.
- Keep pages accessible: real buttons, links, and labels, visible focus, and
  touch targets of at least 44 px.

## Comments

- Write comments and docstrings in clear English.
- Explain a non-obvious reason, invariant, concurrency rule, or safety
  decision; comments say why, not what.
- Never write notes or messages to the user inside code. Do not narrate
  obvious syntax or leave tutorial text.
- Avoid vague TODO comments and redundant documentation.

## Testing and delivery

- Test behavior rather than private implementation details.
- Cover success, empty, validation, authorization, conflict, and error paths
  in proportion to risk.
- Before reporting work as done, run the CI checks:
  `ruff format --check src tests`, `ruff check src tests`,
  `mypy src tests`, `lint-imports`, `python -m pytest -q`, and
  `pnpm --dir frontend run check` for frontend changes.
- Report any check that was not run and why.
