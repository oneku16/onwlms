# ADR-0005: Generate Frontend API Types from Versioned OpenAPI

- **Status:** Proposed
- **Decision date:** 2026-08-05
- **Decision owners:** OwnSIS backend and web maintainers

## Purpose

Keep the FastAPI and Next.js application contract aligned without sharing ORM or
domain implementation types across runtime boundaries.

## Context and Decision Drivers

The web application needs strict TypeScript types, while hand-maintained copies
of backend request and response structures drift. A Python package shared with
the browser would leak backend implementation concerns and couple build systems.

## Decision

FastAPI's explicit request and response schemas produce a deterministic,
versioned OpenAPI artifact. The frontend uses `openapi-typescript` to generate
contract types from that artifact. Runtime API boundaries still validate
security-critical or externally variable data and never treat TypeScript as
server authorization.

Generated files are machine-owned, carry a generation notice, and are checked
for drift in validation. Public schema changes are reviewed for compatibility.
No ORM model, database row, or internal domain object is serialized
automatically to satisfy generation.

## Consequences and Risks

One source describes the HTTP contract and strict frontend compilation catches
drift. OpenAPI cannot express every semantic rule, permission, or temporal
constraint, so documentation and behavioral tests remain required. Generated
churn is controlled through deterministic formatting and review.

## Alternatives Considered

- **Handwritten duplicate interfaces:** rejected because they drift silently.
- **A language-neutral schema framework added now:** deferred because OpenAPI is
  already available and a new framework has no demonstrated benefit.
- **Sharing backend implementation models:** rejected because it violates
  adapter and module boundaries.

## Assumptions and Reassessment

Versioned HTTP remains the browser-facing application boundary. Reassess if
another first-class client protocol becomes authoritative. Acceptance requires a
clean regeneration check and frontend contract tests.
