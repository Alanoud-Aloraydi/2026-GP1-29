# Repository Structure

This document defines the approved high-level repository layout and the responsibility of each area.

```text
harass/
├── frontend/                              # React and TypeScript web client
│   ├── src/                               # frontend source code; detailed structure is defined with the UI design
│   └── tests/                             # frontend tests
│
├── backend/                               # Python backend with separate API and worker entry points
│   ├── src/                               # installable backend source packages
│   │   ├── harass_api/                    # public Application API
│   │   │   ├── identity_access/           # authentication, authorization, and user access
│   │   │   ├── projects/                  # project configuration and ownership
│   │   │   ├── target_connections/        # client-model configuration and capability validation
│   │   │   ├── assessments/               # assessment snapshots, lifecycle, and status
│   │   │   ├── reviews/                   # human-review decisions and approved prompt promotion
│   │   │   ├── reporting/                 # result queries, summaries, and reports
│   │   │   ├── bootstrap.py               # API dependency composition root
│   │   │   └── main.py                    # FastAPI entry point
│   │   │
│   │   ├── harass_worker/                 # private red-team assessment runtime
│   │   │   ├── evaluation/                # evaluation bounded context
│   │   │   │   ├── domain/                # AT/OR rules and execution invariants
│   │   │   │   ├── application/           # baseline, Adaptive ST/MT use cases, and ports
│   │   │   │   └── adapters/              # framework and infrastructure integrations
│   │   │   │       ├── inbound/           # workflow-task entry points
│   │   │   │       └── outbound/          # PyRIT, LLM, persistence, and telemetry implementations
│   │   │   ├── bootstrap.py               # worker dependency composition root
│   │   │   └── main.py                    # worker entry point
│   │   │
│   │   └── harass_contracts/              # versioned API–worker wire contracts
│   ├── migrations/                        # application-database migrations only
│   └── tests/                              # backend test suites
│       ├── unit/                           # isolated domain and use-case tests
│       ├── integration/                    # database, PyRIT, and provider integration tests
│       ├── contract/                       # API–worker and target-adapter contract tests
│       ├── architecture/                   # automated dependency-boundary tests
│       └── end_to_end/                     # complete assessment-path tests
│
├── dataset/                               # benchmark data-product definitions
│   ├── schemas/                            # machine-readable dataset field definitions
│   ├── codebooks/                          # domains, risks, strategies, dialects, and status codes
│   ├── fixtures/                          # small, non-sensitive test samples
│   └── release_manifests/                  # dataset versions and provenance records
│
├── docs/                                  # project documentation
│   ├── architecture/                      # architecture documentation and source diagrams
│   │   ├── repository-structure.md        # this repository-structure document
│   │   ├── decisions/                     # Architecture Decision Records
│   ├── methodology/                       # dataset and evaluation methodology
│   ├── specifications/                    # API, worker, target, and data contracts
│   ├── security/                          # threat model, secrets, and retention policies
│   └── operations/                        # deployment, observability, and recovery procedures
│
├── infrastructure/                       # deployment configuration; no business logic
│   ├── local/                              # local development environment
│   └── render/                             # Render deployment configuration
├── .github/workflows/                    # CI/CD and architecture checks
├── .importlinter                         # executable Python dependency rules
├── compose.yaml                           # local multi-service startup
└── README.md                              # project overview, setup, and documentation links
```

Only directories required by implemented use cases should be created. Detailed implementation filenames are added during development while preserving the boundaries above.
