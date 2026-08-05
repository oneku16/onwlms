# ADR-0007: Use Resumable Module-Owned Admissions Enrollment

- **Status:** Proposed
- **Decision date:** 2026-08-05
- **Decision owners:** OwnSIS admissions, people, academics, and architecture maintainers

## Purpose

Define how an accepted admissions applicant becomes a People student profile and
an official Academic enrollment without conflating bounded-context identifiers
or requiring a distributed transaction.

## Context and Decision Drivers

Admissions owns applicant identity, acceptance, quota reservation, deposit
evidence, and conversion progress. People owns the institutional person and
student profile. Academics owns program enrollment and interprets the admissions
intake as an academic term. A process crash can occur after either downstream
module commits but before Admissions records completion, so an ordinary sequence
of create calls can duplicate people or enrollments.

All three modules use the same PostgreSQL deployment in the first-release
modular monolith, but shared infrastructure does not grant one module ownership
of another module's tables. The workflow therefore needs stable public commands,
module-owned validation, and visible resumable progress.

## Decision

Admissions creates one durable conversion identifier before downstream work. It
copies only the minimum accepted-applicant data into a versioned application
command and retains distinct identifiers for the People student profile and the
Academic enrollment. The originating, already authorized tenant actor and
correlation context accompany the command; raw documents and deposit-provider
payloads do not.

The composition-level registrar calls public idempotent People and Academics
application capabilities. People creates or resolves the person and Student
profile under the conversion key and atomically publishes the profile activation
fact through the outbox. Academics creates or resolves the enrollment under the
same conversion key, treating `student_id` as the stable People Student-profile
identifier. Academics resolves `academic_year_id` from the intake Term; the first
release does not infer a cohort when the application did not select one.

Each downstream capability returns the same identifiers when replayed and rejects
a conversion key that is already bound to different data. Admissions marks its
conversion, application, and seat reservation complete only after both results
are available. A pending conversion remains retryable after partial progress.
External payment processing is outside this workflow; a configured deposit port
must first attest that any required deposit is satisfied or waived.

## Consequences and Risks

The workflow tolerates process failure and duplicate requests without collapsing
module ownership or introducing a broker. Partial progress is explicit and can
be resumed through the normal authorized use case. Student activation still
drives provisioning through the durable outbox.

Cross-module completion is not instantaneous: a pending conversion may have a
People profile before its Academic enrollment. User interfaces and operations
must show pending status and retry through the application capability rather
than editing tables. Retention or correction of copied applicant contact data
must respect both modules' distinct record responsibilities.

## Alternatives Considered

- **Reuse the Admissions applicant-profile UUID as the People student ID:**
  rejected because identical values would obscure separate concepts and owners.
- **Write People and Academics tables from Admissions in one transaction:**
  rejected because it bypasses module contracts and invariants.
- **Fire an event and immediately mark enrollment complete:** rejected because
  asynchronous failure would make the official application state untrue.
- **Introduce a workflow engine or distributed transaction coordinator:**
  deferred because this explicit two-step workflow does not justify either
  platform dependency.

## Assumptions and Reassessment

The first-release intake is an existing tenant Academic Term and therefore has
one authoritative Academic Year. Cohort assignment remains an explicit later
operation unless requirements add it to Admissions. Reassess if conversion gains
many independently governed steps, long-running human tasks, compensation, or
cross-deployment participants. Acceptance requires domain, architecture,
security, and operations review plus duplicate, crash-resume, cross-tenant,
deposit, and outbox evidence.
