# File structure

Maintained source files and their responsibilities. Generated files, local secrets, virtual environments, caches, and IDE settings are excluded.

```text
2026-GP1-29/
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
│   └── test_dataset.xlsx                                           # Provides neutral cases for automated tests.
├── doc/
│   └── file-structure.md                                           # Documents the maintained repository structure.
├── frontend/
│   ├── assets/
│   │   ├── css/
│   │   │   └── styles.css                                          # Shared layout, form controls and responsive evaluation presentation.
│   │   ├── images/
│   │   │   └── harass-logo.png                                     # Stores the HARASS product mark.
│   │   └── js/
│   │       ├── core/
│   │       │   ├── api-client.js                                   # Same-origin API transport with bounded requests and serialized session renewal.
│   │       │   ├── bootstrap.js                                    # Account initialization and page-controller dispatch.
│   │       │   ├── forms.js                                        # Shared form validation, submission and page navigation behavior.
│   │       │   └── ui.js                                           # Shared navigation, escaped markup and accessible UI primitives.
│   │       ├── pages/
│   │       │   ├── account-email.js                                # Feature-gated recovery and verification forms with fragment-only link tokens.
│   │       │   ├── account.js                                      # Password reauthentication and owner-scoped session management.
│   │       │   ├── auth.js                                         # Auth page interactions and error recovery.
│   │       │   ├── connections.js                                  # Connections page interactions and error recovery.
│   │       │   ├── dashboard.js                                    # Dashboard page interactions and error recovery.
│   │       │   ├── evaluation.js                                   # Evaluation page interactions and error recovery.
│   │       │   ├── history.js                                      # History page interactions and error recovery.
│   │       │   └── report.js                                       # Report page interactions and error recovery.
│   │       └── views/
│   │           ├── report-evidence.js                              # Escaped attempt transcripts, verdict evidence and evidence pagination.
│   │           ├── report.js                                       # Evaluation metrics, coverage and report composition.
│   │           └── run.js                                          # Evaluation lifecycle, progress and bounded page navigation.
│   ├── account.html                                                # Presents password and session management.
│   ├── connections.html                                            # Lists saved target-model connections.
│   ├── dashboard.html                                              # Presents the authenticated account overview.
│   ├── evaluation-run.html                                         # Displays evaluation progress and results.
│   ├── evaluation-setup.html                                       # Collects the evaluation mode and scope.
│   ├── forgot-password.html                                        # Requests a password-recovery message.
│   ├── history.html                                                # Lists persisted evaluation runs.
│   ├── htmlvalidate.config.cjs                                     # Validate native HTML while allowing named checkbox groups.
│   ├── index.html                                                  # Provides the public landing page.
│   ├── login.html                                                  # Provides account authentication.
│   ├── model-configuration.html                                    # Collects and verifies target connection details.
│   ├── reset-password.html                                         # Accepts a recovery token and replacement password.
│   ├── signup.html                                                 # Provides account registration.
│   ├── stylelint.config.cjs                                        # Detect invalid CSS and duplicate declarations without a styling library.
│   └── verify-email.html                                           # Processes email-verification links.
├── src/
│   └── harass/
│       ├── application/
│       │   ├── accounts/
│       │   │   ├── __init__.py                                     # Account authentication and recovery use cases.
│       │   │   ├── authentication.py                               # Create accounts, authenticate credentials, and revoke sessions.
│       │   │   ├── errors.py                                       # Public account failures without credential or provider details.
│       │   │   ├── password_policy.py                              # Shared password requirements for registration, changes and recovery.
│       │   │   └── recovery.py                                     # Issue and consume purpose-bound account verification and reset links.
│       │   ├── evaluation/
│       │   │   ├── __init__.py                                     # Evaluation admission, orchestration and durable worker execution.
│       │   │   ├── contracts.py                                    # Request and report data exchanged with the evaluation use case.
│       │   │   ├── job_parameters.py                               # Decode persisted execution parameters without depending on HTTP schemas.
│       │   │   ├── outcome_codec.py                                # Decode stored outcomes for evidence and statistical analysis.
│       │   │   ├── parameters.py                                   # Validated selections and immutable inputs for evaluation admission.
│       │   │   ├── run_service.py                                  # Manage evaluation admission, lifecycle and stored reports.
│       │   │   ├── runner.py                                       # Select paired seeds and compute auditable evaluation reports.
│       │   │   ├── variant_engine.py                               # Execute adaptive evaluations with durable attempt reservations.
│       │   │   └── worker.py                                       # Renewable worker execution outside the HTTP application lifecycle.
│       │   ├── ports/
│       │   │   ├── __init__.py                                     # Abstract interfaces that outer layers implement.
│       │   │   ├── account_actions.py                              # Atomic storage and mail delivery contracts for account actions.
│       │   │   ├── attempt_executor.py                             # Port for one isolated target request followed by its verdicts.
│       │   │   ├── authentication.py                               # Persistence and cryptographic contracts for authentication.
│       │   │   ├── connection_store.py                             # Persist owned model connections and encrypted API keys.
│       │   │   ├── connection_verifier.py                          # Check model endpoints using the supplied credentials.
│       │   │   ├── evaluation_engine.py                            # Port for executing an evaluation plan against a model.
│       │   │   ├── evaluation_journal.py                           # Durable attempt reservations, checkpoints and outcome iteration.
│       │   │   ├── report_exporter.py                              # Port for persisting evaluation reports outside the system.
│       │   │   ├── request_limiter.py                              # Shared admission control for expensive HTTP operations.
│       │   │   ├── run_admission.py                                # Owner-facing admission, lifecycle and evidence access for durable runs.
│       │   │   ├── run_queue.py                                    # Durable run admission, worker leases and paged evidence.
│       │   │   ├── run_store.py                                    # Port for persisting the lifecycle and results of evaluation runs.
│       │   │   ├── secret_cipher.py                                # Define encryption and decryption of stored secrets.
│       │   │   ├── seed_source.py                                  # Port for reading human-written evaluation cases.
│       │   │   └── variant_catalog.py                              # Define authored templates and deterministic transformations.
│       │   ├── reporting/
│       │   │   ├── __init__.py                                     # Framework-independent report projections and serialization.
│       │   │   ├── document.py                                     # Serialize evaluation reports into JSON-compatible documents.
│       │   │   └── labels.py                                       # Arabic labels under which verdicts and metrics are presented to readers.
│       │   ├── __init__.py                                         # Use cases orchestrating the domain through abstract ports.
│       │   ├── connections.py                                      # Use case: add, update, list and test clients' model connections.
│       │   └── errors.py                                           # Errors that are part of the application port contracts.
│       ├── bootstrap/
│       │   ├── __init__.py                                         # Composition root wiring adapters to ports.
│       │   ├── accounts.py                                         # Compose account authentication and optional mail delivery at startup.
│       │   ├── api.py                                              # Composition root of the HTTP API.
│       │   ├── cli.py                                              # Composition root of the command-line interface.
│       │   ├── evaluation.py                                       # Compose evaluation dependencies and configuration fingerprints.
│       │   ├── execution_profile.py                                # Fingerprint execution inputs before admitting or resuming durable work.
│       │   ├── health.py                                           # Bounded health probes for the HTTP process and durable worker heartbeat.
│       │   ├── migrate.py                                          # Apply explicit database migrations as a standalone deployment step.
│       │   ├── review_cli.py                                       # Compose blind-review preparation and calibration commands.
│       │   └── worker.py                                           # Independent durable evaluation worker sharing the API's PostgreSQL queue.
│       ├── domain/
│       │   ├── __init__.py                                         # Define framework-independent Arabic safety evaluation rules.
│       │   ├── account_action.py                                   # Expiring, single-use account actions with purpose-bound credentials.
│       │   ├── adaptive_controller.py                              # Implement Beta-Bernoulli Thompson recipe selection.
│       │   ├── adaptive_metrics.py                                 # Measure observed discovery under adaptive selection.
│       │   ├── agreement.py                                        # Agreement between two raters labelling the same responses.
│       │   ├── authentication.py                                   # User identities and revocable authentication sessions.
│       │   ├── case_identifier.py                                  # Case identifiers of the HARASS coding system.
│       │   ├── case_outcome.py                                     # Judged outcome of sending one case using an auditable prompt recipe.
│       │   ├── case_selection.py                                   # Criteria for selecting evaluation cases.
│       │   ├── errors.py                                           # Errors raised when domain invariants are violated.
│       │   ├── evaluation_case.py                                  # Evaluation cases sent to the target model.
│       │   ├── evaluation_plan.py                                  # Select paired cases, recipes and execution policy.
│       │   ├── evaluation_run.py                                   # The lifecycle record of one evaluation run managed by the backend.
│       │   ├── metrics.py                                          # Safety metrics computed from judged case outcomes.
│       │   ├── model_connection.py                                 # A client's saved connection to a model under evaluation.
│       │   ├── owasp_scenario.py                                   # Define synthetic single-turn OWASP LLM scenarios.
│       │   ├── prompt_variant.py                                   # Define framework-independent prompt variants and recipe contracts.
│       │   ├── review.py                                           # Analyze labelled agreement and held-out leak calibration.
│       │   ├── seed_library.py                                     # Group linguistic variants by unambiguous base-case identity.
│       │   ├── target_connection.py                                # Connection details of the model under evaluation.
│       │   └── taxonomy.py                                         # Classification codes of the HARASS evaluation taxonomy.
│       ├── infrastructure/
│       │   ├── dataset/
│       │   │   ├── __init__.py                                     # Readers of the project dataset.
│       │   │   ├── prompt_transforms.py                            # Auditable Arabic transforms with explicit composition properties.
│       │   │   ├── spreadsheet_seed_source.py                      # Seed source reading evaluation cases from the dataset spreadsheet.
│       │   │   └── yaml_variant_catalog.py                         # Compose bounded prompt variants from authored YAML recipes.
│       │   ├── http/
│       │   │   ├── __init__.py                                     # HTTP adapters.
│       │   │   ├── endpoint_policy.py                              # Pin approved outbound addresses while retaining TLS checks.
│       │   │   └── openai_connection_verifier.py                   # Verify model availability and generation on compatible endpoints.
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
│       │   │   │   │   └── 0007_account_actions.py                 # Add optional email verification and hashed single-use account actions.
│       │   │   │   ├── env.py                                      # Run migrations using environment or injected connection settings.
│       │   │   │   └── script.py.mako                              # Defines the template used to generate Alembic revisions.
│       │   │   ├── tables/
│       │   │   │   ├── __init__.py                                 # Register all ORM mappings against one shared metadata collection.
│       │   │   │   ├── accounts.py                                 # Account identities, revocable sessions and expiring actions.
│       │   │   │   ├── base.py                                     # Shared ORM metadata and portable entity identifier storage.
│       │   │   │   ├── connections.py                              # Owned model connection metadata and encrypted credentials.
│       │   │   │   ├── evaluations.py                              # Evaluation lifecycle, reports and durable worker checkpoints.
│       │   │   │   ├── request_limits.py                           # Shared rate-limit counters without raw client identifiers.
│       │   │   │   └── research.py                                 # Generated prompt content and reproducible defect observations.
│       │   │   ├── __init__.py                                     # PostgreSQL persistence for project-level data.
│       │   │   ├── job_sessions.py                                 # Transactional job storage and worker ownership checks.
│       │   │   ├── prompt_archive.py                               # Internal research archival inside the report transaction.
│       │   │   ├── row_mapping.py                                  # Convert persisted evaluation rows and restore UTC timestamps.
│       │   │   ├── schema.py                                       # Explicit schema readiness checks before production storage is used.
│       │   │   ├── session_factory.py                              # Type contract for independent SQLAlchemy database sessions.
│       │   │   ├── sqlalchemy_account_actions.py                   # Consume account actions atomically and revoke stale credentials.
│       │   │   ├── sqlalchemy_authentication.py                    # Persist accounts and revocable sessions transactionally.
│       │   │   ├── sqlalchemy_connections.py                       # Persist owned model connections and encrypted credentials.
│       │   │   ├── sqlalchemy_jobs.py                              # Persist queued work with shared judge admission and leases.
│       │   │   ├── sqlalchemy_journal.py                           # Commit attempt evidence under fenced worker leases.
│       │   │   ├── sqlalchemy_request_limiter.py                   # Database-backed fixed-window counters shared by all API workers.
│       │   │   ├── sqlalchemy_runs.py                              # Query evaluation histories and persist report documents.
│       │   │   └── upsert.py                                       # Build atomic inserts for PostgreSQL and SQLite.
│       │   ├── pyrit/
│       │   │   ├── scoring/
│       │   │   │   ├── rubrics/
│       │   │   │   │   ├── attack_success_question.yaml            # Attack success criteria following HarmBench (Mazeika et al., 2024, Appendix B.1).
│       │   │   │   │   ├── attack_success_system_prompt.yaml       # Applies the attack criterion with a concise auditable verdict.
│       │   │   │   │   ├── response_categories.yaml                # Response categories following XSTest (Röttger et al., 2024, Section 4.2), with an unclear
│       │   │   │   │   └── response_category_system_prompt.yaml    # Instructions
│       │   │   │   ├── __init__.py                                 # Judge-model scorers built on PyRIT.
│       │   │   │   ├── majority_vote.py                            # Majority vote over repeated judge verdicts on the same response.
│       │   │   │   ├── reasoning_response_handler.py               # Separate judge reasoning traces from structured verdicts.
│       │   │   │   ├── request_aware_category_scorer.py            # Category scorer that shows the judge the request alongside the response.
│       │   │   │   ├── scorer_builder.py                           # Assembly of the judge-model scorers from their rubric files.
│       │   │   │   ├── synthetic_disclosure_scorer.py              # Deterministic synthetic disclosure judging without another model request.
│       │   │   │   └── voting_true_false_scorer.py                 # Aggregate independent binary judge votes by majority.
│       │   │   ├── __init__.py                                     # Adapters built on PyRIT.
│       │   │   ├── attempt_outcome.py                              # Conversion of stored PyRIT verdicts into auditable application outcomes.
│       │   │   ├── judge_request_audit.py                          # Count judge HTTP calls without recording request content.
│       │   │   ├── target_builder.py                               # Build PyRIT targets for evaluated models and the judge.
│       │   │   └── variant_attempt_executor.py                     # Execute isolated PyRIT attempts with request-aware scoring.
│       │   ├── reporting/
│       │   │   ├── __init__.py                                     # Report export adapters.
│       │   │   ├── json_report_exporter.py                         # Export of evaluation reports as UTF-8 JSON files.
│       │   │   └── review_files.py                                 # Prepare review CSV files and validate supplied labels.
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
│       │   │   └── app.py                                          # FastAPI application exposing connection and run management over HTTP.
│       │   ├── cli/
│       │   │   ├── __init__.py                                     # Command-line delivery.
│       │   │   ├── evaluate_command.py                             # Command-line interface for single-turn evaluation runs.
│       │   │   └── review_command.py                               # Review commands with file operations injected by the composition root.
│       │   └── __init__.py                                         # Delivery mechanisms exposing the use cases.
│       └── __init__.py                                             # HARASS: Hardened Arabic Red-Teaming And Safety Shield.
├── tests/
│   ├── end_to_end/
│   │   └── browser_server.py                                       # Run local browser QA against real application adapters.
│   ├── frontend/
│   │   ├── initialization.cjs                                      # Tests page initialization and credential-safe form behavior.
│   │   ├── report.cjs                                              # Tests escaped evidence and report metric rendering.
│   │   └── shell.cjs                                               # Provides the isolated JavaScript test environment.
│   ├── integration/
│   │   ├── test_live_round_trip.py                                 # Tests for live round trip.
│   │   └── test_pyrit_dependency.py                                # Tests for pyrit dependency.
│   ├── unit/
│   │   ├── application/
│   │   │   ├── test_manage_connections.py                          # Tests for the connection-management use case with in-memory fakes.
│   │   │   ├── test_manage_runs.py                                 # Run admission coordinates ownership and durable ports without execution.
│   │   │   ├── test_run_evaluation.py                              # Tests for run evaluation.
│   │   │   └── test_variant_evaluation.py                          # Tests for variant evaluation.
│   │   ├── domain/
│   │   │   ├── test_agreement.py                                   # Tests for inter-rater agreement.
│   │   │   ├── test_case_identifier.py                             # Tests for the case identifier coding rules.
│   │   │   ├── test_case_selection.py                              # Tests for case selection criteria.
│   │   │   ├── test_domain_invariants.py                           # Tests for invariants of evaluation cases and converter chains.
│   │   │   ├── test_evaluation_plan.py                             # Tests for evaluation plans and base-case sampling.
│   │   │   ├── test_metrics.py                                     # Tests for safety metrics and Wilson score intervals.
│   │   │   ├── test_review.py                                      # Tests for review.
│   │   │   └── test_target_connection.py                           # Tests for target connection invariants.
│   │   ├── infrastructure/
│   │   │   ├── test_account_mail.py                                # SMTP transport security and disabled-feature composition checks.
│   │   │   ├── test_connection_verifier.py                         # Tests for connection verifier.
│   │   │   ├── test_durable_runs.py                                # Tests for durable runs.
│   │   │   ├── test_fernet_secret_cipher.py                        # Tests for the Fernet secret cipher.
│   │   │   ├── test_json_report_exporter.py                        # Tests for the JSON report exporter.
│   │   │   ├── test_migrations_and_limits.py                       # Tests for migrations and limits.
│   │   │   ├── test_review_files.py                                # Tests for review files.
│   │   │   ├── test_scoring.py                                     # Tests for scoring.
│   │   │   ├── test_settings_and_targets.py                        # Tests for system settings and the construction of PyRIT targets.
│   │   │   ├── test_spreadsheet_seed_source.py                     # Tests for reading evaluation cases from the dataset spreadsheet.
│   │   │   ├── test_sqlalchemy_stores.py                           # Tests for the SQLAlchemy connection and run stores on in-memory SQLite.
│   │   │   └── test_variant_attempt_executor.py                    # Tests for variant attempt executor.
│   │   └── interfaces/
│   │       ├── test_account_recovery.py                            # Account-email gating and single-use recovery on real isolated storage.
│   │       ├── test_api.py                                         # Tests for the HTTP API with in-memory use cases and no real model calls.
│   │       ├── test_authentication.py                              # Tests for authentication.
│   │       ├── test_evaluate_command.py                            # Tests for the evaluate command of the command-line interface.
│   │       ├── test_product_protocol.py                            # Behavioral tests for the product's two fixed evaluation protocols.
│   │       └── test_review_command.py                              # Tests for review command.
│   └── conftest.py                                                 # Shared test fixtures.
├── .dockerignore                                                   # Excludes local and generated files from Docker build contexts.
├── .env.example                                                    # Documents environment variables without storing credentials.
├── .gitignore                                                      # Excludes secrets, environments, caches, and build output.
├── alembic.ini                                                     # Configures the Alembic migration environment.
├── AUTHORS                                                         # Lists the project contributors.
├── compose.test.yml                                                # Defines disposable PostgreSQL integration-test storage.
├── compose.yml                                                     # Defines PostgreSQL, migrations, the API, and the worker.
├── Dockerfile                                                      # Builds the shared non-root API and worker image.
├── pyproject.toml                                                  # Defines package metadata, entry points, and quality rules.
├── README.md                                                       # Describes the project, runtime, and verification workflow.
└── requirements.txt                                                # Pins reproducible runtime and development dependencies.
```
