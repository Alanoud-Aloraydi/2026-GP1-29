# File structure

Source files and their responsibilities.

```text
2026-GP1-29/
├── config/
│   └── templates/
│       ├── at_direct_plain.yaml  # AT direct plain template.
│       ├── at_direct_steps.yaml  # AT direct steps template.
│       ├── at_distraction_heading.yaml  # AT distraction heading template.
│       ├── at_distraction_sections.yaml  # AT distraction sections template.
│       ├── at_obfuscation_payload.yaml  # AT obfuscation payload template.
│       ├── at_obfuscation_quoted.yaml  # AT obfuscation quoted template.
│       ├── at_persuasion_consistency.yaml  # AT persuasion consistency template.
│       ├── at_persuasion_urgency.yaml  # AT persuasion urgency template.
│       ├── at_poisoned_note.yaml  # AT poisoned note template.
│       ├── at_poisoned_record.yaml  # AT poisoned record template.
│       ├── at_role_dialogue.yaml  # AT role dialogue template.
│       ├── at_role_expert.yaml  # AT role expert template.
│       ├── or_delimited.yaml  # OR delimited template.
│       ├── or_plain.yaml  # OR plain template.
│       ├── or_readability.yaml  # OR readability template.
│       └── or_verbatim.yaml  # OR verbatim template.
├── data/
│   └── test_dataset.xlsx  # Neutral evaluation fixture.
├── doc/
│   ├── agentic-workflow.md  # Adaptive selection and stopping rules.
│   ├── file-structure.md  # Source-tree reference.
│   └── system-diagrams.md  # Storage, class and sequence diagrams.
├── frontend/
│   ├── assets/
│   │   ├── css/
│   │   │   └── styles.css  # Shared component styles.
│   │   ├── images/
│   │   │   └── harass-logo.png  # Product logo.
│   │   └── js/
│   │       ├── api.js  # Same-origin HTTP client.
│   │       ├── app.js  # Page controllers and form events.
│   │       └── harass.js  # Rendering helpers and shared layout.
│   ├── connections.html  # Connections and verification.
│   ├── dashboard.html  # Account overview.
│   ├── evaluation-run.html  # Run status and report view.
│   ├── evaluation-setup.html  # Evaluation settings form.
│   ├── history.html  # Evaluation history.
│   ├── index.html  # Public landing page.
│   ├── login.html  # Account sign-in form.
│   ├── model-configuration.html  # Model connection form.
│   └── signup.html  # Account registration form.
├── src/
│   ├── harass/
│   │   ├── application/
│   │   │   ├── ports/
│   │   │   │   ├── __init__.py  # Abstract interfaces that outer layers implement.
│   │   │   │   ├── attempt_executor.py  # Port for one isolated target request followed by its verdicts.
│   │   │   │   ├── authentication.py  # Persistence and cryptographic contracts for authentication.
│   │   │   │   ├── connection_store.py  # Port for persisting clients' model connections and their encrypted API keys.
│   │   │   │   ├── connection_verifier.py  # Connection verifier module.
│   │   │   │   ├── evaluation_engine.py  # Port for executing an evaluation plan against a model.
│   │   │   │   ├── report_exporter.py  # Port for persisting evaluation reports outside the system.
│   │   │   │   ├── run_store.py  # Port for persisting the lifecycle and results of evaluation runs.
│   │   │   │   ├── secret_cipher.py  # Port for protecting secrets, such as client API keys, while they are stored.
│   │   │   │   ├── seed_source.py  # Port for reading human-written evaluation cases.
│   │   │   │   └── variant_catalog.py  # Port for an extensible authored template and rule-based transform library.
│   │   │   ├── use_cases/
│   │   │   │   ├── __init__.py  # Application use cases.
│   │   │   │   ├── manage_authentication.py  # Create accounts, authenticate credentials, and revoke sessions.
│   │   │   │   ├── manage_connections.py  # Use case: add, update, list and test clients' model connections.
│   │   │   │   ├── manage_runs.py  # Use case: start evaluation runs, track their status and keep their reports.
│   │   │   │   └── run_evaluation.py  # Run evaluation module.
│   │   │   ├── __init__.py  # Use cases orchestrating the domain through abstract ports.
│   │   │   ├── errors.py  # Errors that are part of the application port contracts.
│   │   │   ├── evaluation_report.py  # Request and report data exchanged with the evaluation use case.
│   │   │   ├── report_document.py  # Pure serialization of an evaluation report into a JSON-compatible document.
│   │   │   ├── report_labels.py  # Arabic labels under which verdicts and metrics are presented to readers.
│   │   │   └── variant_evaluation_engine.py  # Static and adaptive single-turn evaluation over an authored variant library.
│   │   ├── bootstrap/
│   │   │   ├── __init__.py  # Composition root wiring adapters to ports.
│   │   │   ├── api.py  # Composition root of the HTTP API.
│   │   │   ├── cli.py  # Composition root of the command-line interface.
│   │   │   └── review_cli.py  # Review cli module.
│   │   ├── domain/
│   │   │   ├── __init__.py  # Domain package.
│   │   │   ├── adaptive_controller.py  # Adaptive controller module.
│   │   │   ├── adaptive_metrics.py  # Adaptive metrics module.
│   │   │   ├── agreement.py  # Agreement between two raters labelling the same responses.
│   │   │   ├── authentication.py  # User identities and revocable authentication sessions.
│   │   │   ├── case_identifier.py  # Case identifiers of the HARASS coding system.
│   │   │   ├── case_outcome.py  # Judged outcome of sending one case using an auditable prompt recipe.
│   │   │   ├── case_selection.py  # Criteria for selecting evaluation cases.
│   │   │   ├── errors.py  # Errors raised when domain invariants are violated.
│   │   │   ├── evaluation_case.py  # Evaluation cases sent to the target model.
│   │   │   ├── evaluation_plan.py  # Evaluation plan module.
│   │   │   ├── evaluation_run.py  # The lifecycle record of one evaluation run managed by the backend.
│   │   │   ├── metrics.py  # Safety metrics computed from judged case outcomes.
│   │   │   ├── model_connection.py  # A client's saved connection to a model under evaluation.
│   │   │   ├── owasp_scenario.py  # Owasp scenario module.
│   │   │   ├── prompt_variant.py  # Prompt variant module.
│   │   │   ├── review.py  # Review module.
│   │   │   ├── seed_library.py  # Seed library module.
│   │   │   ├── target_connection.py  # Connection details of the model under evaluation.
│   │   │   └── taxonomy.py  # Classification codes of the HARASS evaluation taxonomy.
│   │   ├── infrastructure/
│   │   │   ├── dataset/
│   │   │   │   ├── __init__.py  # Readers of the project dataset.
│   │   │   │   ├── prompt_transforms.py  # Auditable Arabic transforms with explicit composition properties.
│   │   │   │   ├── spreadsheet_seed_source.py  # Seed source reading evaluation cases from the dataset spreadsheet.
│   │   │   │   └── yaml_variant_catalog.py  # Yaml variant catalog module.
│   │   │   ├── http/
│   │   │   │   ├── __init__.py  # HTTP adapters.
│   │   │   │   └── openai_connection_verifier.py  # Openai connection verifier module.
│   │   │   ├── persistence/
│   │   │   │   ├── __init__.py  # PostgreSQL persistence for project-level data.
│   │   │   │   ├── sqlalchemy_authentication.py  # Sqlalchemy authentication module.
│   │   │   │   ├── sqlalchemy_stores.py  # SQLAlchemy-backed implementations of the connection and run stores.
│   │   │   │   └── tables.py  # SQLAlchemy table definitions for connections and runs.
│   │   │   ├── pyrit/
│   │   │   │   ├── scoring/
│   │   │   │   │   ├── rubrics/
│   │   │   │   │   │   ├── attack_success_question.yaml  # Attack-success judge criterion.
│   │   │   │   │   │   ├── response_categories.yaml  # Response categories.
│   │   │   │   │   ├── __init__.py  # Judge-model scorers built on PyRIT.
│   │   │   │   │   ├── scorer_builder.py  # Assembly of the judge-model scorers from their rubric files.
│   │   │   │   ├── __init__.py  # Adapters built on PyRIT.
│   │   │   │   ├── target_builder.py  # Target builder module.
│   │   │   │   └── variant_attempt_executor.py  # Variant attempt executor module.
│   │   │   ├── reporting/
│   │   │   │   ├── __init__.py  # Report export adapters.
│   │   │   │   ├── json_report_exporter.py  # Export of evaluation reports as UTF-8 JSON files.
│   │   │   │   └── review_files.py  # Review files module.
│   │   │   ├── security/
│   │   │   │   ├── __init__.py  # Secret protection adapters.
│   │   │   │   ├── fernet_secret_cipher.py  # Secret cipher based on Fernet authenticated symmetric encryption.
│   │   │   │   └── jwt_authentication.py  # PyJWT session signing and OWASP-recommended scrypt password hashing.
│   │   │   ├── __init__.py  # Framework and driver adapters implementing the application ports.
│   │   │   └── settings.py  # System settings read from environment variables.
│   │   ├── interfaces/
│   │   │   ├── api/
│   │   │   │   ├── __init__.py  # REST API delivery built on FastAPI.
│   │   │   │   ├── app.py  # FastAPI application exposing connection and run management over HTTP.
│   │   │   │   ├── authentication.py  # Same-origin cookie authentication routes and owner dependency.
│   │   │   │   └── schemas.py  # Pydantic request and response models for the HTTP API.
│   │   │   ├── cli/
│   │   │   │   ├── __init__.py  # Command-line delivery.
│   │   │   │   ├── evaluate_command.py  # Command-line interface for single-turn evaluation runs.
│   │   │   │   └── review_command.py  # Review commands with file operations injected by the composition root.
│   │   │   └── __init__.py  # Delivery mechanisms exposing the use cases.
│   │   └── __init__.py  # HARASS: Hardened Arabic Red-Teaming And Safety Shield.
│   └── harass.egg-info/
│       ├── dependency_links.txt  # Project resource.
│       ├── entry_points.txt  # Project resource.
│       ├── PKG-INFO  # Project resource.
│       ├── requires.txt  # Project resource.
│       ├── SOURCES.txt  # Project resource.
│       └── top_level.txt  # Project resource.
├── tests/
│   ├── end_to_end/
│   │   └── browser_server.py  # Isolated browser-test server.
│   ├── integration/
│   │   ├── test_live_round_trip.py  # Opt-in target and judge checks.
│   │   └── test_pyrit_dependency.py  # PyRIT compatibility checks.
│   ├── unit/
│   │   ├── application/
│   │   │   ├── test_manage_connections.py  # Tests for manage connections.
│   │   │   ├── test_manage_runs.py  # Tests for manage runs.
│   │   │   ├── test_run_evaluation.py  # Tests for run evaluation.
│   │   │   └── test_variant_evaluation.py  # Tests for variant evaluation.
│   │   ├── domain/
│   │   │   ├── test_agreement.py  # Tests for agreement.
│   │   │   ├── test_case_identifier.py  # Tests for case identifier.
│   │   │   ├── test_case_selection.py  # Tests for case selection.
│   │   │   ├── test_domain_invariants.py  # Tests for domain invariants.
│   │   │   ├── test_evaluation_plan.py  # Tests for evaluation plan.
│   │   │   ├── test_metrics.py  # Tests for metrics.
│   │   │   ├── test_review.py  # Tests for review.
│   │   │   └── test_target_connection.py  # Tests for target connection.
│   │   ├── infrastructure/
│   │   │   ├── test_connection_verifier.py  # Tests for connection verifier.
│   │   │   ├── test_fernet_secret_cipher.py  # Tests for fernet secret cipher.
│   │   │   ├── test_json_report_exporter.py  # Tests for json report exporter.
│   │   │   ├── test_review_files.py  # Tests for review files.
│   │   │   ├── test_scoring.py  # Tests for scoring.
│   │   │   ├── test_settings_and_targets.py  # Tests for settings and targets.
│   │   │   ├── test_spreadsheet_seed_source.py  # Tests for spreadsheet seed source.
│   │   │   ├── test_sqlalchemy_stores.py  # Tests for sqlalchemy stores.
│   │   │   └── test_variant_attempt_executor.py  # Tests for variant attempt executor.
│   │   └── interfaces/
│   │       ├── test_api.py  # Tests for api.
│   │       ├── test_authentication.py  # Tests for authentication.
│   │       ├── test_evaluate_command.py  # Tests for evaluate command.
│   │       ├── test_product_protocol.py  # Tests for product protocol.
│   │       └── test_review_command.py  # Tests for review command.
│   └── conftest.py  # Shared pytest fixtures.
├── .env.example  # Environment defaults.
├── .gitignore  # Git ignore rules.
├── AUTHORS  # Project authors.
├── pyproject.toml  # Dependencies, entry points and tool settings.
├── README.md  # Project overview.
└── requirements.txt  # Pinned dependency lock.
```

Entry points: `harass`, `harass-api`, and `harass-review`.


Jev judge: `src/harass/infrastructure/pyrit/scoring/jev_scorer.py`.
