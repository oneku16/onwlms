# Architecture Decision Records

## Purpose

This directory records significant OwnSIS architecture decisions and the reasoning that made them appropriate at the time. ADRs preserve context for future maintainers, reduce repeated debate, and make deliberate evolution possible without relying on institutional memory.

## Scope

An ADR is required for a decision that materially affects system structure, module boundaries, data ownership, security posture, tenant isolation, integration style, deployment topology, platform dependencies, or long-term operability. Routine implementation details and easily reversible local choices do not require ADRs unless they establish a repository-wide precedent.

ADRs document engineering decisions. They do not substitute for product requirements, detailed design, security review, implementation plans, or operational procedures.

An ADR cannot silently override an approved product requirement, platform requirement, domain-authority rule, or legal obligation. If an architectural proposal requires one of those obligations to change, the responsible governance process must approve and update that source before or together with acceptance of the ADR.

## Responsibilities

- **Authors** describe the problem, constraints, options, decision, consequences, assumptions, and evolution path in neutral technical language.
- **Architecture maintainers** confirm that the decision is coherent with existing requirements and ADRs and assign its status.
- **Implementers** follow accepted ADRs and reference them when a change depends on their constraints.
- **Reviewers** challenge assumptions, alternatives, boundary effects, tenant safety, operational cost, and reversibility.
- **Future maintainers** supersede decisions with a new ADR rather than rewriting history.

## Record Format

Each ADR has a stable number and descriptive lowercase filename using the form `ADR-NNNN-short-title.md`. A record includes:

- title, status, and decision date;
- purpose and scope;
- context and decision drivers;
- the decision and resulting responsibilities;
- consequences and risks;
- alternatives considered;
- assumptions;
- future evolution or criteria for reassessment.

Accepted records are historical artifacts. Corrections that do not change meaning may be made transparently; a changed decision requires a new ADR that identifies the record it supersedes.

## Status Model

- **Proposed**: under review and not authoritative.
- **Accepted**: approved and currently authoritative.
- **Rejected**: evaluated and not selected.
- **Superseded**: replaced by a newer ADR, which must be linked.
- **Deprecated**: retained for history but no longer recommended for new work.

Among ADR statuses, only Accepted records are authoritative and constrain implementation. A Proposed record cannot be used to bypass review.

## Decision Process

1. Establish the concrete problem and evidence that a durable decision is necessary.
2. Identify affected requirements, domains, modules, security properties, tenant boundaries, and operational responsibilities.
3. Compare viable alternatives using consistent decision drivers.
4. State the decision in enforceable terms, including what is outside its scope.
5. Document positive and negative consequences, risks, and mitigation responsibilities.
6. Obtain review from maintainers accountable for the affected areas.
7. Set the status and update this index.
8. Keep implementation and governing documentation aligned with the accepted decision.

## Index

| ADR | Status | Decision |
| --- | --- | --- |
| [ADR-0001](ADR-0001-modular-monolith.md) | Accepted | Adopt a modular monolith for the OwnSIS core instead of microservices |
| [ADR-0002](ADR-0002-postgresql-tenant-enforcement.md) | Proposed | Backstop explicit tenant context with PostgreSQL row-level security |
| [ADR-0003](ADR-0003-postgresql-server-sessions.md) | Proposed | Store encrypted browser-session material in PostgreSQL |
| [ADR-0004](ADR-0004-transactional-outbox-worker.md) | Proposed | Run reliable background work from a PostgreSQL transactional outbox |
| [ADR-0005](ADR-0005-openapi-frontend-contracts.md) | Proposed | Generate frontend API types from versioned OpenAPI |
| [ADR-0006](ADR-0006-deterministic-scheduling-heuristic.md) | Proposed | Use a deterministic, explainable first scheduling heuristic |
| [ADR-0007](ADR-0007-resumable-admissions-enrollment.md) | Proposed | Convert accepted applicants through resumable module-owned registrations |
| [ADR-0008](ADR-0008-postgresql-scheduling-advisory-locks.md) | Proposed | Serialize concurrent scheduling resources with transaction-scoped PostgreSQL advisory locks |
| [ADR-0009](ADR-0009-postgresql-term-grading-serialization.md) | Proposed | Serialize Academic term closure with official grade writes |

## Assumptions

- OwnSIS will evolve over at least fifteen years and will outlast individual contributors and teams.
- Significant decisions need durable context as well as a record of the selected outcome.
- Accepted ADRs are reviewed together with related architecture and security documentation.
- Architecture can evolve, but evolution must be evidence-driven and explicit.

## Future Evolution

The ADR catalog will grow as concrete requirements create durable choices. Index automation, ownership metadata, and decision-quality checks may be added when the volume of records justifies them. The process should remain lightweight enough to encourage timely records while preserving rigorous analysis for decisions with large blast radius.
