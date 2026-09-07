# OwnSIS Local Operation and Recovery Guide

## Purpose

This guide documents the supported first-release local workflow and the
production responsibilities that remain deployment-specific. Commands are run
from the repository root unless noted.

This is a local-development and recovery-responsibility guide, not evidence that
OwnSIS is production-ready. Current operational status is:

| Classification | Operational scope |
| --- | --- |
| Implemented locally | Locked dependency setup, Docker Compose services, separate PostgreSQL runtime/migration/worker roles, forward migrations, synthetic seeding, health/readiness, structured logs, API/worker shutdown, automated checks, and runtime image builds. |
| Partial | Outbox leasing/retry/quarantine, provisioning retry, safe integration status, and diagnostics exist, but generic quarantined-event replay, dashboards/alerts, service objectives, load isolation, release/rollback, privacy lifecycle, and exercised recovery are incomplete. |
| Credential-gated | Real OwnID, Moodle, and MCP compatibility and failure exercises require controlled provider tenants and secrets. |
| Deferred | Managed hosting, external notification providers, Microsoft 365 provisioning, payment/object-storage/domain providers, production backup automation, and incident/on-call integration are not supplied by this repository. |

## Local Setup

Requirements are Docker with Compose, `uv`, Python 3.14, Node.js 24 or newer,
and npm 11 or newer. Initial setup and dependency audits also require registry
and image-registry network access. Initialize locked dependencies, a private
local `.env`, and images:

```text
make setup
```

The setup command copies `.env.example` when `.env` is absent. On later runs it
preserves configured values, appends defaults that have not yet been declared,
and generates separate local encryption keys only where the server-session,
sensitive-person-field, or integration-credential key is missing or blank.

Start the complete local stack:

```text
make run
```

`make run` remains attached to the service logs. Compose starts PostgreSQL,
applies migrations, and then starts the API, worker, and frontend. Use a second
terminal for `make seed` or verification commands.

Open the web application at `http://localhost:3000`, API documentation at
`http://localhost:8000/api/docs`, liveness at `/health`, and dependency readiness
at `/ready`. Local development authentication is available only while
`APP_ENV=local` and `DEV_AUTH_ENABLED=true`; production validation rejects it.

Stop containers without deleting the development database with `make stop`.
Remove containers and networks with `make down`. The named PostgreSQL volume is
retained unless an operator explicitly requests volume deletion.

## Local Configuration and Provider Credentials

The default local workflow requires no external provider credential. A newly
created `.env` contains distinct Fernet keys for:

- `SESSION_ENCRYPTION_KEY` — server-side session material;
- `PII_ENCRYPTION_KEY` — sensitive tenant person/profile fields; and
- `INTEGRATION_ENCRYPTION_KEY` — external integration credentials.

If `.env` already exists, `make setup` preserves every nonblank configured value,
adds defaults that are not declared, fills blank or absent encryption keys with
distinct generated values, and restricts the file to its owner. To rotate a
development key deliberately, generate a replacement with:

```text
cd backend
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Do not reuse one generated value for all three purposes. Do not commit `.env`.

Real-provider testing requires the following additional configuration:

| Boundary | Required controlled configuration |
| --- | --- |
| OwnID browser login | `OWNID_ISSUER`, `OWNID_CLIENT_ID`, `OWNID_CLIENT_SECRET`, exact redirect and post-logout URLs, compatible scopes, and an OwnID client configured for Authorization Code + PKCE. |
| First platform administrator | `PLATFORM_ADMIN_BOOTSTRAP_SECRET` containing at least 32 characters, held in the deployment secret system only until one signed-in OwnID subject completes bootstrap. A blank value disables bootstrap. |
| Moodle | Tenant-scoped HTTPS Moodle base URL and least-privileged web-service token, encrypted through `PUT /api/v1/integrations/moodle/configuration`; required Moodle functions and tenant mappings must exist. No supported application workflow currently creates those mappings or orchestrates production provisioning, so credentials alone enable only the implemented status and bounded mapped-user reads. Live calls also require deployment egress policy and private/link-local/loopback destination enforcement; clean HTTPS syntax alone is not complete SSRF protection. |
| MCP | `MCP_ENABLED=true`, `MCP_AUDIENCE`, `MCP_RESOURCE_URL`, OwnID issuer/JWKS support, an access token carrying `ownsis:mcp:read`, an active membership, the correct role/resource relationship, and an enabled tenant MCP entitlement. The seeded development-base plan does not grant MCP. |

Production settings additionally require secure cookies, HTTPS application and
CORS origins, externally managed encryption/provider/database secrets, and
`DEV_AUTH_ENABLED=false`. The three PostgreSQL URLs must represent the intended
least-privilege async API, synchronous migration, and async worker roles. Real
external notification, Microsoft 365, payment, storage, DNS, and certificate
adapters are unavailable in this release; credentials alone do not enable them.

### Platform-administrator bootstrap and recovery

Use bootstrap only when the database has no active platform administrator:

1. generate a high-entropy value outside the repository and place it in
   `PLATFORM_ADMIN_BOOTSTRAP_SECRET` through the deployment secret system;
2. restart the API, sign in through OwnID, and submit the secret to
   `POST /api/v1/platform/administrators/bootstrap` with the session-bound CSRF
   header;
3. verify the successful global audit intent and outcome records;
4. clear the bootstrap secret and restart the API; and
5. assign at least one additional trusted administrator through
   `POST /api/v1/platform/administrators/{subject_id}/assign` before attempting
   administrator rotation.

Bootstrap closes atomically as soon as any active administrator exists. The
ordinary revocation endpoint refuses to deactivate the final active
administrator. Do not bypass either safeguard with direct database updates. A
target must already be an OwnSIS identity subject established through OwnID
sign-in; administrator assignment does not create an identity or credential.

Tenant membership administrators use `GET /api/v1/memberships` under an exact
`X-Organization-ID` context, then the suspend, reactivate, or revoke endpoint for
the selected membership. These endpoints never govern organization owners.
Revocation takes effect when tenant authorization re-reads the persisted
membership. It intentionally does not delete the subject's global identity
session or revoke provider refresh families because those credentials can also
support another tenant membership or platform responsibility.

Platform administrators govern owners from `/platform/owners`. The page reads
the PII-free
`GET /api/v1/platform/organizations/{organization_id}/owners` projection and
uses the corresponding `POST .../owners/{membership_id}/suspend` or
`POST .../owners/{membership_id}/revoke` operation. Establish another active
owner before either transition. The backend rejects non-owner, cross-tenant,
already-terminal, and final-active-owner targets. Concurrent attempts to remove
the last two active owners serialize on the tenant's owner rows; only one can
succeed. Do not bypass this safeguard with direct database updates.

## Database Evolution

Start PostgreSQL if necessary and apply committed migrations with:

```text
docker compose up -d --wait postgres
make migrate
```

`make run` performs the same upgrade through its one-shot `migrate` service.
Create a reviewed candidate migration with:

```text
make migration name="describe the owned schema change"
```

The synchronous migration role is separate from the async request/worker roles.
Every tenant-owned table must be classified, indexed for its access path, and
receive forced RLS and grants in the same migration. Validate a migration from
an empty database and from every supported release state. Never edit a migration
already applied to a shared environment.

Check that the database is at one migration head and that SQLAlchemy metadata has
not drifted:

```text
make migration-check
```

The migration chain is forward-only for data-bearing changes. The initial
schema, admissions-conversion, and teacher-availability migrations raise an
error from their downgrade functions; the worker-audit grant migration is
safely reversible. The initial downgrade is **not** allowed, even for an empty
development schema. It would discard the entire schema and cannot preserve
authoritative data. Recovery uses a reviewed forward repair or a verified
restore; never present `alembic downgrade base` as a supported rollback.

## Development Data

Development data is created only after PostgreSQL is reachable and migrations
are current:

```text
make migrate
make seed
```

The seed command refuses to run outside local development and uses synthetic
names/identifiers. Application startup never inserts fake records automatically.
Re-running the seed is idempotent.

## Verification

Use focused commands during development and the aggregate gate before handoff:

```text
make lint
make typecheck
make test
make frontend-build
make backend-build
make validate
```

`make openapi` exports the backend schema and regenerates strict frontend API
types. A resulting diff is a public-contract change and must be reviewed.

The exact command responsibilities are:

| Command | What it verifies |
| --- | --- |
| `make test` | Backend pytest suite and frontend Vitest suite. |
| `make lint` | Backend Ruff lint/format checks, frontend ESLint, and `git diff --check`. |
| `make typecheck` | Strict mypy over backend source/tests and TypeScript checking. |
| `make openapi-check` | Backend schema export and committed frontend OpenAPI type consistency. |
| `make migration-check` | Current migration head and SQLAlchemy/Alembic model drift against the configured database. |
| `make audit` | Python, frontend, and OpenAPI-tool dependency audits; registry access is required. |
| `make validate` | OpenAPI, lint, type, tests, frontend build, audits, Compose configuration, and backend/frontend runtime image builds. |

`make validate` does not run `make migration-check`; execute both when persistence
changes. The PostgreSQL tenant-enforcement suite is opt-in locally because it
requires a real initialized PostgreSQL database and runtime roles:

```text
docker compose up -d --wait postgres
make migrate
OWNSIS_RUN_POSTGRES_INTEGRATION=1 make test
```

Without `OWNSIS_RUN_POSTGRES_INTEGRATION=1`, the PostgreSQL tests are skipped. CI sets
the flag and provisions the NOBYPASSRLS roles. Report skipped tests as skipped,
not as passed PostgreSQL evidence.

## Health and Diagnostics

`/health` reports only process liveness. `/ready` tests the required PostgreSQL
dependency and returns 503 when the process must not receive traffic. Logs are
structured and use correlation IDs; they intentionally omit request bodies,
credentials, contact values, national identifiers, grade payloads, and external
provider responses.

Operational dashboards must track API readiness/error/latency, authorization and
tenant-context denials, database pool pressure, outbox pending/retry/quarantine
depth, oldest work age, provisioning status by safe category, notification
delivery outcomes, Moodle freshness/reconciliation differences, and worker
throughput. Tenant identifiers must not become unbounded metric labels.

## Moodle Deadline Evidence

Student and teacher deadline endpoints do not read a local deadline cache. Each
request first revalidates the OwnSIS actor and mapped tenant person, then makes a
bounded live Moodle call for that external user's enrolled courses and requests
assignments only for those course identifiers. Unexpected course results are
discarded. Returned evidence carries observation time and source version.

Consequences for operation:

- Moodle latency or outage can fail that optional read and must not change an
  authoritative OwnSIS academic record;
- there is no stale-cache fallback to present as current data;
- a missing person mapping returns no deadline evidence rather than guessing;
- the deadline read requires the allowlisted user-course and assignment
  functions; a shared integration token also needs only the other allowlisted
  functions for explicitly enabled provisioning operations; and
- provider compatibility, throttling, timeout, malformed-response, and extended
  outage behavior remain credential-gated controlled-environment tests.

MCP is disabled by default. Enabling the MCP mount does not bypass ordinary
portal behavior or authorization; each tool invocation revalidates OwnID subject,
membership, permission, resource ownership, tenant, and MCP entitlement and
records minimized audit evidence.

## Outbox and Worker Recovery

Workers claim bounded event batches with leases and `SKIP LOCKED`. A crash may
cause duplicate delivery; handlers use event idempotency keys and declared
reconciliation. Do not mark work complete manually or edit a payload.

For a backlog:

1. identify affected event types, tenants, age, and error codes without reading
   protected payloads;
2. suspend a compromised provider or noisy tenant through its governed
   capability;
3. correct configuration or code and deploy the same compatible release to API
   and workers;
4. retry an eligible provisioning job through
   `POST /api/v1/operations/provisioning/{job_id}/retry` in bounded batches; and
5. verify downstream state through the owning application's reconciliation or
   status capability.

The worker automatically retries eligible outbox events and quarantines terminal
failures. A generic operator API for replaying a quarantined outbox event is not
implemented in this release. Stop and implement/review that application
capability when required; direct database updates are not an accepted replay
mechanism.

## Backup and Restore Exercise

Production operators must use managed encrypted backups with access separation.
At a risk-appropriate cadence, restore the selected backup into an isolated
environment with outbound integrations disabled. Record source backup identity,
start/end time, integrity result, migration version, tenant row counts using safe
aggregates, RLS negative tests, application readiness, and destruction of the
exercise environment.

A restore is successful only when authoritative state is interpretable and an
ordinary tenant role cannot access another tenant. This repository does not claim
a restore exercise until an operator records that evidence for the selected
hosting environment.

## Credential Compromise

On suspected session, OwnID client, Moodle, notification, database, encryption,
CI, or hosting credential compromise:

1. contain access and preserve audit/log evidence;
2. disable the affected integration or process role without weakening OwnSIS
   authority;
3. rotate/revoke credentials in the owning secrets or provider system;
4. invalidate affected application sessions or encrypted material when key-ring
   migration is unavailable;
5. assess tenants, records, and external effects using safe correlation and audit
   data; and
6. restore service only after negative-path verification.

Never place compromised values in an issue, chat, log, fixture, or incident
report.

OwnSIS checks the current OwnID token family through the provider introspection
endpoint on protected session use. Provider-inactive or mismatched sessions are
deleted locally. Provider unavailability denies the protected operation with a
service error; it does not preserve an authorization decision as successful.
Interactive logout always deletes the local session first. When OwnID discovery
advertises an end-session endpoint, the API returns a provider logout URL built
with the ID-token hint, configured post-logout redirect URI, and fresh state;
the frontend follows only an HTTPS URL. Revocation or end-session discovery
failure cannot restore the deleted local session.

## Troubleshooting Commands

Begin with state and safe logs rather than changing data:

```text
docker compose ps
docker compose logs postgres migrate backend worker frontend
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/ready
```

Common cases:

- **Setup cannot update `.env`:** verify that the repository directory and file
  are writable. Setup preserves nonblank configured values, appends absent
  defaults, generates blank or missing Fernet keys, and restricts the file to
  its owner. Use the rotation command in
  [Local Configuration and Provider Credentials](#local-configuration-and-provider-credentials)
  only when an intentional local key replacement is required.
- **Database is unavailable or seed fails:** run
  `docker compose up -d --wait postgres`, then `make migrate`; confirm success
  with `docker compose ps`, then run `make seed`.
- **Readiness is 503 while liveness is 200:** inspect
  `docker compose logs postgres migrate backend`; readiness intentionally fails
  until PostgreSQL can be reached.
- **Port binding fails:** identify the process using ports `3000`, `5432`, or
  `8000`. If changing a port, update Compose plus the matching application,
  callback, CORS, and backend URLs together.
- **Migration check reports multiple or stale heads:** do not stamp or edit a
  shared database to hide the result. Review `cd backend && uv run alembic heads`,
  the migration graph, and the intended forward repair.
- **PostgreSQL isolation tests are skipped:** start the initialized PostgreSQL
  service and rerun `OWNSIS_RUN_POSTGRES_INTEGRATION=1 make test`.
- **OpenAPI check differs:** for an intentional API change run `make openapi`,
  review the schema and generated TypeScript diffs, then rerun
  `make openapi-check`. Otherwise revert the unintended contract change through
  the normal review workflow.
- **Dependency audit cannot reach a registry:** retain the failure result and
  retry when the registry is available. Do not claim `make validate` passed.
- **Moodle deadlines fail:** check the safe status at
  `GET /api/v1/integrations/moodle/status`, tenant entitlement, person mapping,
  token function permissions, and provider availability. Do not log the token or
  provider response body.

For a disposable local environment only, the following command deletes the named
PostgreSQL volume and all local data irreversibly:

```text
docker compose down -v
```

Do not use it as migration recovery or against any data that must be retained.

## Production Promotion Limits

Production hosting must supply HTTPS, managed PostgreSQL, encryption-at-rest,
secret management, backup/restore, network egress policy, observability,
rate/concurrency limits, and least-privilege process identities. Vercel can host
the web runtime and a container platform can host API/worker roles, but vendor
selection does not change domain ownership.

Before promotion, human reviewers must accept applicable ADRs and complete
identity, tenant/RLS, migration, integration, accessibility, load/noisy-tenant,
penetration, backup, recovery, incident, dependency/image, privacy/retention, and
operational-readiness evidence. Local green checks alone do not establish
production readiness.
