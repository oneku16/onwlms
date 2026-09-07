# ADR-0008: Serialize Scheduling Resources with PostgreSQL Advisory Locks

- **Status:** Proposed
- **Decision date:** 2026-08-07
- **Decision owners:** OwnSIS scheduling, database, and architecture maintainers

## Purpose

Define how OwnSIS prevents concurrent timetable writes from committing
overlapping room, teacher, or protected-group bookings while keeping conflict
evaluation and persistence in one PostgreSQL transaction.

## Context and Decision Drivers

Scheduling conflict rules depend on several many-to-many resources and time
windows. A read-then-write service flow is unsafe because two requests can both
observe an available resource and commit conflicting sessions. Row locks alone
cannot lock a booking row that does not yet exist, and a process-local lock would
not coordinate multiple backend processes.

The first release is a PostgreSQL-backed modular monolith. The solution must
preserve tenant isolation, support create and move operations, coordinate normal
writes with full generated-schedule replacement, avoid deadlocks through stable
ordering, and return a bounded retryable conflict instead of waiting indefinitely.

## Decision

The Scheduling PostgreSQL adapter uses transaction-scoped advisory locks. Lock
keys are deterministic signed 64-bit values derived with BLAKE2b from the
organization UUID, a versioned resource-kind label, and the resource UUID when
one exists. Tenant identity is therefore part of every lock namespace.

A normal session create or move acquires:

1. a shared tenant-schedule lock;
2. exclusive locks for its room, every teacher, and every protected group;
3. resource locks in sorted numeric-key order.

After the locks are held, the repository reloads current tenant sessions,
evaluates hard conflicts, applies optimistic-version checks, and persists the
session in the same transaction. It uses PostgreSQL try-lock operations and
returns a scheduling conflict instructing the caller to retry when another
transaction already owns a required lock.

Generated full-schedule replacement acquires the tenant-schedule lock
exclusively before reloading the complete persisted tenant schedule. Within that
same transaction it requires the caller's expected-version map to equal the
complete current ID-to-version map. It derives the effective lock set as every
persisted row whose `locked` flag is true plus the caller-supplied lock IDs. The
caller IDs are additive preservation assertions, not the source of truth for
which persisted rows are locked. Every effective locked row must still exist in
the proposal and be byte-for-byte equal at the domain-value level, including its
membership, lock flag, and version.

Proposal versions express snapshot expectations but never select persisted
versions. A proposed row whose ID already exists must carry that row's current
version; if it is not effectively locked, the repository persists it at exactly
`current version + 1`. A proposed ID that does not exist must carry version zero
and is persisted at version zero. Missing, extra, stale, negative, or otherwise
inconsistent expectations fail the replacement. The repository returns the
authoritative prepared sessions so API responses expose the versions actually
committed. Only after these checks does it recheck proposal conflicts, replace
parent and membership rows, and commit. This excludes concurrent normal writes
without requiring the replacement path to enumerate every resource first.

Advisory locks are an infrastructure concurrency backstop, not an authorization
or validation mechanism. Application services must still resolve every room,
offering, teacher, and group through public tenant-scoped module contracts before
calling the repository. In-memory repositories may use process locks only to
model the repository contract in unit tests; production correctness depends on
the PostgreSQL protocol.

## Consequences and Risks

Conflict checking and persistence are atomic with respect to cooperating
Scheduling booking writers across backend processes. New sessions are protected
even though no row existed to lock, generated replacement is coordinated in both
directions with normal booking writes, and identical resource UUIDs in different
tenants do not contend. Persisted locks cannot be bypassed by omitting client lock
IDs, replacement versions are monotonic for retained mutable rows, and owned
teacher/group membership is replaced with the same atomic schedule transaction.

Every future Scheduling writer must participate in the same lock-key derivation
and ordering protocol. A non-participating SQL writer can bypass the guarantee,
so direct table writes remain forbidden. Try-lock contention produces a safe
retry rather than blocking, which may require caller backoff under sustained
load. Hash collisions are extremely unlikely but conservatively serialize
unrelated resources; they cannot permit an overlap. Changing resource-kind
labels or key derivation requires a coordinated transition because mixed
application versions would otherwise use different locks.

The protocol adds no schema migration. PostgreSQL advisory-lock availability,
contention, retry rates, and long transactions should be observable before a
production-readiness claim.

This protocol's current guarantee is deliberately limited to concurrent booking
overlap, generated-replacement coordination, and the reference-integrity checks
performed by the application contracts and database. Mutable teacher
availability and academic-calendar constraint snapshots are loaded before the
booking transaction, and writers that own those snapshots are not serialized by
these scheduling advisory locks. A concurrent availability or calendar change
can therefore make the validated snapshot stale. That gap is a documented
first-release risk, not covered by this decision's atomicity claim, and requires
a future version/lock protocol shared with the owning writers before continuous
constraint validity can be claimed.

## Alternatives Considered

- **Process-local locks:** rejected because they do not coordinate replicas or
  independent worker processes.
- **Row-level locks only:** rejected because a conflicting booking row may not
  exist yet and resource membership spans several tables.
- **Serializable isolation for every scheduling transaction:** not selected
  because it broadens retry behavior and database cost beyond the explicitly
  protected resources.
- **Exclusion constraints:** deferred because the current recurrence and
  many-resource representation does not map to one stable range constraint
  without a material schema redesign.
- **One exclusive tenant lock for every write:** rejected for normal writes
  because it would serialize unrelated resources; retained only for atomic full
  replacement.

## Assumptions and Reassessment

All authoritative scheduling mutations use the Scheduling repository and one
PostgreSQL database. Reassess if sessions move to another datastore, recurrence
is materialized differently, a single tenant's contention becomes excessive, or
the system introduces non-cooperating writers. Acceptance requires architecture
and database review plus real concurrent PostgreSQL tests for room, teacher,
protected-group, tenant separation, nonempty replacement in both contention
directions, persisted-lock preservation, version monotonicity, and member-row
replacement. Availability/calendar snapshot serialization remains a separate
release-risk decision and future protocol.
