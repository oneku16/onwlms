# ADR-0010: Accept Moodle grade evidence only through explicit Grading acceptance

- **Status:** Proposed
- **Decision date:** 2026-09-08

## Purpose and Scope

This record decides how Moodle course results enter OwnSIS and how they may
become official final grades. It covers the tenant-signed grade-event ingress,
operator-initiated selected-term reconciliation, the duplicate-safe evidence
store, and the Grading-owned acceptance and rejection capability. It does not
decide Moodle provisioning, deadline reads, or any other provider exchange.

## Context and Decision Drivers

The first-release journey required that "Moodle evidence is accepted through
official grading policy". The foundation already stored Moodle grade evidence
with a tenant plus external-event unique key, but no authenticated ingress,
reconciliation run, or acceptance path existed, so evidence could never become
an official result. The governing documents require that:

- Moodle owns learning delivery only; OwnSIS owns official outcomes
  (`docs/06_INTEGRATIONS.md`, `OWN-MDL-001`, `OWN-DATA-004`);
- external evidence carries provenance and observation time and becomes
  official only through the owning domain policy (`OWN-DATA-005`);
- incoming integration traffic is authenticated, integrity-checked, and
  replay-protected where the protocol permits (`docs/07_SECURITY.md`);
- duplicate and reordered delivery are normal and must not create broader
  authority (`OWN-EVT-004`, `OWN-INT-005`);
- consequential changes are authorized, audited, and attributable to a human
  actor (`OWN-SEC-006`, `OWN-IAM-009`).

Moodle has no supported native webhook for final grades, so a push-only design
would depend on a site plugin, while a pull-only design would leave operators
without a timely signal. Automatic acceptance was rejected because OwnSIS cannot
infer a grading scale or resolve ambiguous participation from a Moodle value.

## Decision

1. **Evidence, never authority.** Every Moodle result is stored as
   non-authoritative evidence with tenant, external event key, observation time,
   source version, and intake outcome. Intake never writes a final grade; the
   first-release receiver dispositions every event as `review_required`, which
   keeps it `pending` with the reason code `review_required`.
2. **Two authenticated intake paths.** A Moodle-side sender may push events to
   `POST /api/v1/integrations/moodle/grade-events/{organization_id}` signed with
   a tenant-specific shared secret: HMAC-SHA256 over a version prefix, a unix
   timestamp, and the raw body, verified in constant time, with a five-minute
   clock-skew window and a bounded body size. The secret is configured by a
   tenant administrator through `PUT /api/v1/integrations/moodle/grade-event-secret`
   and stored Fernet-encrypted beside the web-service token. Independently, an
   administrator with `integrations.grade_evidence.reconcile` may run
   `POST /api/v1/integrations/moodle/grade-reconciliations` for one term, which
   pulls course totals through the allowlisted `gradereport_user_get_grade_items`
   function for every mapped offering, translates mapped learners into evidence
   with a deterministic external key, and counts unmapped offerings and users
   instead of guessing. Runs are persisted per tenant with their counts and a
   safe error code.
3. **Explicit human acceptance in Grading.** Only an actor holding
   `grading.final_grade.record` may accept pending evidence through
   `POST /api/v1/grading/external-evidence/{evidence_id}/accept`, naming the
   grading scale. Grading resolves the participation through People (person to
   student profile) and Academics (exactly one active participation in the
   offering), parses the value as a raw score, and then applies the ordinary
   recording rules: an initial grade when none exists, otherwise a revision that
   additionally requires `grading.final_grade.revise` and an explanation; closed
   terms require the closed-term permission and an explanation. Rejection through
   `.../reject` records an audited reason. Both outcomes are written back to the
   evidence owner so lineage (evidence to final grade) is retained, and both
   resolve pending evidence exactly once under a row lock.
4. **Separate read permission.** Evidence and run listings require the new
   tenant permission `integrations.grade_evidence.read`; teachers keep only the
   assignment-scoped synchronization status.

## Consequences and Risks

- Step 8 of the critical journey is executable locally with controlled fakes;
  real Moodle verification of the reconciliation function, throttling, and the
  event sender remain credential-gated.
- Grade acceptance and the evidence write-back are two transactions in two
  modules. A crash between them leaves an official grade with evidence still
  pending; a retry then produces a revision rather than a duplicate grade, and
  the audit trail shows both intents. This matches the documented consistency
  gate and is not silently masked.
- The shared secret is a tenant-scoped workload credential, not an identity
  provider. Rotation is an ordinary configuration update; a compromised secret
  can only create pending evidence that a human must still accept.
- Unmapped Moodle users or offerings are counted, never inferred; mapping
  management remains a separate, credential-gated provisioning concern.

## Alternatives Considered

- **Automatic acceptance with a default scale:** rejected because it would let
  an external system define an official record and hide scale ambiguity.
- **Unauthenticated ingress relying on event uniqueness alone:** rejected
  because duplicate suppression does not prevent forged evidence.
- **OwnID-authenticated workload tokens for the sender:** deferred; it needs an
  approved non-human identity policy that the first release does not have.
- **Pull-only reconciliation:** rejected as the sole path because it gives
  operators no timely signal between runs.

## Assumptions

- Moodle exposes `gradereport_user_get_grade_items` to the tenant token.
- The Moodle-side sender can compute an HMAC over the raw body and keep the
  tenant secret confidential.
- Tenant administrators maintain Moodle person and offering mappings.

## Future Evolution

An accepted workload-identity policy may replace the shared secret with OwnID
issued sender credentials. Automatic acceptance for narrowly configured scales
and unambiguous participation could become an explicit, per-tenant policy after
institutional validation, without weakening the audit and lineage requirements.
