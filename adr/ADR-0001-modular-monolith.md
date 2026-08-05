# ADR-0001: Adopt a Modular Monolith Instead of Microservices

- **Status:** Accepted
- **Decision date:** 2026-08-05
- **Decision owners:** OwnSIS architecture maintainers

## Purpose

This record establishes the initial structural architecture for the OwnSIS core and explains why a modular monolith is preferred to a microservices architecture for the platform's current and foreseeable needs.

## Scope

The decision governs the core OwnSIS backend, its domain boundaries, internal collaboration, transactional model, and deployment topology. It does not collapse the separately owned responsibilities of OwnID or Moodle into OwnSIS, and it does not prescribe business modules, public APIs, database schemas, user-interface structure, or vendor-specific infrastructure.

## Context

OwnSIS is a greenfield, multi-tenant Education ERP expected to evolve for at least fifteen years. Its academic and administrative capabilities will contain related workflows, shared institutional language, strong consistency requirements, and security-sensitive tenant boundaries. The domain model is not yet sufficiently mature to justify irreversible physical distribution along service boundaries.

Microservices would require the project to define network contracts, distributed ownership, independent release behavior, observability, deployment automation, failure recovery, and cross-service data consistency before those boundaries are validated by operating experience. That cost would be immediate, while the expected benefits of independent scaling and autonomous service ownership are not yet demonstrated.

A traditional unstructured monolith would avoid distributed-systems cost but would not provide the explicit ownership and dependency controls required for long-term evolution. The architecture therefore needs monolithic operational simplicity with deliberate internal separation.

## Decision Drivers

- preserve clear domain ownership using Domain-Driven Design;
- maintain strong tenant isolation and consistent authorization enforcement;
- support atomic operations where domain consistency requires them;
- keep local development, testing, deployment, and incident diagnosis comprehensible;
- minimize irreversible infrastructure and organizational commitments before domain boundaries mature;
- enable incremental evolution over a fifteen-year horizon;
- prevent an undifferentiated codebase through enforceable module boundaries;
- retain event-driven collaboration without requiring every interaction to cross a network.

## Decision

OwnSIS will implement its core backend as a **modular monolith**: one versioned application and release boundary composed of explicit, domain-aligned modules with controlled public contracts and enforced dependency direction.

The application may use synchronous application contracts and domain, application, or integration events according to the consistency and coupling needs of each interaction. Event-driven architecture is an internal decoupling and evolution mechanism, not a justification for premature network distribution.

Modules own their domain model, application behavior, and persistence representation. A module may not access another module's internal types, tables, or implementation details. Cross-module collaboration must pass through explicit contracts owned by the appropriate boundary. Shared PostgreSQL infrastructure does not imply shared ownership of all data.

The core is deployed and operated as one versioned release and ownership boundary. The same release may run multiple process roles, such as request handling and background processing, and those roles may scale independently; they do not become independently versioned or owned services. Independently released components may be introduced only through a later accepted ADR supported by concrete scaling, reliability, security, regulatory, release-independence, or team-ownership evidence.

## Responsibilities

- Architecture maintainers define and enforce module dependency rules and approve exceptions through governance.
- Module owners maintain their public contracts, invariants, persistence ownership, events, and compatibility obligations.
- Application authors choose synchronous or event-driven collaboration based on explicit consistency and failure requirements.
- Platform maintainers provide one repeatable build, migration, deployment, observability, and rollback path for the core application.
- Security reviewers verify that internal modularity does not weaken tenant isolation, authorization, auditing, or data ownership.
- Contributors must not create de facto services, shared-model coupling, or cross-module persistence access without an accepted architectural change.

## Consequences

### Positive

- Cross-capability transactions can remain local where the domain requires atomic consistency.
- Developers can navigate, run, test, and diagnose the core without reproducing a distributed environment.
- Domain boundaries can be refined through evidence while refactoring remains comparatively inexpensive.
- Security, tenant context, migrations, and operational controls can be applied consistently.
- A single release unit reduces initial deployment, version compatibility, tracing, and incident-response complexity.
- Explicit contracts and events still create seams that can support future extraction.

### Negative

- The complete core application is released as one unit even when a change affects only one module.
- A defect or resource exhaustion in one module can affect the shared process.
- Independent scaling of a single module is limited until the relevant boundary is extracted or isolated by another approved mechanism.
- Module discipline must be enforced through review and automated dependency checks; directory structure alone cannot prevent coupling.
- Shared infrastructure can tempt contributors to bypass public contracts through direct persistence access.

### Risks and Mitigations

- **Risk: boundary erosion.** Maintain explicit module ownership, dependency rules, contract tests, and architecture reviews.
- **Risk: whole-application performance pressure.** Measure resource use by module and optimize proven bottlenecks before changing topology.
- **Risk: oversized releases.** Keep changes small, use reliable automated verification, and maintain reversible deployment and migration practices.
- **Risk: events that assume in-process delivery forever.** Specify event semantics, idempotency, ownership, and failure behavior so important boundaries can evolve safely.
- **Risk: shared database coupling.** Enforce logical data ownership and prohibit cross-module access to persistence internals.

## Alternatives Considered

### Microservices from the Start

Not selected. It introduces distributed transactions, network failure modes, contract versioning, multi-service observability, deployment coordination, and substantially greater operational cost before independent scaling or release requirements are proven. It would also force early physical boundaries while the OwnSIS domain is still being discovered.

### Traditional Layered Monolith Without Domain Modules

Not selected. Although operationally simple, a system organized primarily by technical layers tends to centralize models and services, obscure ownership, and allow unrelated capabilities to couple through shared persistence. That structure conflicts with the required DDD boundaries and long-term maintainability goals.

### Independently Deployable Services Sharing One Database

Not selected. This combines distributed deployment and failure complexity with database-level coupling, leaving service ownership ambiguous and making independent evolution unsafe.

### Hybrid Service Topology at Inception

Not selected for the OwnSIS core because there is no evidence yet for a specific extraction boundary. OwnID and Moodle remain separate systems because their ownership is already explicit; that fact does not establish a general microservice pattern inside OwnSIS.

## Assumptions

- OwnSIS begins without validated needs for independent module scaling or autonomous release cadence.
- Strong consistency will be valuable for some academic and administrative operations.
- The organization will invest in module-boundary enforcement, automated tests, and architecture review.
- PostgreSQL can support the initial transactional and scale requirements of the core platform.
- OwnID and Moodle remain externally owned systems with explicit integration boundaries.
- A future service extraction is acceptable when evidence outweighs the cost of distribution.

## Future Evolution

This decision must be revisited when measured conditions demonstrate that a module requires independent scaling, availability isolation, regulatory separation, release autonomy, or distinct team ownership that cannot be achieved responsibly inside the modular monolith. A proposed extraction must show a stable domain boundary, explicit data ownership, network contract and compatibility policy, consistency model, failure and retry behavior, observability, migration path, and operational ownership.

Any such change requires a new ADR that supersedes or narrows this record. Until then, distribution is not an optimization target; improving internal modularity, contract quality, tenant safety, and operational evidence is the approved evolution path.
