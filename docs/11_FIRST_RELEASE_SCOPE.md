# OwnSIS First-Release Scope and Module Map

## Purpose

This document records how the approved first-release brief is mapped onto owned
capabilities without weakening the foundation documents. It supplies the module
declarations needed to implement the brief; detailed institutional policy remains
configurable or explicitly deferred when stakeholder evidence is absent.

## Release Interpretation

The first release is a controlled working product, not a claim of universal
institutional policy or completed production certification. It must run locally,
exercise the critical end-to-end academic journey, enforce tenant isolation, and
provide real application behavior for exposed actions. External providers that
need credentials use real ports and safe controlled adapters; their production
verification remains credential-gated.

The release uses these reversible policy defaults:

- a person record is tenant-owned; one OwnID subject can link to separate person
  and membership records in several organizations without joining their PII;
- built-in roles map to explicit permissions, and memberships may hold several
  roles; authorization and subscription entitlement remain separate;
- admissions, enrollment approvals, term closure, and grade amendments use
  explicit state transitions rather than a generic workflow engine;
- organization policy stores education mode, credit unit, maximum-credit,
  approval, quota, deadline, and scheduling preferences rather than assuming one
  university model;
- official results are append-revised and Moodle observations remain external
  evidence until grading policy accepts them;
- paid communication, Microsoft 365, payment, object storage, DNS, and certificate
  providers fail explicitly until configured; Finance balances and attendance are
  not invented.

## Module Map

### Organizations

Owns organization identity, slug, lifecycle, type, locale, timezone, branding,
custom-domain metadata, non-secret OwnID tenant/client references, academic
configuration, and campuses. Platform operations create, suspend, reactivate,
and recover ownership through separate permissions and audit. Moodle activation
and credentials are owned by Integrations; feature availability is owned by
Entitlements.

### Identity and People

Identity owns OwnID subject references, OIDC pending flows, encrypted server
sessions, platform-administrator appointments, and the public actor-context
contract. People owns tenant-local people, safe contact methods, memberships,
multiple role assignments, student/teacher/staff/guardian profiles, and explicit
guardian-student links. National identifiers and contact values are sensitive,
never diagnostic metadata, and only enter explicit safe serializers.

### Entitlements

Owns global plans and feature definitions, organization subscriptions, usage
limits, and tenant entitlement resolution. It answers whether a capability is
available; Identity/People answers whether the actor has permission. Callers use
the centralized resolver rather than scattered premium flags.

### Academics

Owns academic years, terms, calendar events, faculties, departments, programs,
courses, offerings, cohorts, rooms, teacher assignments, academic enrollment,
course enrollment, curricula, curriculum-course classification, prerequisites,
credit rules, selection requests, approval records, and administrative override
facts. Campus identifiers are consumed through the Organizations public contract
and are not duplicated.

### Admissions

Owns applicants, applications, intake/program choice, document metadata, reviews,
decisions, quotas, seat categories, seat reservations, and deposit-required
metadata. It publishes an accepted conversion request; People and Academics own
the resulting student profile and academic enrollment. Payment execution is a
port and is not treated as complete without a configured provider.

### Grading

Owns grading scales and mappings, official final grades, credits attempted and
earned, GPA contribution, transcript read models, immutable revisions, amendment
reason, and term-closure enforcement. It alone accepts or rejects Moodle grade
evidence as an official result.

### Scheduling

Owns teacher availability, scheduled sessions, hard and soft constraint
evaluation, proposal generation, locked-session regeneration, conflict
explanations, and explicit proposal acceptance. It consumes stable room,
offering, group, teacher, and calendar identifiers through Academics contracts.
ADR-0006 documents the first deterministic heuristic and its limits.

### Integrations

Owns tenant integration activation, encrypted credentials, external identifier
mappings, synchronization status, bounded live deadline evidence with
observation/source metadata, and duplicate-safe grade evidence records. Deadline
reads are constrained to the mapped user's enrolled Moodle courses and are not
served from a local cache. Moodle uses supported web services only. Selected-term
grade reconciliation, authenticated grade-event ingress, retry/quarantine, and
official-grade acceptance remain deferred until explicit mapping and grading
policy are approved. Integration data cannot overwrite an owning domain.

### Outbox and Provisioning

Outbox owns durable versioned publication, leases, attempts, retry timing, and
quarantine. Provisioning owns destination-specific job state after an accepted
student or employee activation and calls replaceable OwnID, Moodle, Microsoft
365, and notification ports. Partial success is visible and replay is idempotent.

### Notifications

Owns tenant-recipient preferences, constrained templates, rendered in-app
messages, channel delivery state, retry outcomes, and provider references. In-app
delivery is functional. Email, SMS, WhatsApp, and Telegram adapters are
replaceable and explicitly unavailable in production until configured. No
channel sends permanent plaintext passwords.

### Audit

Owns append-only evidence mechanics and authorized read access. Originating
modules own which facts require evidence and submit minimized audit facts through
explicit sinks; accepted-profile activation also publishes its event atomically
through the outbox. Not every application mutation and audit append shares one
database transaction, so that stronger guarantee remains a known gate rather
than a release claim. Audit contains actor, organization, action, target
reference, time, source, outcome, correlation, and required reason without
credentials or unnecessary PII.

### MCP Gateway

Owns the OwnID-authenticated protocol boundary and the curated read-only tool
catalog. It calls public authorized application query contracts and never reads
module tables. Every invocation revalidates membership, permission, resource
relationship, organization context, and MCP entitlement. The first release does
not expose grade mutation or another consequential write.

### Web Application

The Next.js application composes platform administration, organization
administration, student, teacher, guardian, staff, and guest experiences. It
shows the active organization, permissions, entitlements, integration state,
loading/empty/error outcomes, and tenant branding. Hidden navigation is not an
authorization boundary. Finance and absent attendance data are visibly
unavailable rather than fabricated.

## Collaboration and Consistency

Immediate invariants stay inside one owning module transaction. Accepted-profile
activation uses versioned outbox events when partial provisioning progress must
be visible. PostgreSQL-backed outbox processing provides atomic publication and
at-least-once delivery for that implemented path, and its consumers are
idempotent. Broader notification, integration-reconciliation, and audit outbox
coverage remains incomplete and must not be inferred from this contract.

Cross-module reads use public application contracts or projections. Stable UUIDs
may be referenced, but another module's mutable ORM model or table interpretation
is never imported. Architecture tests enforce inward layer dependencies and ban
cross-module infrastructure imports.

## Security and Acceptance Evidence

Every tenant table is subject to explicit repository scoping, tenant-aware
constraints, and the RLS approach in ADR-0002. Protected application use cases
receive a verified actor context from Identity. Platform operations are distinct
from tenant operations. Sensitive serialization, CSRF, callback replay,
cross-tenant access, role/permission, grade-history, event duplication,
integration failure, and MCP resource checks require automated negative tests.

The target critical release journey is:

1. a platform administrator creates an organization and appoints an owner;
2. the owner establishes an OwnID-backed or explicit local-test session;
3. the owner configures organization and academic structure;
4. an administrator creates or converts and enrolls a student;
5. activation publishes idempotent provisioning jobs;
6. staff create a course offering and official schedule;
7. the student reads the tenant-scoped schedule;
8. Moodle evidence is accepted through official grading policy;
9. the student reads the official grade and GPA summary; and
10. equivalent access using another organization's actor or identifier is denied.

Steps 1–7, 9, and 10 have bounded application foundations and automated evidence.
Step 8 is not complete: Moodle evidence currently remains non-authoritative and
cannot become an official grade without an approved external-event authenticity,
course-enrollment, grading-scale, and closed-term reconciliation policy.

## Credential-Gated and Intentionally Deferred Work

Real OwnID, Moodle, Microsoft 365, email, SMS, WhatsApp, Telegram, payment,
object-storage, custom-domain DNS, and certificate verification require tenant or
platform credentials not stored in this repository. Production-grade optimizer
selection, attendance, Finance balances, HR, Library, Dormitory, advanced
analytics, automated certificate issuance, and destructive data-lifecycle policy
remain outside this release unless separately specified. Their navigation and
ports may be visible only as unavailable or entitlement foundations, never as
fake completed behavior.

## Governance

The module map is introduced by the direct first-release authorization. The
architecture choices in ADR-0002 through ADR-0006 remain Proposed until the
required human architecture, security, identity, database, and public-contract
reviews accept them. Implementation may exercise these reversible choices under
the direct brief, but a production promotion cannot treat Proposed records as
approved evidence.
