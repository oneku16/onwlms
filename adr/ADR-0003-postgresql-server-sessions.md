# ADR-0003: Store Encrypted Browser Sessions in PostgreSQL

- **Status:** Proposed
- **Decision date:** 2026-08-05
- **Decision owners:** OwnSIS identity, security, and platform maintainers

## Purpose

Choose a first-release server-side session store for OwnID Authorization Code
Flow with PKCE without introducing another datastore.

## Context and Decision Drivers

Browser access must use OwnID exclusively, keep access, refresh, and ID tokens
out of browser storage, rotate the application session after authentication,
support revocation and logout, and work across horizontally scaled backend
processes. The platform already depends on PostgreSQL and has no proven need for
Redis.

## Decision

OwnSIS stores pending OIDC flows and authenticated application sessions in
PostgreSQL. A cookie carries only a cryptographically random opaque value; the
database stores its SHA-256 digest. Session identifiers rotate after successful
callback. Pending state, nonce, and PKCE verifier are single-use and expire.

OwnID tokens are encrypted as authenticated ciphertext using a runtime-supplied
key before persistence. The key is mandatory in production and never enters the
database, image, logs, URLs, frontend bundle, or audit metadata. Session cookies
are HttpOnly, Secure in production, SameSite=Lax, and narrowly scoped. A separate
CSRF value uses a cookie/header double-submit check plus the server session and
constant-time comparison for state-changing requests.

Membership and permission changes are re-evaluated from OwnSIS state for
protected capabilities; a stored session does not freeze authorization.
Production startup fails closed without valid OwnID and encryption settings.
Development authentication is an explicit local/test-only adapter and is
rejected in production.

Refresh-token rotation is serialized per application session with a PostgreSQL
row lock. A refresh request reads and validates the session and CSRF binding,
then locks the session row and compares the locked version with the version it
validated before making the bounded OwnID refresh call. Only that lock holder
may present the current refresh token. A successful rotation updates encrypted
tokens and increments the version in the held transaction; provider failure
deletes the session in that transaction. A queued request that observes a newer
version returns a retryable conflict without reusing the old provider token.

Protected-session introspection remains outside a database transaction. If its
result says a token is inactive, deletion is conditional on the version that was
introspected. A concurrent row-locked refresh therefore commits its newer
version before the conditional deletion is re-evaluated, preserving the fresh
session.

## Consequences and Risks

Sessions survive process restarts and work across replicas without sticky
routing. PostgreSQL load and cleanup become operational responsibilities.
Encryption-key rotation requires a staged key-ring or session invalidation
procedure; the first release documents session invalidation as the safe fallback.

A refresh holds one application-pool connection and row lock during a bounded
OwnID HTTP exchange. Concurrent refreshes for the same browser session queue,
but no audit or repository operation opens a nested database session while that
lock is held. Provider timeouts, pool occupancy, row-lock waits, refresh
conflicts, and invalidations require operational visibility. Refresh traffic
must remain within the configured PostgreSQL pool and OwnID timeout budgets.

A compromised application process can use active session material, so least
privilege, short lifetimes, revocation, logging discipline, and incident response
remain necessary. Database encryption does not replace managed storage
encryption.

## Alternatives Considered

- **Browser token storage:** rejected because it increases token-exfiltration
  impact and violates the release security requirements.
- **Signed self-contained application sessions:** rejected because token
  revocation, rotation, and server-side invalidation would be weaker.
- **Redis:** deferred because PostgreSQL already provides the required shared,
  transactional store and current load does not justify another dependency.

## Assumptions and Reassessment

Session traffic fits the managed PostgreSQL workload. Reassess when measured
latency, contention, or independent availability objectives justify a dedicated
session store. Acceptance requires identity and security review, callback replay
tests, CSRF tests, token-leak tests, provider refresh-reuse tests, stale
introspection races, and real PostgreSQL row-lock verification.
