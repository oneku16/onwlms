# First-Release Integration Contracts

## Purpose

This document records authority, tenant configuration, security, delivery, and
failure behavior for first-release OwnID, Moodle, provisioning, notification, and
MCP boundaries. Payload schemas remain in versioned code/OpenAPI; a schema alone
does not replace these semantic obligations.

## OwnID OIDC Relying Party

**Purpose and owner:** Identity authenticates human actors through OwnID only.
OwnID owns credentials, authentication assurance, subject identity, provider
session, discovery, JWKS, token issuance, refresh, revocation, and logout.
OwnSIS Identity owns pending authorization flow, encrypted application session,
subject reference, and mapping into current OwnSIS authorization.

**Configuration and disclosure:** issuer, client identifier/secret, redirect URI,
post-logout URI, scopes, and encryption key are runtime settings. The client
secret, access token, and refresh token never reach the browser, logs, events,
audit, or API responses. The verified ID token remains server-side during normal
application use; the sole browser disclosure is the standard `id_token_hint`
inside the HTTPS end-session URL returned by an explicit CSRF-protected logout.
`sub` is the stable external reference; email/name are display attributes only.

**Protocol and validation:** browser login uses Authorization Code Flow with
PKCE, state, nonce, exact redirect allowlisting, single-use pending state, RS256
signature, exact issuer/audience, validity-time, and nonce validation. Discovery
and JWKS use bounded HTTPS calls and key rotation. Application session identifiers
rotate after callback and are server-side. Cookie-authenticated writes require
session-bound CSRF.

**Failure and lifecycle:** an unverifiable assertion, invalid configuration,
missing membership, suspended organization, missing permission, refresh failure,
or revoked/expired session fails closed. Logout clears local authority even when
provider revocation temporarily fails and reports only the safe partial outcome.
Refresh-token exchange is serialized on the exact PostgreSQL session row so the
same rotating token is never deliberately presented twice; queued stale
requests fail before contacting OwnID. Inactive introspection removes only the
session version that was checked.
When discovery advertises an end-session endpoint, OwnSIS builds the browser
redirect from that advertised endpoint, the ID-token hint, configured
post-logout URI, and fresh state; the browser follows only HTTPS. No fallback
password or alternate production identity provider exists.

**Compatibility and verification:** supported OwnID discovery/token behavior is
the contract version. Claim or endpoint changes require controlled compatibility
tests for success, bad issuer/audience/signature/time/nonce/state, replay, key
rotation, refresh rotation, revocation, and logout. Real-provider verification is
credential-gated.

## Moodle Web Services

**Implementation status:** configuration, encrypted credentials, identifier
mappings, supported user/course/enrollment calls, mapped-user deadline reads,
duplicate-safe grade evidence storage, tenant-signed grade-event ingress,
operator-initiated selected-term reconciliation runs, reviewer-visible
evidence state, and explicit Grading acceptance or rejection of that evidence
exist ([ADR-0010](../adr/ADR-0010-moodle-grade-evidence-acceptance.md),
Proposed). Real-provider verification of the reconciliation function, the
Moodle-side event sender, throttling, and outage behavior remains
credential-gated. Mapping management for Moodle users and offerings is still a
provisioning concern without its own administrative workflow.

**Grade evidence lifecycle:** every Moodle result enters as non-authoritative
evidence keyed by tenant plus external event identifier. Intake dispositions
each event as `review_required`, so it is stored `pending` with the reason code
`review_required`; a failing grading policy call stores `rejected` with an
opaque error class code. A tenant administrator holding
`integrations.grade_evidence.read` may list evidence (`GET
/api/v1/integrations/moodle/grade-evidence`, filterable by status and offering)
and runs. An actor holding `grading.final_grade.record` accepts one pending
item with a named grading scale (`POST
/api/v1/grading/external-evidence/{evidence_id}/accept`) or rejects it with an
audited reason (`.../reject`). Acceptance resolves the person through People and
the participation through Academics, then applies ordinary recording rules: an
initial grade, or a revision that also requires `grading.final_grade.revise`
and an explanation; closed terms require the closed-term permission and an
explanation. Evidence is resolved exactly once and keeps the accepted final
grade identifier, resolver, and time as lineage.

**Signed event ingress:** `POST /api/v1/integrations/moodle/grade-events/{organization_id}`
accepts a JSON object with `external_event_id`, `course_offering_id`,
`student_person_id`, `grade_value`, `observed_at` (timezone-aware ISO 8601),
and optional `source_version`. The sender signs the raw body with the tenant
secret configured through `PUT /api/v1/integrations/moodle/grade-event-secret`
(at least 32 characters, stored encrypted): `X-OwnSIS-Timestamp` carries unix
seconds and `X-OwnSIS-Signature` carries `v1=` plus the hex HMAC-SHA256 of
`v1:{timestamp}:` followed by the body. Signatures are compared in constant
time, timestamps outside a five-minute window are refused, bodies above 16 KiB
are refused, and the tenant plus event key suppresses replayed deliveries.
Authentication failures are audited without payload contents.

**Selected-term reconciliation:** `POST /api/v1/integrations/moodle/grade-reconciliations`
with a `term_id` (permission `integrations.grade_evidence.reconcile`) calls the
allowlisted `gradereport_user_get_grade_items` function for every mapped
offering of that term, translates course totals of mapped learners into
evidence with a deterministic external key, and records a run with counts of
observed totals, new evidence, duplicates, unmapped offerings, and unmapped
users plus a safe error code on failure. Runs are bounded to 200 offerings.

**Purpose and owner:** Moodle owns learning users as delivery accounts, learning
course shells, learning enrollment state, activities, and deadlines. OwnSIS owns
institutional people, course offerings, official enrollment, curriculum,
schedule, and official final grades. Moodle results are evidence until Grading
accepts them.

**Tenant configuration and credentials:** Integrations owns one clean HTTPS
Moodle origin, encrypted web-service token, status, opaque mappings, and safe
failure codes per organization. Completion requires explicit sync checkpoints,
attempts, and reconciliation-run state. Credentials are least-privileged to the
allowlisted functions and never leave the infrastructure adapter.

**Supported direction:**

- OwnSIS → Moodle: ensure delivery user, ensure course shell, enroll/suspend/remove
  student or teacher after authoritative OwnSIS state;
- Moodle → OwnSIS projection: assignments/upcoming deadlines with observation
  time and source version;
- Moodle → OwnSIS evidence: final-grade change event with tenant mapping,
  duplicate key, source version, and observation time;
- operator → both: selected-term reconciliation according to the authority map.

**Delivery and idempotency:** implemented activation-driven provisioning uses the
transactional outbox. Provisioning operations carry a stable idempotency key;
external IDs are tenant-scoped mappings. Stored grade evidence has a tenant plus
external-event unique key, so replayed events and repeated reconciliation runs
report duplicates instead of creating new evidence. There is no background
retry worker for evidence: rejected evidence stays visible with its reason code
and a reviewer decides explicitly.

**Failure and conflict:** implemented calls have bounded time and no redirects.
They record safe class codes; a failed reconciliation run is stored with that
code and marks the integration degraded. Missing or ambiguous mappings and
ambiguous participations are counted or refused, never guessed. Moodle
unavailability leaves authoritative OwnSIS records unchanged. Any future
disable operation must stop new exchange while retaining the minimum
mapping/evidence required for audit and reconciliation.

**Compatibility and verification:** the first adapter uses supported Moodle REST
web-service functions behind an allowlist. An organization must enable those
functions and compatible OIDC authentication behavior. Provider-version support
requires contract fixtures and a controlled environment covering malformed
responses, timeout, invalid auth, throttling, duplicate/reordered events,
partial failure, reconciliation, extended outage, and disablement.

## Provisioning Destinations

**Purpose and authority:** an accepted student/employee activation requests
replaceable OwnID linking/creation, Moodle delivery setup, Microsoft 365 setup,
and welcome notification. Provisioning owns orchestration/job state only; each
owning domain remains authoritative for person/employment/enrollment facts and
each provider owns its external account state.

One tenant/subject/target produces one idempotency key and observable job.
Destinations progress independently through pending, processing, retry,
succeeded, or terminal failed states. A partial success is not collapsed into a
global success. Retries are bounded and adapters reconcile stable external
references. Unconfigured production adapters fail explicitly. Recording adapters
are local/test-only and do not claim provider verification.

Microsoft 365 public API details and credentials are not approved in this
release, so only its port and failure-visible job exist. Implementing the real
adapter requires a separate authority/security/compatibility review.

## Notification Channels

**Purpose and authority:** Notifications owns tenant-recipient preferences,
bounded templates, rendered in-app content, delivery state, retries, and safe
provider references. Originating modules own why and when a message is required.

In-app delivery is authoritative within OwnSIS and available by default. Email,
SMS, WhatsApp, and Telegram are opt-in per recipient and require configured
tenant/platform adapters. External providers own transport delivery only, not
membership, academic records, or notification policy. Templates accept only
declared simple placeholders and cannot execute code. Messages never contain a
permanent plaintext password or provider credential.

External sends use a stable notification identifier as idempotency context,
bounded time/retry, and safe failure classification. Production provider APIs,
regions, retention, consent, sender identities, credentials, and delivery webhooks
remain credential/provider gated.

## MCP Resource Server

**Purpose and authority:** MCP exposes a minimal read-only catalog to compatible
AI clients. OwnID authenticates the bearer subject. OwnSIS application services
remain authoritative for membership, permission, entitlement, tenant/resource
relationship, and returned data. The model/provider owns no fact or permission.

**Authentication and scope:** the resource server verifies RS256 access tokens
through exact OwnID issuer/JWKS/audience/time checks and requires
`ownsis:mcp:read`. Each tool receives an organization identifier but rebinds it to
the verified subject's active membership, role permission, resource ownership,
and MCP entitlement at invocation time.

**Tool catalog:** student own schedule, official grades, upcoming events, and
bounded live Moodle deadline evidence for the mapped user's enrolled courses;
teacher assigned sections, authorized section roster, and grade-sync status;
guardian explicitly linked-student summaries. Outputs are minimum-data read
models with observation/source metadata where external. There is no grade
mutation, generic query, database, filesystem, code execution, secret, or ambient
network tool, and there is no local Moodle deadline cache.

**Failure, audit, and availability:** missing/invalid scope or context denies;
fabricated cross-tenant/user/resource IDs reveal no protected existence. Every
invocation records actor, organization, tool, outcome, and correlation without
retaining unnecessary prompts or records. MCP/provider outage does not prevent
ordinary OwnSIS use. Sensitive production use requires provider retention,
training, region, and subprocessor review outside this protocol contract.
