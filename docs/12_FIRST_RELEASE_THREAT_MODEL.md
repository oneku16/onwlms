# OwnSIS First-Release Threat Model

## Purpose and Scope

This threat model covers the browser, Next.js runtime, FastAPI boundary,
PostgreSQL, request and worker process roles, OwnID OIDC flow, Moodle web
services, notification/provisioning ports, audit, and MCP read gateway included
in the first-release scope. It supplements `07_SECURITY.md`; it does not approve
a production deployment or replace deployment-specific review.

Protected assets include tenant academic and administrative records, official
grades and history, membership and authorization state, sensitive person/contact
data, session and integration credentials, event and provisioning state, audit
evidence, and shared platform availability.

## Trust Boundaries and Controls

| Boundary | Primary threats | Required controls and evidence |
| --- | --- | --- |
| Browser → Next.js/FastAPI | session theft/fixation, CSRF, XSS, tenant-header tampering, IDOR | HttpOnly/Secure/SameSite session cookie, rotation after login, server-stored tokens, CSRF cookie/header plus server session, CSP/security headers, explicit schemas, verified membership for organization context, resource tenant checks, denied-path tests |
| OwnID → Identity adapter | forged/replayed/misdirected or revoked tokens, malicious discovery/JWKS, callback replay, open redirect | exact issuer/audience/RS256/time/nonce validation, HTTPS issuer, redirect allowlist, state/nonce/PKCE, one-time pending flow, client-authenticated token introspection on protected session use, bounded no-follow HTTP, key-rotation tests, fail-closed production settings |
| Application → PostgreSQL | omitted tenant predicate, SQL injection, excess privileges, stale pool context | parameterized SQLAlchemy queries, tenant-scoped repository contracts, transaction-local tenant setting, forced RLS, tenant-aware constraints, runtime/migration/worker role separation, two-tenant tests using the runtime role |
| API → application modules | role confusion, entitlement/permission confusion, direct state mutation | verified actor context at every protected use case, deny by default, separate permission and entitlement resolution, thin routes, explicit state machines and version/conflict checks |
| State change → outbox/worker | lost event, duplicate effect, replay, cross-tenant job, poison payload, noisy tenant | atomic outbox publication, immutable tenant/correlation/version/idempotency context, `SKIP LOCKED` leases, idempotent handlers, bounded retries, quarantine, safe error codes, per-tenant metrics/limits, replay through normal policy |
| OwnSIS → Moodle/providers | credential leakage, SSRF/redirect, provider compromise, timeout, duplicate effects | encrypted tenant credentials, clean HTTPS origin validation, no redirects, allowlisted functions, bounded timeouts, idempotency/mappings, anti-corruption translation, observable failure/reconciliation, no payload logging. Private/link-local/loopback resolution and approved-egress enforcement remain a production blocker before live Moodle calls are enabled. |
| Moodle → official grading | forged/duplicate/stale evidence, Moodle becoming authoritative | authenticated integration path, tenant/external-event uniqueness, provenance and observed time, grading-module acceptance policy, immutable official revisions, rejected-state visibility |
| MCP client/model → tools | stolen bearer, prompt/tool-output injection, fabricated IDs, overbroad scope, cross-user/tenant reads | OwnID bearer verification, required MCP scope, explicit organization input re-bound to membership, permission/resource/entitlement checks per call, minimum read-only tools, no database access, minimized outputs, audit; no grade writes |
| Operators/support → tenant data | silent impersonation, broad database access, evidence destruction | no ordinary platform-admin tenant-data bypass, explicit tenant-bound support capability/reason/time limit, separate credentials, append-only audit, reviewed access, protected backup/restore procedures |
| Build/deploy → runtime | compromised dependency/image, secret in source/image, mutable artifact | locked uv/npm dependencies, dependency/secret/image scans, multi-stage non-root images, runtime secrets, read-only CI permissions, source revision labels, artifact promotion policy |

## High-Risk Abuse Cases

### Cross-tenant identifier substitution

An authenticated organization A user submits an organization B person, course,
application, schedule, notification, or grade identifier. The actor resolver
validates active membership for A, the application verifies resource ownership,
the repository includes A, and RLS prevents returning or mutating B. Public
not-found/forbidden responses do not reveal which check failed. Tests repeat this
case for reads, writes, references, events, MCP, and support access. Academic
teacher assignments and student enrollments also validate the People-owned
profile kind, so a same-tenant Student UUID cannot be substituted for a Teacher
or vice versa. Grade and admissions targets are revalidated against current
enrollment and term lifecycle state instead of trusting identifier possession.

### Platform administrator academic-data access

A platform administrator attempts to reuse platform permission against tenant
academic endpoints. Tenant endpoints require a `TenantActorContext`; selecting an
organization requires an active matching membership. Platform context only
reaches global organization/plan/subscription administration. Any future support
read is a distinct audited capability and is absent until its time/reason policy
is approved.

### OIDC callback and session replay

An attacker reuses state/code or fixes a pre-authentication cookie. Pending state
and PKCE verifier expire and are consumed once before code exchange. The callback
validates nonce and token claims, creates a new random session identifier, and
invalidates the prior flow. Cookies never contain provider tokens. Logout clears
the local session even if provider revocation is temporarily unavailable and
records that partial outcome safely.

Protected session use introspects the refresh token family when available and
otherwise the access token. An inactive token, wrong subject, or wrong client
binding deletes the local session and denies the request. An OwnID outage does
not convert into authorization success.

Concurrent refreshes serialize on the exact server-session row before OwnSIS
presents a rotating refresh token to OwnID. The lock holder rechecks the session
version; a queued stale request returns a conflict without provider token reuse.
Inactive-introspection deletion is version-conditional, so a stale result cannot
delete a newer rotation.

### Platform-administrator bootstrap or lockout

An attacker with an ordinary signed-in account attempts to become a platform
administrator, or two administrators concurrently revoke the final assignment.
Bootstrap additionally requires a high-entropy deployment secret and is accepted
only while the serialized active-administrator count is zero. Normal assignment
and revocation require current platform permission. A PostgreSQL transaction
advisory lock serializes empty-set bootstrap and final-admin checks. Audit intent
must persist before mutation, and the final active administrator cannot be
revoked.

### Membership revocation with a stale session

A revoked member continues using an already established OwnSIS or OwnID session.
Tenant actor resolution re-reads the exact membership and accepts only `active`.
Revocation therefore denies that tenant immediately without deleting the
subject's global identity session or revoking provider tokens that may still
support another tenant membership or a platform responsibility. Organization
owners cannot be suspended, reactivated, or revoked through the ordinary tenant
membership-manager path. Each lifecycle, role, or owner-recovery mutation locks
and rehydrates the exact tenant membership before reapplying its domain rule, so
stale concurrent requests cannot restore revoked access or erase owner status.
Separately authorized platform administrators may list a PII-free owner
lifecycle projection and suspend or terminally revoke an owner only while
another active owner remains. The persistence adapter locks every owner
membership row in that exact organization in deterministic order. If two
requests concurrently remove the last two active owners, one commits and the
other revalidates against the new state and fails; zero active owners is never a
successful outcome.

### Grade history erasure

An authorized teacher attempts to overwrite a final grade, especially after term
closure. Grading creates a revision containing the previous and new official
value. Closed-term amendment requires an explicit non-empty explanation and the
amend permission. Moodle supplies evidence only; it cannot write the grade table.
The change emits audit evidence with no unnecessary student data. A permitted
initial grade after closure also preserves its explanation and closure flag as
immutable Grading-owned recording evidence; later revisions cannot overwrite it,
and authorized history readers can inspect it.

### Integration credential or payload exfiltration

An attacker causes a provider error or inspects status APIs. Credentials remain
encrypted in the database and are decrypted only inside the adapter. Redirects
are disabled, provider functions/destinations are allowlisted, response bodies
and exception text are not logged or returned, and status exposes only safe
codes, timings, and references.

### Worker replay and duplicate effects

A worker crashes after an external provider accepts an effect but before the
outbox row completes. The lease becomes retryable; the handler uses the stable
idempotency key or deterministic reconciliation so the provider effect is not
duplicated. Attempts are bounded and terminal failure is quarantined visibly.

## Residual Risks and Required Human Review

- Proposed ADR-0002 through ADR-0009 require architecture/security ownership and
  acceptance before production promotion.
- Real OwnID issuer behavior, key rotation, revocation, logout, and claim shape
  require controlled-environment verification.
- Moodle web-service versions, enabled functions, OIDC auth plugin behavior,
  tenant rate limits, and event authentication require a real compatible test
  environment and contract fixtures.
- Encryption key storage/rotation, TLS termination, CSP deployment composition,
  database role grants, managed backup encryption, regional retention, and
  incident contacts depend on the selected hosting environment.
- File document metadata is implemented without object upload; malware scanning,
  signed download, retention, and object-store policy require a future storage
  decision before accepting document bytes.
- The deterministic scheduler can produce an incomplete proposal; an authorized
  human must review and publish it. It is not a safety control for calendar data.
- Dependency and container scanner findings require human exploitability and
  licensing review; automated success alone is not release approval.
- Penetration, accessibility, load/noisy-tenant, backup-restore, migration-
  recovery, and incident-response exercises remain mandatory Gate 5 evidence.

## Verification Checklist

- Two real PostgreSQL tenants exercise read, write, foreign-reference, outbox,
  notification, integration, audit, and MCP denial paths with the runtime role.
- OIDC state/nonce/PKCE/callback replay, session rotation, secure-cookie, CSRF,
  logout, invalid issuer/audience/expiry/signature, and token-leak tests pass.
- Permission changes take effect without waiting for an identity-provider session
  to expire; entitlement alone never grants a user permission.
- Membership lifecycle tests cover tenant scoping, owner protection, audit-intent
  failure, immediate revoked-tenant denial, preservation of an unrelated tenant
  membership, concurrent revoke-versus-reactivate/role/owner races, and real-role
  PostgreSQL serialization of concurrent owner suspension and revocation.
- Platform-administrator tests cover one-time bootstrap, wrong-secret denial,
  assignment/revocation audit ordering, and final-admin protection.
- Official-grade revision and term-closure negative cases preserve history.
- Outbox duplicate, crash/retry, quarantine, and tenant-context tests pass.
- Provider timeout, invalid authentication, redirect, malformed result, duplicate
  event, reconciliation, and disablement tests pass without payload disclosure.
- MCP tools reject a different tenant, different person, unassigned section,
  unlinked student, missing permission, missing scope, and missing entitlement.
- Images run non-root; dependency, image, and secret scans are reviewed; production
  configuration fails closed; OpenAPI/docs exposure follows environment policy.
