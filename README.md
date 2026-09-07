# OwnSIS

## Purpose

This README is the developer entry point for the first OwnSIS implementation.
It explains what can be exercised now, what remains incomplete, and the exact
local setup and verification workflow. It is not a production deployment guide
or a production-readiness claim.

## What OwnSIS Is

OwnSIS is a multi-tenant Education ERP for schools, colleges, and universities.
It is a greenfield replacement for OpenSIS, not a fork, database proxy, or legacy
compatibility layer.

OwnSIS is the system of record for academic and administrative data. Each organization is an isolated tenant with its own branding, domain, users, permissions, integrations, and subscriptions. Tenant isolation is a foundational architectural property rather than an optional feature.

The platform has explicit authority boundaries:

- **OwnID** is the only identity provider. OwnSIS consumes identity and authentication outcomes but does not create a competing identity system.
- **Moodle** is responsible only for learning delivery. OwnSIS retains ownership of academic and administrative records.
- **MCP** is the governed boundary for AI capabilities. Its first catalog is
  read-only, permission-aware, tenant-bound, entitlement-controlled, and audited.

## First-Release Status

The repository contains a working local first-release implementation for
controlled development and evaluation. Green checks show that repository
contracts pass in the tested environment; they do not establish production
security, availability, accessibility, provider compatibility, backup recovery,
or institutional policy acceptance.

| Classification | Current evidence and limit |
| --- | --- |
| Implemented | FastAPI modular monolith, PostgreSQL/Alembic persistence, explicit tenant context and RLS policies, encrypted server sessions, organization/people/entitlement/academic/admissions/grading/scheduling APIs, audit records, an outbox worker, in-app notifications, bounded self-service reads, a read-only MCP catalog, a permission-driven Next.js shell, Docker local services, and automated backend/frontend checks. |
| Partial | Most of the critical academic journey is assembled from real use cases, but Moodle evidence cannot yet become an official grade and not every portal page is an interactive workflow. Operational replay, observability, accessibility, localization, load isolation, backup restoration, privacy lifecycle, and deployment procedures still require environment-specific evidence. The deterministic timetable generator is intentionally limited. |
| Credential-gated | Real OwnID login, real Moodle calls, and authenticated MCP access require external configuration and controlled-provider tests. Moodle deadline reads are bounded live evidence for the mapped user's enrolled courses; the repository does not persist or serve a deadline cache. |
| Deferred or explicitly unavailable | Authenticated Moodle grade-event ingress, selected-term reconciliation, official Moodle-to-OwnSIS grade acceptance, attendance, Finance balances and payments, HR, Library, Dormitory, advanced analytics, production notification providers, Microsoft 365 provisioning, object storage, custom-domain automation, and production-grade optimizer selection are not complete capabilities. The UI must identify unavailable work rather than fabricate results. |

ADRs [0002 through 0007](adr/README.md) remain **Proposed**. Their implementation
is reviewable evidence, not architecture acceptance. Only ADR-0001 is currently
Accepted. Do not describe this repository as production-ready until the
applicable roadmap gates and human reviews are complete.

## Quick Start

### Prerequisites

- Docker Engine with Docker Compose v2;
- `uv` and a Python 3.14 runtime;
- Node.js 24 or newer and npm 11 or newer; and
- network access for the initial locked dependency install, image pulls, and
  dependency-audit commands.

From the repository root:

```text
make setup
make run
```

`make setup` installs locked backend and frontend dependencies, builds local
images, and creates `.env` from `.env.example` only when `.env` does not already
exist. A new file receives three independently generated Fernet keys for
sessions, PII, and integration credentials. Existing `.env` files are never
overwritten.

`make run` starts PostgreSQL, applies Alembic migrations through the separate
migration role, and starts the API, worker, and frontend. It stays attached to
container logs. In another terminal, seed the synthetic local tenant and
administrator:

```text
make seed
```

The seed is local-only and idempotent. Open:

- web application: `http://localhost:3000`;
- API documentation: `http://localhost:8000/api/docs`;
- liveness: `http://localhost:8000/health`; and
- database readiness: `http://localhost:8000/ready`.

The example environment enables the explicit local development login. It is
rejected by production settings. Stop without deleting data using `make stop`,
or remove containers and networks while retaining the PostgreSQL volume using
`make down`.

## Everyday Commands

Run these from the repository root:

| Task | Exact command |
| --- | --- |
| Install locked dependencies, create a missing local environment, and build images | `make setup` |
| Run the complete local stack | `make run` |
| Apply committed migrations to the configured database | `make migrate` |
| Generate a migration candidate for review | `make migration name="describe the owned schema change"` |
| Verify migration head and model drift | `make migration-check` |
| Seed synthetic local data | `make seed` |
| Run backend and frontend tests | `make test` |
| Run formatting checks, linters, and diff hygiene | `make lint` |
| Run strict backend and frontend type checks | `make typecheck` |
| Verify the committed OpenAPI contract | `make openapi-check` |
| Regenerate OpenAPI and frontend API types intentionally | `make openapi` |
| Build frontend and backend runtime images separately | `make frontend-build` and `make backend-build` |
| Run dependency audits | `make audit` |
| Run the aggregate local validation gate and runtime image builds | `make validate` |

`make validate` does not include `make migration-check`. Run both before handing
off a migration. Real PostgreSQL tenant-enforcement tests are opt-in locally:

```text
docker compose up -d --wait postgres
make migrate
OWNSIS_RUN_POSTGRES_INTEGRATION=1 make test
```

CI enables that flag. Without it, nine PostgreSQL integration tests are reported
as skipped rather than passed.

## Configuration and Credentials

Local development requires no provider credential. `make setup` supplies local
encryption keys, Docker supplies the three PostgreSQL roles, and
`DEV_AUTH_ENABLED=true` enables the explicit development identity adapter.

Controlled external testing requires:

- OwnID issuer, client ID, client secret, redirect/post-logout URLs, and a client
  configuration compatible with Authorization Code + PKCE;
- a tenant Moodle HTTPS origin and least-privileged web-service token configured
  through the authenticated tenant API;
- for MCP, `MCP_ENABLED=true`, `MCP_AUDIENCE`, `MCP_RESOURCE_URL`, an OwnID access
  token with `ownsis:mcp:read`, an active tenant membership, and an enabled MCP
  entitlement (the seeded development-base plan does not grant MCP); and
- separate test tenants and non-production provider accounts for negative and
  failure-path verification.

Production additionally requires externally managed secrets, HTTPS URLs,
secure cookies, HTTPS CORS origins, separate least-privilege database roles,
managed PostgreSQL, backup/restore, egress control, rate/concurrency limits, and
observability. The code validates several unsafe configurations, but validation
is not a substitute for a deployment security review. Real external
notification, Microsoft 365, payment, object-storage, DNS, and certificate
adapters are not made available merely by adding credentials.

## Migration and Recovery Policy

The committed migration chain is forward-only for data-bearing changes. The
initial schema, admissions-conversion, and teacher-availability migrations
intentionally refuse downgrade because destructive reversal cannot preserve
authoritative data; the worker-audit grant migration is safely reversible. Do
not run or document `alembic downgrade base` as a recovery procedure. Use a
reviewed forward repair or restore a verified backup into a controlled
environment.

## Troubleshooting

- If setup cannot initialize `.env`, verify that the repository directory is
  writable. Setup preserves configured values, adds missing defaults, generates
  blank or absent local encryption keys, and restricts the file to its owner.
- If ports `3000`, `5432`, or `8000` are occupied, stop the conflicting service or
  adjust both Compose and the matching URLs; changing only one side breaks
  callbacks or database access.
- If `/ready` returns 503, inspect `docker compose ps` and
  `docker compose logs postgres migrate backend` before retrying migrations.
- If `make seed` cannot connect, start PostgreSQL and apply migrations first with
  `docker compose up -d --wait postgres`, then `make migrate`.
- If OpenAPI checks fail after an intentional API change, run `make openapi`,
  review both generated diffs, and rerun `make openapi-check`.
- `make audit` and therefore `make validate` require package-registry access and
  may fail on network or registry outages; do not report that as a clean audit.
- To erase a disposable local database only, `docker compose down -v` removes the
  named PostgreSQL volume irreversibly. Never use it against data that must be
  retained.

## Responsibilities

The repository must:

- preserve the ownership boundary between OwnSIS, OwnID, and Moodle;
- enforce tenant isolation across data, authorization, integrations, and operations;
- keep domain behavior inside explicit modular boundaries;
- record consequential architecture decisions as ADRs;
- make changes reviewable, testable, observable, and reversible where practical;
- keep documentation synchronized with the behavior and constraints it governs;
- support long-term evolution without premature distribution of the system.

Contributors are responsible for understanding the relevant project documents and accepted ADRs before changing behavior or architecture.

## Technology Stack

| Area | Technology |
| --- | --- |
| Backend language | Python 3.14 |
| Backend framework | FastAPI |
| Data platform | PostgreSQL |
| Database change management | Alembic |
| Frontend framework | Next.js |
| Frontend language | TypeScript |
| Architecture | Domain-Driven Design, Modular Monolith, Event-Driven Architecture |
| Packaging and dependency workflow | uv |
| Runtime packaging | Docker |
| Identity | OwnID |
| Learning platform | Moodle |
| AI integration | MCP |

The stack is a constraint, not a complete design. Detailed technology choices that materially affect longevity, security, operability, or coupling require documented justification and, when architectural, an ADR.

## Repository Philosophy

- **Documentation is part of the product.** Architecture, security expectations, coding standards, and decisions must be maintained with the implementation they govern.
- **Domain language is deliberate.** Names must reflect concepts validated through domain discovery rather than terminology inherited from a legacy system.
- **Boundaries are more important than directory aesthetics.** A modular monolith succeeds only when dependency direction and ownership are enforced.
- **Explicit code is preferred.** Readable intent, strong types, clear contracts, and straightforward control flow are favored over clever compression or hidden behavior.
- **Change is evidence-driven.** New abstractions, dependencies, infrastructure, and service boundaries require a demonstrated need.
- **Security is structural.** Tenant context, authorization, secrets handling, auditability, and least privilege are designed into every relevant path.
- **No legacy compatibility is assumed.** OpenSIS behavior, schemas, and interfaces have no authority unless separately adopted through OwnSIS requirements and decisions.

## Documentation Map

The numbered documents in `docs/` move from project context and requirements through architecture, domain boundaries, security, engineering standards, agent rules, and roadmap. Detailed backend implementation and engineering conventions are defined in [`docs/13_BACKEND_ENGINEERING_GUIDE.md`](docs/13_BACKEND_ENGINEERING_GUIDE.md). The [`adr/` catalog](adr/README.md) records durable architecture decisions, and the root [`AGENTS.md`](AGENTS.md) defines mandatory operating rules for AI agents.

System instructions and direct human instructions override repository documentation. Within repository documentation, authority is scoped by subject: accepted ADRs govern accepted architectural decisions; [`docs/03_ARCHITECTURE.md`](docs/03_ARCHITECTURE.md) governs system-level boundaries; [`docs/13_BACKEND_ENGINEERING_GUIDE.md`](docs/13_BACKEND_ENGINEERING_GUIDE.md) governs backend implementation and engineering conventions; and [`AGENTS.md`](AGENTS.md) governs agent behavior across the repository. [`docs/08_CODING_STANDARD.md`](docs/08_CODING_STANDARD.md) remains the repository-wide coding baseline.

Approved requirements and domain authority define what the system must preserve. A direct human instruction that changes a durable product or architectural decision must update the appropriate requirement, ADR, or governing document as part of the authorized change. Material conflicts must be surfaced rather than resolved through undocumented drift.

## Assumptions

- OwnSIS begins as a greenfield implementation with no obligation to preserve OpenSIS code, schemas, or interfaces.
- Each organization is one tenant and retains its own isolation boundary even when future domain relationships connect organizations.
- OwnID remains the sole identity provider, while OwnSIS remains responsible for authorization decisions over its own resources.
- Moodle does not become the source of truth for OwnSIS academic or administrative records.
- PostgreSQL is the authoritative transactional data platform for OwnSIS.
- The product will be maintained by changing teams over a horizon of at least fifteen years.
- Business capabilities and detailed domain rules will be established through deliberate domain discovery rather than inferred from legacy behavior.

## Future Evolution

The repository is expected to grow through bounded, reviewable increments. Domain modules, public contracts, storage models, deployment topology, and integration details will be introduced only when supported by requirements and documented decisions. The modular monolith may evolve internally or yield independently deployed components when measured operational or organizational needs justify that change; such evolution must preserve ownership, security, observability, and data consistency and must be recorded through ADRs.
