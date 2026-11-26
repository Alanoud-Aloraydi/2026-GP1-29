# File structure

Maintained source files and their responsibilities. Generated files, local secrets, virtual environments, caches, and IDE settings are excluded.

```text
/
├── .github/
│   └── workflows/
│       └── ci.yml                                                  # Python, frontend and PostgreSQL contract checks for every proposed revision.
├── config/
│   ├── docker/
│   │   └── init-database.sh                                        # Create a dedicated application role; database administration stays separate.
│   └── templates/
│       ├── at_direct_plain.yaml                                    # Authored at direct plain evaluation prompt template.
│       ├── at_direct_steps.yaml                                    # Authored at direct steps evaluation prompt template.
│       ├── at_distraction_heading.yaml                             # Authored at distraction heading evaluation prompt template.
│       ├── at_distraction_sections.yaml                            # Authored at distraction sections evaluation prompt template.
│       ├── at_obfuscation_payload.yaml                             # Authored at obfuscation payload evaluation prompt template.
│       ├── at_obfuscation_quoted.yaml                              # Authored at obfuscation quoted evaluation prompt template.
│       ├── at_persuasion_consistency.yaml                          # Authored at persuasion consistency evaluation prompt template.
│       ├── at_persuasion_urgency.yaml                              # Authored at persuasion urgency evaluation prompt template.
│       ├── at_poisoned_note.yaml                                   # Authored at poisoned note evaluation prompt template.
│       ├── at_poisoned_record.yaml                                 # Authored at poisoned record evaluation prompt template.
│       ├── at_role_dialogue.yaml                                   # Authored at role dialogue evaluation prompt template.
│       ├── at_role_expert.yaml                                     # Authored at role expert evaluation prompt template.
│       ├── or_delimited.yaml                                       # Authored or delimited evaluation prompt template.
│       ├── or_plain.yaml                                           # Authored or plain evaluation prompt template.
│       ├── or_readability.yaml                                     # Authored or readability evaluation prompt template.
│       └── or_verbatim.yaml                                        # Authored or verbatim evaluation prompt template.
├── data/
│   ├── judge_benchmarks/
│   │   ├── d1-2b_bf16_dev_2026-11-03.json                          # Judge benchmark report; publish with harass-reports publish.
│   │   ├── deepseek-r1-8b_Q4_K_M_dev_2026-11-03.json               # Judge benchmark report; publish with harass-reports publish.
│   │   ├── escalating_dev_2026-11-05_chunked.json                  # Judge benchmark report; publish with harass-reports publish.
│   │   ├── faisal-nf4_dev_2026-11-04.json                          # Judge benchmark report; publish with harass-reports publish.
│   │   ├── qwen3guard-0.6b-bf16_dev_2026-11-04.json                # Judge benchmark report; publish with harass-reports publish.
│   │   ├── qwen3guard-4b-nf4_dev_2026-11-04.json                   # Judge benchmark report; publish with harass-reports publish.
│   │   ├── qwen3guard-escalating_dev_2026-11-05.json               # Judge benchmark report; publish with harass-reports publish.
│   │   ├── qwenguard-small_dev_2026-11-05_chunked.json             # Judge benchmark report; publish with harass-reports publish.
│   │   ├── qwenguard_dev_2026-11-05_chunked.json                   # Judge benchmark report; publish with harass-reports publish.
│   │   ├── qwenguard_test_2026-11-07.err                           # Error output kept beside its judge benchmark report.
│   │   ├── qwenguard_test_2026-11-07.json                          # Judge benchmark report; publish with harass-reports publish.
│   │   ├── shieldstral_dev_2026-11-07.json                         # Judge benchmark report; publish with harass-reports publish.
│   │   └── split_dev_2026-11-05.json                               # Judge benchmark report; publish with harass-reports publish.
│   └── baseline_dataset.xlsx                                       # Baseline evaluation cases for both axes.
├── doc/
│   └── file-structure.md                                           # Documents the maintained repository structure.
├── frontend/
│   ├── assets/
│   │   ├── css/
│   │   │   └── styles.css                                          # Shared design tokens, layout primitives and component styles.
│   │   ├── images/
│   │   │   └── harass-logo.png                                     # Stores the HARASS product mark.
│   │   └── js/
│   │       ├── core/
│   │       │   ├── api-client.js                                   # Same-origin API transport with bounded requests and serialized session renewal.
│   │       │   ├── bootstrap.js                                    # Shared page layout, account initialization and page-controller start.
│   │       │   ├── forms.js                                        # Shared form submission, busy buttons and list pagination.
│   │       │   └── ui.js                                           # Escaped markup, shared formats and page feedback used by every view.
│   │       ├── pages/
│   │       │   ├── account-email.js                                # Password recovery and email verification forms with fragment-only link tokens.
│   │       │   ├── account.js                                      # Profile, activity summary and the account's sessions.
│   │       │   ├── auth.js                                         # Login and signup forms.
│   │       │   ├── connections.js                                  # Model connections: the paged list and the add or edit form.
│   │       │   ├── dashboard.js                                    # Dashboard: account totals, latest runs and the next step.
│   │       │   ├── evaluation.js                                   # New evaluation form with a live summary of the choices.
│   │       │   ├── history.js                                      # Paged list of the account's evaluations.
│   │       │   ├── judges.js                                       # Administrator page that compares published judge benchmark reports.
│   │       │   └── report.js                                       # Evaluation page: live progress while a run works, then its report.
│   │       └── views/
│   │           ├── judge-comparison.js                             # Judge benchmark reports: summary table and full report.
│   │           ├── report-evidence.js                              # Attempt transcripts, verdict evidence and evidence pagination.
│   │           ├── report.js                                       # Evaluation metrics, coverage and report composition.
│   │           └── run.js                                          # Evaluation lifecycle, progress and the list of runs.
│   ├── account.html                                                # Profile interface for the HARASS evaluation service.
│   ├── connections.html                                            # Connections interface for the HARASS evaluation service.
│   ├── dashboard.html                                              # Dashboard interface for the HARASS evaluation service.
│   ├── evaluation-run.html                                         # Evaluation run interface for the HARASS evaluation service.
│   ├── evaluation-setup.html                                       # Evaluation setup interface for the HARASS evaluation service.
│   ├── forgot-password.html                                        # Feature-gated account action using a single-use email link.
│   ├── history.html                                                # History interface for the HARASS evaluation service.
│   ├── htmlvalidate.config.cjs                                     # Validate native HTML while allowing named checkbox groups.
│   ├── index.html                                                  # Home interface for the HARASS evaluation service.
│   ├── judges.html                                                 # Administrator comparison of judge benchmark reports.
│   ├── login.html                                                  # Login interface for the HARASS evaluation service.
│   ├── model-configuration.html                                    # Model configuration interface for the HARASS evaluation service.
│   ├── package.json                                                # Pins the frontend quality tools and marks the scripts as ES modules.
│   ├── reset-password.html                                         # Feature-gated account action using a single-use email link.
│   ├── signup.html                                                 # Signup interface for the HARASS evaluation service.
│   ├── stylelint.config.cjs                                        # Detect invalid CSS and duplicate declarations without a styling library.
│   └── verify-email.html                                           # Feature-gated account action using a single-use email link.
├── src/
│   └── harass/
│       ├── application/
│       │   ├── accounts/
│       │   │   ├── __init__.py                                     # Account authentication and recovery use cases.
│       │   │   ├── administrators.py                               # Grant and revoke administrator access and reset forgotten passwords.
│       │   │   ├── authentication.py                               # Create accounts, authenticate credentials, and revoke sessions.
│       │   │   ├── errors.py                                       # Public account failures without credential or provider details.
│       │   │   ├── password_policy.py                              # Shared password requirements for registration, changes and recovery.
│       │   │   └── recovery.py                                     # Issue and consume purpose-bound account verification and reset links.
│       │   ├── evaluation/
│       │   │   ├── __init__.py                                     # Evaluation admission, orchestration and durable worker execution.
│       │   │   ├── contracts.py                                    # Run parameters, requests and reports exchanged with the evaluation use case.
│       │   │   ├── outcome_codec.py                                # Decode stored outcomes for evidence and statistical analysis.
│       │   │   ├── run_service.py                                  # Manage evaluation admission, lifecycle and stored reports.
│       │   │   ├── runner.py                                       # Select paired seeds and compute auditable evaluation reports.
│       │   │   ├── variant_engine.py                               # Execute adaptive evaluations with durable attempt reservations.
│       │   │   └── worker.py                                       # Renewable worker execution outside the HTTP application lifecycle.
│       │   ├── generation/                                         # Orchestration of the agentic prompt generator.
│       │   │   ├── __init__.py                                     # Orchestration of the agentic prompt generator.
│       │   │   ├── contracts.py                                    # What a generation round is asked for and what it reports back.
│       │   │   ├── drafting.py                                     # Write one prompt for one cell and carry it through the writing gates.
│       │   │   ├── generation_service.py                           # Run one round of the agentic over-refusal prompt generator.
│       │   │   └── librarian.py                                    # Distil lessons from a finished round at two scopes.
│       │   ├── ports/
│       │   │   ├── __init__.py                                     # Abstract interfaces that outer layers implement.
│       │   │   ├── accounts.py                                     # Ports for accounts, sessions, account-action mail and request limits.
│       │   │   ├── connections.py                                  # Ports for stored model connections, their verification and key encryption.
│       │   │   ├── evaluation.py                                   # Ports for evaluation cases, prompt recipes, attempts, engines and journals.
│       │   │   ├── generation.py                                   # Ports the prompt generator reaches its models and its store through.
│       │   │   ├── judge_report_store.py                           # Persistence contract for published judge benchmark reports.
│       │   │   └── runs.py                                         # Ports for reading runs, admitting them and leasing them to workers.
│       │   ├── reporting/
│       │   │   ├── __init__.py                                     # Framework-independent report projections and serialization.
│       │   │   ├── document.py                                     # Serialize evaluation reports into JSON-compatible documents.
│       │   │   └── labels.py                                       # Arabic labels under which verdicts and metrics are presented to readers.
│       │   ├── __init__.py                                         # Use cases orchestrating the domain through abstract ports.
│       │   ├── connections.py                                      # Use case: add, update, list and test clients' model connections.
│       │   ├── errors.py                                           # Errors that are part of the application port contracts.
│       │   └── judge_reports.py                                    # Publish judge benchmark reports and read them for administrators.
│       ├── bootstrap/
│       │   ├── __init__.py                                         # Composition root wiring adapters to ports.
│       │   ├── accounts.py                                         # Compose account authentication and optional mail delivery at startup.
│       │   ├── administrators.py                                   # Composition root of the administrator access command.
│       │   ├── api.py                                              # Composition root of the HTTP API.
│       │   ├── database.py                                         # Shared startup steps: the environment file, the database and the judge slot.
│       │   ├── evaluation.py                                       # Compose evaluation dependencies and configuration fingerprints.
│       │   ├── execution_profile.py                                # Fingerprint execution inputs before admitting or resuming durable work.
│       │   ├── generation.py                                       # Composition root of the prompt generation command.
│       │   ├── health.py                                           # Bounded health probes for the HTTP process and durable worker heartbeat.
│       │   ├── migrate.py                                          # Apply explicit database migrations as a standalone deployment step.
│       │   ├── reports.py                                          # Composition root of the judge report publishing command.
│       │   └── worker.py                                           # Independent durable evaluation worker sharing the API's PostgreSQL queue.
│       ├── domain/
│       │   ├── __init__.py                                         # Define framework-independent Arabic safety evaluation rules.
│       │   ├── account_action.py                                   # Expiring, single-use account actions with purpose-bound credentials.
│       │   ├── adaptive_controller.py                              # Implement Beta-Bernoulli Thompson recipe selection.
│       │   ├── adaptive_metrics.py                                 # Measure observed discovery under adaptive selection.
│       │   ├── authentication.py                                   # User identities and revocable authentication sessions.
│       │   ├── case_identifier.py                                  # Case identifiers of the HARASS coding system.
│       │   ├── case_outcome.py                                     # Judged outcome of sending one case using an auditable prompt recipe.
│       │   ├── case_selection.py                                   # Criteria for selecting evaluation cases.
│       │   ├── comprehension.py                                    # Rule signals that a target response did not understand its prompt.
│       │   ├── errors.py                                           # Errors raised when domain invariants are violated.
│       │   ├── evaluation_case.py                                  # Evaluation cases sent to the target model.
│       │   ├── evaluation_plan.py                                  # Select paired cases, recipes and execution policy.
│       │   ├── evaluation_run.py                                   # The lifecycle record of one evaluation run managed by the backend.
│       │   ├── generation/                                         # Domain rules for generating evaluation prompts.
│       │   │   ├── __init__.py                                     # Domain rules for generating evaluation prompts (over-refusal and attack).
│       │   │   ├── briefs.py                                       # Turn a cell and a pattern card into the Arabic briefs the models see.
│       │   │   ├── cells.py                                        # The over-refusal cell grid and the planner that schedules a round.
│       │   │   ├── dialect.py                                      # Check an Arabic prompt against the variety it claims.
│       │   │   ├── history.py                                      # What the generator has learned so far about one target model.
│       │   │   ├── pattern_card.py                                 # Pattern cards: why a seed prompt was refused, abstracted from its text.
│       │   │   ├── review.py                                       # The form reviewer's verdict on one generated prompt.
│       │   │   └── transforms.py                                   # Auditable Arabic surface transforms with explicit composition properties.
│       │   ├── judge_report.py                                     # Published benchmark reports of response judges.
│       │   ├── metrics.py                                          # Safety metrics computed from judged case outcomes.
│       │   ├── model_connection.py                                 # A client's saved connection to a model under evaluation.
│       │   ├── owasp_scenario.py                                   # Define synthetic single-turn OWASP LLM scenarios.
│       │   ├── prompt_variant.py                                   # Define framework-independent prompt variants and recipe contracts.
│       │   ├── seed_library.py                                     # Group linguistic variants by unambiguous base-case identity.
│       │   ├── target_connection.py                                # Connection details of the model under evaluation.
│       │   └── taxonomy.py                                         # Classification codes of the HARASS evaluation taxonomy.
│       ├── infrastructure/
│       │   ├── dataset/
│       │   │   ├── __init__.py                                     # Readers of the project dataset.
│       │   │   ├── card_file.py                                    # Read the generator's pattern cards from a JSON lines file.
│       │   │   ├── spreadsheet_seed_source.py                      # Seed source reading evaluation cases from the dataset spreadsheet.
│       │   │   └── yaml_variant_catalog.py                         # Compose bounded prompt variants from authored YAML recipes.
│       │   ├── http/
│       │   │   ├── __init__.py                                     # HTTP adapters.
│       │   │   ├── endpoint_policy.py                              # Pin approved outbound addresses while retaining TLS checks.
│       │   │   ├── generation_judges.py                            # The model-backed judges of the prompt generator.
│       │   │   ├── model_gateway.py                                # One gateway to the generator's writing and judging models.
│       │   │   ├── openai_connection_verifier.py                   # Verify model availability and generation on compatible endpoints.
│       │   │   └── qwenguard_moderation.py                         # One moderation request to the Qwen3Guard server, read into its labels.
│       │   ├── mail/
│       │   │   ├── __init__.py                                     # Optional account-mail configuration and SMTP delivery adapters.
│       │   │   ├── settings.py                                     # Validate SMTP configuration only when account email is enabled.
│       │   │   └── smtp_mailer.py                                  # Send account links through authenticated, certificate-verified SMTP.
│       │   ├── persistence/
│       │   │   ├── migrations/
│       │   │   │   ├── versions/
│       │   │   │   │   ├── 0001_accounts_runs.py                   # Create accounts, connections and evaluation storage.
│       │   │   │   │   ├── 0002_research_limits.py                 # Add internal research archive and shared request limits.
│       │   │   │   │   ├── 0003_durable_runs.py                    # Add durable jobs, fenced worker slots and paged attempt evidence.
│       │   │   │   │   ├── 0004_execution_controls.py              # Connection revisions and explicit evaluation lifecycle history.
│       │   │   │   │   ├── 0005_integrity_uuid.py                  # Native PostgreSQL entity identifiers and ownership integrity.
│       │   │   │   │   ├── 0006_rotating_sessions.py               # Add bounded refresh-token rotation to revocable account sessions.
│       │   │   │   │   ├── 0007_account_actions.py                 # Add optional email verification and hashed single-use account actions.
│       │   │   │   │   ├── 0008_user_roles.py                      # Add the account role, defaulting every existing account to a plain user.
│       │   │   │   │   ├── 0009_judge_benchmark_reports.py         # Store published judge benchmark reports for administrators.
│       │   │   │   │   ├── 0010_generator_benchmark_reports.py     # Store published prompt-generator benchmark reports for administrators.
│       │   │   │   │   └── 0011_drop_generator_reports.py          # Drop the prompt-generator benchmark reports, which the site no longer shows.
│       │   │   │   │   ├── 0012_generation.py                      # Store the prompt generator's cards, prompts, outcomes and lessons.
│       │   │   │   ├── env.py                                      # Run migrations using environment or injected connection settings.
│       │   │   │   └── script.py.mako                              # Defines the template used to generate Alembic revisions.
│       │   │   ├── tables/
│       │   │   │   ├── __init__.py                                 # Register all ORM mappings against one shared metadata collection.
│       │   │   │   ├── accounts.py                                 # Account identities, revocable sessions, expiring actions and request limits.
│       │   │   │   ├── base.py                                     # Shared ORM metadata and portable entity identifier storage.
│       │   │   │   ├── connections.py                              # Owned model connection metadata and encrypted credentials.
│       │   │   │   ├── evaluations.py                              # Evaluation lifecycle, reports, durable worker checkpoints and research findings.
│       │   │   │   ├── generation.py                               # Tables of the prompt generator: its cards, prompts, outcomes and lessons.
│       │   │   │   └── judge_reports.py                            # Judge benchmark reports published for administrators.
│       │   │   ├── __init__.py                                     # PostgreSQL persistence for project-level data.
│       │   │   ├── job_sessions.py                                 # Transactional job storage and worker ownership checks.
│       │   │   ├── prompt_archive.py                               # Internal research archival inside the report transaction.
│       │   │   ├── row_mapping.py                                  # Convert persisted evaluation rows and restore UTC timestamps.
│       │   │   ├── schema.py                                       # Explicit schema readiness checks before production storage is used.
│       │   │   ├── session_factory.py                              # Type contract for independent SQLAlchemy database sessions.
│       │   │   ├── sqlalchemy_account_actions.py                   # Consume account actions atomically and revoke stale credentials.
│       │   │   ├── sqlalchemy_authentication.py                    # Persist accounts and revocable sessions transactionally.
│       │   │   ├── sqlalchemy_connections.py                       # Persist owned model connections and encrypted credentials.
│       │   │   ├── sqlalchemy_generation.py                        # Persist the prompt generator's cards, prompts, outcomes and lessons.
│       │   │   ├── sqlalchemy_jobs.py                              # Persist queued work with shared judge admission and leases.
│       │   │   ├── sqlalchemy_journal.py                           # Commit attempt evidence under fenced worker leases.
│       │   │   ├── sqlalchemy_judge_reports.py                     # Persist published judge benchmark reports.
│       │   │   ├── sqlalchemy_request_limiter.py                   # Database-backed fixed-window counters shared by all API workers.
│       │   │   ├── sqlalchemy_runs.py                              # Read evaluation histories and their report documents.
│       │   │   └── upsert.py                                       # Build atomic inserts for PostgreSQL and SQLite.
│       │   ├── pyrit/
│       │   │   ├── scoring/
│       │   │   │   ├── __init__.py                                 # Judge-model scorers built on PyRIT.
│       │   │   │   ├── guard_scorers.py                            # PyRIT scorers that take their verdicts from the Qwen3Guard server.
│       │   │   │   └── synthetic_disclosure_scorer.py              # Deterministic synthetic disclosure judging without another model request.
│       │   │   ├── __init__.py                                     # Adapters built on PyRIT.
│       │   │   ├── attempt_outcome.py                              # Conversion of stored PyRIT verdicts into auditable application outcomes.
│       │   │   ├── judge_request_audit.py                          # Count judge HTTP calls without recording request content.
│       │   │   ├── target_builder.py                               # Build PyRIT targets for the evaluated models.
│       │   │   └── variant_attempt_executor.py                     # Execute isolated PyRIT attempts with request-aware scoring.
│       │   ├── reporting/
│       │   │   └── __init__.py                                     # Report export adapters.
│       │   ├── security/
│       │   │   ├── __init__.py                                     # Secret protection adapters.
│       │   │   ├── common_passwords.sha256                         # Stores blocked-password digests without plaintext passwords.
│       │   │   ├── fernet_secret_cipher.py                         # Secret cipher based on Fernet authenticated symmetric encryption.
│       │   │   ├── jwt_authentication.py                           # PyJWT session signing and OWASP-recommended scrypt password hashing.
│       │   │   └── password_blocklist.py                           # Screen password hashes locally against configured blocklists.
│       │   ├── __init__.py                                         # Framework and driver adapters implementing the application ports.
│       │   └── settings.py                                         # System settings read from environment variables.
│       ├── interfaces/
│       │   ├── api/
│       │   │   ├── accounts/
│       │   │   │   ├── __init__.py                                 # HTTP account, session and recovery interfaces.
│       │   │   │   ├── cookies.py                                  # Transport access and refresh credentials in HTTP-only cookies.
│       │   │   │   ├── dependencies.py                             # Resolve account ownership from signed, revocable session cookies.
│       │   │   │   ├── policy.py                                   # Same-origin mutation checks and shared authentication request limits.
│       │   │   │   ├── recovery_routes.py                          # Feature-gated account-email routes with generic delivery acknowledgments.
│       │   │   │   ├── recovery_schemas.py                         # Bound recovery inputs without exposing action tokens in diagnostics.
│       │   │   │   ├── routes.py                                   # Same-origin cookie authentication routes and owner dependency.
│       │   │   │   └── schemas.py                                  # Validated account inputs and public session representations.
│       │   │   ├── admin/
│       │   │   │   ├── __init__.py                                 # HTTP interfaces for administrator-only endpoints.
│       │   │   │   └── routes.py                                   # Read-only judge benchmark endpoints for administrators.
│       │   │   ├── connections/
│       │   │   │   ├── __init__.py                                 # HTTP interfaces for owned model connections.
│       │   │   │   ├── routes.py                                   # Owner-scoped model connection endpoints.
│       │   │   │   └── schemas.py                                  # Validate model connection requests and public response fields.
│       │   │   ├── evaluations/
│       │   │   │   ├── __init__.py                                 # HTTP interfaces for evaluation admission and evidence.
│       │   │   │   ├── catalogue.py                                # Authenticated evaluation catalogue metadata.
│       │   │   │   ├── labels.py                                   # Arabic catalogue labels shared by HTTP metadata and report presentation.
│       │   │   │   ├── mapping.py                                  # Map validated HTTP inputs to domain evaluation parameters.
│       │   │   │   ├── routes.py                                   # Evaluation admission, lifecycle control and streamed evidence endpoints.
│       │   │   │   └── schemas.py                                  # Validate evaluation selections and lifecycle response fields.
│       │   │   ├── middleware/
│       │   │   │   ├── __init__.py                                 # HTTP transport admission and response protections.
│       │   │   │   ├── body_limit.py                               # Bound incoming request bodies before JSON parsing or password work.
│       │   │   │   └── security_headers.py                         # Browser security headers for same-origin HTML and authenticated API.
│       │   │   ├── __init__.py                                     # REST API delivery built on FastAPI.
│       │   │   ├── app.py                                          # FastAPI application exposing connection and run management over HTTP.
│       │   │   └── identifiers.py                                  # Validate entity identifiers taken from request paths.
│       │   ├── cli/
│       │   │   ├── __init__.py                                     # Command-line delivery.
│       │   │   ├── administrator_command.py                        # Administrator access commands with the service injected.
│       │   │   ├── generation_command.py                           # Import pattern cards, or run one round, with the services injected.
│       │   │   └── report_command.py                               # Publish judge benchmark report files with the storage injected.
│       │   └── __init__.py                                         # Delivery mechanisms exposing the use cases.
│       └── __init__.py                                             # HARASS: Hardened Arabic Red-Teaming And Safety Shield.
├── tests/
│   ├── end_to_end/
│   │   └── browser_server.py                                       # Run local browser QA against real application adapters.
│   ├── frontend/
│   │   ├── initialization.cjs                                      # Pending initialization cannot send credential fields through a native form request.
│   │   ├── report.cjs                                              # Unsafe evidence stays text while adaptive and control metrics remain distinct.
│   │   └── shell.cjs                                               # Mounting the shared layout replaces navigation without duplicating controls.
│   ├── integration/
│   │   ├── test_live_round_trip.py                                 # Tests for live round trip.
│   │   └── test_pyrit_dependency.py                                # Tests for pyrit dependency.
│   ├── unit/
│   │   ├── application/
│   │   │   ├── generation/                                         # Tests for the agentic prompt generator's rounds.
│   │   │   │   └── test_generation_round.py                        # Tests for one generation round, driven entirely by fake ports.
│   │   │   ├── test_administrators.py                              # Tests for granting and revoking administrator access.
│   │   │   ├── test_judge_benchmark_reports.py                     # Tests for publishing and reading judge benchmark reports.
│   │   │   ├── test_manage_connections.py                          # Tests for the connection-management use case with in-memory fakes.
│   │   │   ├── test_manage_runs.py                                 # Run admission coordinates ownership and durable ports without execution.
│   │   │   ├── test_report_document.py                             # Tests for the JSON-compatible evaluation report document.
│   │   │   ├── test_run_evaluation.py                              # Tests for run evaluation.
│   │   │   └── test_variant_evaluation.py                          # Tests for variant evaluation.
│   │   ├── domain/
│   │   │   ├── generation/                                         # Tests for the generator's pure rules.
│   │   │   │   ├── test_briefs.py                                  # Tests for the Arabic briefs the writer and the localizer read.
│   │   │   │   ├── test_cells.py                                   # Tests for the over-refusal cell grid and round planner.
│   │   │   │   ├── test_dialect.py                                 # Tests for the dialect marker and formal leakage checks.
│   │   │   │   ├── test_history.py                                 # Tests for the generator's history: verdicts, counts and lesson choice.
│   │   │   │   ├── test_pattern_card.py                            # Tests for pattern cards and their confidence-bound assignment.
│   │   │   │   ├── test_review.py                                  # Tests for the form reviewer's verdict record.
│   │   │   │   └── test_transforms.py                              # Tests for the auditable Arabic surface transforms.
│   │   │   ├── test_case_identifier.py                             # Tests for the case identifier coding rules.
│   │   │   ├── test_case_selection.py                              # Tests for case selection criteria.
│   │   │   ├── test_comprehension.py                               # Tests for the rule signals of responses that missed the prompt.
│   │   │   ├── test_domain_invariants.py                           # Tests for invariants of evaluation cases and converter chains.
│   │   │   ├── test_evaluation_plan.py                             # Tests for evaluation plans and base-case sampling.
│   │   │   ├── test_metrics.py                                     # Tests for safety metrics and Wilson score intervals.
│   │   │   └── test_target_connection.py                           # Tests for target connection invariants.
│   │   ├── infrastructure/
│   │   │   ├── test_account_mail.py                                # SMTP transport security and disabled-feature composition checks.
│   │   │   ├── test_connection_verifier.py                         # Tests for connection verifier.
│   │   │   ├── test_durable_runs.py                                # Tests for durable runs.
│   │   │   ├── test_fernet_secret_cipher.py                        # Tests for the Fernet secret cipher.
│   │   │   ├── test_generation_judges.py                           # Tests for the generator's reviewer, safety judge and pattern reader.
│   │   │   ├── test_generation_store.py                            # Tests for the append-only storage of the prompt generator.
│   │   │   ├── test_judge_server.py                                # Tests for the judge server script, run with stand-ins for the GPU stack.
│   │   │   ├── test_migrations_and_limits.py                       # Tests for migrations and limits.
│   │   │   ├── test_model_gateway.py                               # Tests for the generator's model gateway and its judging wrapper.
│   │   │   ├── test_settings_and_targets.py                        # Tests for system settings and the construction of PyRIT targets.
│   │   │   ├── test_spreadsheet_seed_source.py                     # Tests for reading evaluation cases from the dataset spreadsheet.
│   │   │   ├── test_sqlalchemy_stores.py                           # Tests for the SQLAlchemy connection and run stores and the finding archive.
│   │   │   └── test_variant_attempt_executor.py                    # Tests for variant attempt executor.
│   │   ├── interfaces/
│   │   │   ├── test_account_recovery.py                            # Account-email gating and single-use recovery on real isolated storage.
│   │   │   ├── test_admin_routes.py                                # Tests for the administrator-only judge benchmark endpoints.
│   │   │   ├── test_administrator_command.py                       # Tests for the administrator access command.
│   │   │   ├── test_api.py                                         # Tests for the HTTP API with in-memory use cases and no real model calls.
│   │   │   ├── test_authentication.py                              # Tests for authentication.
│   │   │   ├── test_generation_command.py                          # Tests for the prompt generation command.
│   │   │   ├── test_product_protocol.py                            # Behavioral tests for the product's two fixed evaluation protocols.
│   │   │   └── test_report_command.py                              # Tests for the judge report publish command.
│   │   └── test_function_length.py                                 # Keep every function short enough to read in one screen.
│   └── conftest.py                                                 # Shared test fixtures.
├── tools/
│   └── judge_host/
│       └── judge_server.py                                         # Serve a decision model over HTTP for the judge benchmark.
├── .dockerignore                                                   # Excludes local and generated files from Docker build contexts.
├── .env.example                                                    # Documents environment variables without storing credentials.
├── .gitignore                                                      # Excludes secrets, environments, caches, and build output.
├── AGENTS.md                                                       # Engineering rules for everyone changing the project.
├── alembic.ini                                                     # Configures the Alembic migration environment.
├── AUTHORS                                                         # Lists the project contributors.
├── compose.test.yml                                                # Defines disposable PostgreSQL integration-test storage.
├── compose.yml                                                     # Defines PostgreSQL, migrations, the API, and the worker.
├── Dockerfile                                                      # Builds the shared non-root API and worker image.
├── pyproject.toml                                                  # Defines package metadata, entry points, and quality rules.
├── README.md                                                       # Describes the project, runtime, and verification workflow.
└── requirements.txt                                                # Pins reproducible runtime and development dependencies.
```
