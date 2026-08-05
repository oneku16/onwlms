# ADR-0004: Use a PostgreSQL Transactional Outbox Worker

- **Status:** Proposed
- **Decision date:** 2026-08-05
- **Decision owners:** OwnSIS platform and integration maintainers

## Purpose

Provide reliable local-first event publication, provisioning, Moodle
synchronization, notifications, reconciliation, and retry processing without a
message broker.

## Context and Decision Drivers

Accepted state changes must not be silently disconnected from required side
effects. External providers fail independently and event delivery must tolerate
duplicates, retries, reordering, and partial failure. Kafka or RabbitMQ would add
an unproven distributed dependency to the first release.

## Decision

The owning transaction appends a versioned event envelope to a PostgreSQL outbox
through a narrow publisher port. Events carry immutable organization, actor,
correlation, contract-version, and idempotency context with a minimized payload.

Worker processes run the same product version as the API. They claim due rows
with `FOR UPDATE SKIP LOCKED`, deliver at least once to explicitly registered
idempotent handlers, and record attempts and safe outcome codes. Failures use
bounded exponential backoff. Exhausted or unsupported work enters a visible
quarantined state and can be replayed only through normal validation and
authorization paths.

The outbox is not the domain source of truth and does not introduce event
sourcing. Handler registration is explicit rather than discovered through
import-time side effects.

## Consequences and Risks

State and required publication can commit atomically, workers can scale
horizontally, and local development needs no broker. PostgreSQL becomes both the
transactional store and work queue, so batch size, locks, indexes, cleanup,
per-tenant pressure, and quarantine depth require monitoring.

Long provider calls occur outside the claim transaction after a bounded lease;
duplicate delivery remains possible and is an expected contract condition. A
later transport must preserve event meaning and idempotency rather than promise
exactly-once behavior.

## Alternatives Considered

- **In-process fire-and-forget:** rejected because process failure loses work.
- **Scheduled polling of business tables:** rejected because it obscures intent,
  ownership, compatibility, and completion state.
- **Kafka or RabbitMQ:** deferred until measured throughput, fault isolation, or
  external-consumer needs justify their operational cost.

## Assumptions and Reassessment

PostgreSQL can support the initial outbox throughput. Reassess when queue load
materially interferes with transactional traffic or when independently operated
external consumers require broker semantics. Acceptance requires duplication,
lease, retry, quarantine, replay, tenant-pressure, and failure-recovery evidence.
