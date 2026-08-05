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
secret and provider tokens never reach the browser, logs, events, audit, or API
responses. `sub` is the stable external reference; email/name are display
attributes only.

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
No fallback password or alternate production identity provider exists.

**Compatibility and verification:** supported OwnID discovery/token behavior is
the contract version. Claim or endpoint changes require controlled compatibility
tests for success, bad issuer/audience/signature/time/nonce/state, replay, key
rotation, refresh rotation, revocation, and logout. Real-provider verification is
credential-gated.

## Moodle Web Services

**Implementation status:** configuration, encrypted credentials, identifier
mappings, supported user/course/enrollment calls, mapped-user deadline reads,
and duplicate-safe grade evidence storage exist. Authenticated grade-event
ingress, a selected-term reconciliation run, retry/quarantine for rejected or
failed grade evidence, and official-grade application do not. The remaining
paragraphs state the required contract for completing those paths; they are not
evidence that those paths are already available.

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
external-event unique key, but no authenticated ingress or retry worker is
currently installed. A completed synchronization path must treat at-least-once,
duplicate, and reordered work as normal.

**Failure and conflict:** implemented calls have bounded time and no redirects.
They record safe class codes, but grade-evidence retry/quarantine visibility is a
remaining requirement. Missing or ambiguous mappings are rejected, never
guessed. Moodle unavailability leaves authoritative OwnSIS records unchanged.
Any future disable operation must stop new exchange while retaining the minimum
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
