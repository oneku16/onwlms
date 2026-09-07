# ADR-0009: Serialize Academic Term Closure with Official Grade Writes

- **Status:** Proposed
- **Decision date:** 2026-08-07
- **Decision owners:** OwnSIS academics, grading, database, and architecture maintainers

## Purpose

Define how OwnSIS prevents Academic term closure from committing between an
official-grade closure check and the corresponding initial grade or revision
write, while preserving module ownership and tenant isolation.

## Context and Decision Drivers

Academics owns the one-way closed state of a term. Grading owns official final
grades and immutable revision history. A read-then-write flow across those
module-owned transactions is unsafe: a grade request can observe an open term,
then Academic closure can commit before the grade mutation commits. That race can
create an initial grade after closure or let an ordinary revision bypass the
closed-term permission and explanation rules.

The solution must coordinate independent application instances, avoid direct
cross-module table access, keep each module's persistence transaction within its
owner, remain safe with a bounded application connection pool, and return a
bounded retryable conflict rather than wait indefinitely.

## Decision

Academics and Grading participate in a tenant-term PostgreSQL transaction-scoped
advisory-lock protocol. Its signed 64-bit lock key is derived exactly as follows:

1. initialize BLAKE2b with an eight-byte digest and the 16-byte ASCII
   personalization value `ownsis-termgrade`;
2. append the organization's UUID as its 16 raw bytes;
3. append the term's UUID as its 16 raw bytes; and
4. interpret the eight-byte digest as a signed, big-endian integer.

The two UUID inputs have fixed lengths, so no delimiter is required. Organization
identity is part of every key and identical term UUIDs in different tenants do
not intentionally contend. Both adapters must implement this exact derivation;
changing any input or encoding requires a coordinated deployment because mixed
versions would otherwise acquire different locks.

Before checking closure, an official-grade create or revision acquires the key in
shared mode with `pg_try_advisory_xact_lock_shared`. The Grading service then
rechecks Academic's public tenant-scoped closure contract, applies the closed-term
authorization rules, and completes audit and Grading persistence while the
shared lock remains held. An initial grade after closure requires both the
separate closed-term amendment permission and a non-empty explanation. An
ordinary initial grade or revision cannot bypass that permission, and revision
history records the closure state observed under the guard. A permitted initial
grade after closure stores the normalized explanation and closure flag as
immutable recording evidence on the Grading-owned grade aggregate. Authorized
grade-history reads return that initial evidence together with later append-only
revisions; later amendments cannot replace the original recording metadata.

Academic term closure acquires the same key exclusively with
`pg_try_advisory_xact_lock` in the transaction that row-locks and closes the
tenant-owned term. It cannot commit while a cooperating grade mutation holds the
shared guard. After a grade mutation releases its guard, closure rechecks and
updates the Academic row through the normal Academic repository path.

Both paths fail fast with a retryable conflict when the try-lock is unavailable.
The advisory lock does not replace authorization, tenant scoping, domain
validation, optimistic revision checks, immutable history, or audit evidence.

The Grading guard uses a dedicated SQLAlchemy asynchronous engine constructed
from the application's existing SQLAlchemy URL object. The URL is passed as an
object and is never rendered, interpolated, or logged. The engine uses
`NullPool`, so the guard does not consume a connection from the bounded
application pool and retains no idle connection. A transaction context owns the
dedicated connection; normal exit commits it, and error or cancellation rolls it
back and closes it, releasing the transaction-scoped lock.

## Responsibilities

- **Academics** remains authoritative for term closure and owns the exclusive
  lock acquisition in the same transaction as the close mutation.
- **Grading** owns the shared guard, the under-guard closure recheck, closed-term
  authorization, grade persistence, immutable initial-record evidence, and
  immutable revision metadata.
- **Composition and operations** must account for the dedicated guard connection
  and must monitor connection demand, contention, conflicts, and long-running
  grade mutations.
- **Future writers** that close terms or create or revise official grades must
  participate in this exact protocol. Direct table writes cannot claim the
  serialization guarantee.

## Consequences and Risks

Cooperating Academic and Grading writers cannot commit the prohibited ordering,
including when they run in different backend processes. The modules continue to
communicate through a public application contract rather than reading each
other's tables, and advisory keys remain tenant-scoped.

Each active grade mutation temporarily requires up to two database connections:
one dedicated `NullPool` guard connection and one normal application-pool
connection at a time for the sequential Academic read, audit work, or Grading
persistence. The dedicated connection prevents an outer guard from exhausting a
one-slot application pool, but concurrent grade mutations can still increase
total PostgreSQL connection demand outside that pool. Deployment connection
limits, request concurrency, readiness, observability, and overload controls must
account for this cost before production readiness. Database unavailability or a
connection-limit failure remains an explicit request failure.

Try-lock contention returns a safe retry instead of waiting, so sustained write
load may require caller backoff. A BLAKE2b collision is extremely unlikely and
would conservatively serialize unrelated tenant terms; it cannot allow the race.
Cancellation and adapter failures release locks when the dedicated transaction
connection closes, but the pre-existing separate audit and persistence
transactions can leave truthful intent evidence when a later write fails.

The lock protocol itself adds no schema requirement. Grading separately persists
the initial closure flag and explanation on the final-grade aggregate so the
required reason is not discarded after authorization. It depends on PostgreSQL
advisory-lock semantics and on all authoritative writers cooperating.

## Alternatives Considered

- **Use the bounded application pool for the outer Grading guard:** rejected
  because a grade mutation also needs that pool for nested tenant-scoped reads
  and writes; concurrent requests can deadlock or starve a small pool.
- **Read the Academic term table from the Grading transaction:** rejected because
  it violates module ownership and creates cross-module persistence coupling.
- **Use only an Academic row lock:** rejected because Grading does not own or
  mutate that row and its independent persistence transaction would not remain
  protected through commit without cross-module transaction sharing.
- **Run the broad workflow at serializable isolation:** not selected because it
  broadens database cost and retry behavior and still needs deliberate
  cross-transaction coordination.
- **Use triggers or new cross-module constraints:** rejected because they couple
  module schemas and cannot express the permission and explanation policy.
- **Introduce a platform-wide shared lock abstraction:** deferred because this is
  one narrow, explicitly versioned collaboration protocol; a general abstraction
  would be premature.

## Assumptions and Reassessment

Academics and Grading use the same PostgreSQL deployment, Academic closure is
one-way, and all authoritative writes go through the cooperating adapters.
Reassess if either module moves to another datastore or service, if connection
pressure or contention becomes material, if grade writes become long-running,
or if atomic audit and mutation transactions are adopted.

Acceptance requires architecture, database, and security review plus
deterministic real-PostgreSQL close-versus-record and close-versus-revise tests.
The record race must also prove liveness with an application pool configured as
`pool_size=1` and `max_overflow=0`; cancellation or failure must not retain the
dedicated guard connection or its advisory lock.
