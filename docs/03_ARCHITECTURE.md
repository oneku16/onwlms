# OwnSIS Architecture

## Purpose

This document defines the structural architecture of OwnSIS and the constraints that preserve it as the platform evolves. It establishes the system boundary, runtime shape, dependency direction, consistency model, tenancy model, and deployment principles. This document governs OwnSIS system-level boundaries. Accepted Architecture Decision Records govern accepted architectural decisions; detailed choices and implementation guidance must remain compatible with both.

## Scope

This document covers the OwnSIS web application, backend application, background processing, persistence, internal events, and integration boundaries. It also describes the architectural relationship with OwnID, Moodle, and Model Context Protocol (MCP) capabilities.

It does not define HTTP endpoints, database tables, payload schemas, user journeys, or detailed business rules. Domain language and module boundaries are developed in `04_DOMAIN_MODEL.md` and `05_MODULES.md`; integration and security constraints are expanded in their dedicated documents.

Detailed Python backend implementation and engineering conventions are governed by [`13_BACKEND_ENGINEERING_GUIDE.md`](13_BACKEND_ENGINEERING_GUIDE.md); that guide implements rather than redefines these system-level boundaries.

## Responsibilities

The architecture is responsible for:

- preserving strict isolation between organizations across every storage and execution path;
- keeping academic and administrative authority inside OwnSIS;
- ensuring that OwnID remains the sole identity provider and Moodle remains limited to learning delivery;
- making domain boundaries explicit and mechanically enforceable;
- supporting reliable event-driven collaboration without obscuring ownership or consistency;
- providing a deployment model that is operable today and separable later;
- enabling incremental change over a horizon of at least fifteen years;
- favoring readability, diagnosability, and controlled change over local brevity.

Architecture owners maintain these constraints, review exceptions, and record consequential decisions in ADRs. Module owners are responsible for conformance within their boundaries.

## Architectural Drivers

OwnSIS serves schools, colleges, and universities in a multi-tenant environment. The principal quality attributes are tenant isolation, correctness, security, maintainability, auditability, availability, performance under uneven tenant load, and evolvability.

The design assumes that institutional policies and regulatory expectations will vary by organization and jurisdiction. Stable domain concepts must therefore be separated from configurable policy. The platform must accommodate growth without forcing premature distribution or centralizing all behavior into a single undifferentiated application.

## Architecture Style

OwnSIS is a domain-driven modular monolith with event-driven collaboration.

The backend is one versioned application and release boundary composed of independently governed domain and platform modules. A module owns its model, application behavior, persistence access, and published contracts. Modularity is a source-code and runtime rule, not a naming convention. The application may run multiple process roles, such as request handling and background event processing, from the same versioned product without turning those roles into independently versioned or owned systems.

This style is chosen to retain simple transactions, coherent refactoring, consistent operations, and fast cross-domain learning while the product and its domain language mature. It also creates extraction seams. A module may become an independently deployed service only when operational or organizational evidence justifies the additional distributed-systems cost. [ADR-0001](../adr/ADR-0001-modular-monolith.md) records the decision in detail.

Event-driven architecture complements, rather than replaces, direct application collaboration. Events communicate facts that have already occurred and support decoupled reactions. They must not be used to hide circular dependencies, bypass authorization, or simulate synchronous calls through a broker.

## Technology Baseline

The backend runtime is Python 3.14 with FastAPI at the transport boundary. PostgreSQL is the authoritative transactional database, and Alembic owns its migration history. Python dependency management and reproducible environments use `uv`.

The browser application uses Next.js and TypeScript. Docker provides the standard packaging boundary for deployable application roles. DDD, modular-monolith boundaries, and event-driven collaboration govern how these technologies are used; frameworks and infrastructure do not define the domain model.

Technology versions will be upgraded through supported release lines over the platform lifetime. A replacement that changes architectural boundaries, data authority, deployment topology, or compatibility commitments requires an ADR.

## System Context and Authority

OwnSIS is authoritative for all academic and administrative data. It owns the official state and the policies that make that state valid.

- **OwnID** is the only identity provider. It owns human authentication, human credentials, identity-provider sessions, and identity assurance. OwnSIS consumes verified identity assertions and owns organization membership, permissions, and authorization decisions. OwnSIS does not provide a parallel password store or fallback identity provider. Non-human workload authentication follows the separate, governed security model and cannot serve as a user identity path.
- **Moodle** is the learning platform. It owns learning content, learning activities, and learning-delivery state native to Moodle. It is not the source of truth for official enrollment, institutional structure, or academic records. Data crossing this boundary is translated through an anti-corruption layer.
- **MCP** is the governed protocol boundary for AI-assisted capabilities. It neither owns domain data nor receives implicit authority. MCP tools operate through the same application policies, tenant controls, audit requirements, and approval rules as other actors.
- **External integrations** exchange explicitly owned data through versioned contracts. An integration cannot become an informal shared database or a second source of truth.

## Logical Architecture

### Web application

The Next.js and TypeScript application is the browser-facing experience. It is responsible for presentation, interaction, accessibility, safe session participation, and composition of backend capabilities. It must not reimplement authoritative domain rules. Client-side checks improve usability but never substitute for server-side authorization or validation.

### Application boundary

FastAPI exposes the backend application boundary. Transport handling authenticates the caller, resolves tenant context, validates input shape, invokes an application use case, and translates the result. Transport concerns must remain outside domain models. No route handler may reach directly into another module's persistence.

### Domain modules

Each domain module contains its own ubiquitous language, invariants, use cases, and persistence abstractions. Internally, dependency direction runs from adapters toward application behavior and domain policy. The domain does not depend on FastAPI, PostgreSQL, an event broker, or the web application.

Modules collaborate through deliberate application contracts or published events. A module may depend only on another module's public surface. Imports into internal model or persistence packages, cross-module table access, and shared mutable domain objects are prohibited.

### Persistence

PostgreSQL is the system of record for OwnSIS data. A shared database does not imply shared ownership: every persisted object has one owning module, and only that module may write or interpret it. Cross-module reporting uses authorized read models or published data products rather than ad hoc joins that encode another module's private model.

Transactions are local to a module and a single application operation whenever possible. Invariants requiring immediate consistency belong inside the same boundary. Cross-module workflows use explicit orchestration or events and make intermediate states visible. Distributed transactions are not an architectural dependency.

Alembic manages all database evolution. Migrations are versioned, reviewable, forward-operable, and compatible with the deployment strategy. Data ownership changes require an ADR and a staged transition; they are not performed as incidental refactoring.

### Event processing

OwnSIS distinguishes three forms of event:

- **Domain events** express meaningful facts inside a bounded context and participate in its model. They are internal and in-process by default; they are not inherently durable, versioned, or externally consumable.
- **Application events** are explicit module-to-module messages within OwnSIS. They are documented, versioned collaboration contracts with compatibility rules; they may be delivered in process, and when delivery must survive process failure they use durable publication.
- **Integration events** are durable, stable, versioned statements intended for consumers across an external-system boundary.

A domain event is translated deliberately into an application event when its meaning must cross an OwnSIS module boundary and into an integration event when it must cross an external-system boundary. Durable publication that must be atomic with a state change uses an outbox or an equivalent proven mechanism. Consumers are idempotent, preserve tenant and correlation context, tolerate duplicate delivery, and define bounded retry and quarantine behavior. Event ordering is assumed only where the published contract explicitly guarantees it. Event history is not automatically the source of truth; event sourcing requires its own ADR.

### Background work

Long-running, scheduled, and retryable work executes outside request latency while using the same application use cases and authorization boundaries. Work items carry immutable tenant and correlation context. Workers do not acquire broader database access merely because they are asynchronous.

## Multi-Tenant Architecture

An organization is the institutional entity and tenant isolation boundary; each organization is one tenant. Tenant context is established at a trusted boundary using verified identity and organization routing information. A tenant identifier supplied by an untrusted client is never sufficient on its own.

Tenant context must be explicit in application operations, persistence access, events, cache keys, object storage paths, background work, audit records, metrics, and integration configuration. Missing or conflicting context fails closed. Platform-global data is exceptional, narrowly defined, and accessed through separate administrative capabilities.

Isolation uses defense in depth:

- application authorization binds the actor, tenant, action, and resource;
- repository access is tenant-scoped by construction;
- PostgreSQL-enforced controls, normally row-level security or an equivalently strong mechanism, backstop application filtering;
- tenant-aware tests attempt both accidental and malicious cross-tenant access;
- operational tools and support workflows use explicit, audited privilege elevation.

The initial deployment may share application and database infrastructure among tenants. The logical model must not depend on that topology. A tenant or tenant group can later be placed in a dedicated database or deployment cell without changing domain semantics.

## Dependency and Boundary Rules

Dependencies must form an acyclic graph. Domain modules may use a deliberately small shared kernel containing only stable, semantics-preserving primitives. The shared kernel must not become a home for convenience helpers, generic entities, or cross-module business rules.

Direct collaboration is appropriate when a caller needs an immediate answer and the provider owns that answer. An event is appropriate when the publisher announces a completed fact and does not control downstream reactions. Workflow orchestration is appropriate when a business outcome spans modules and its progress, compensation, or deadlines must be visible.

Framework abstractions remain at the edges. Domain behavior must be testable without network, database, container, or framework startup. Generated clients and integration-specific models stay within their adapters.

## Deployment and Operations

All deployable roles are built as Docker images from reproducible sources. Python dependencies and environments are managed with `uv`; frontend dependencies are locked and reproducible. Images are immutable, run with least privilege, and expose configuration through validated runtime settings. Secrets are supplied by the deployment environment and never embedded in images or repository history.

The web application, backend request processes, background processes, and PostgreSQL may scale independently where their runtime roles require it, while remaining one product release. A release identifies compatible application, frontend, and migration versions.

Deployments favor backward-compatible expansion and contraction. A running mixed-version window must not corrupt state or make events uninterpretable. Health checks distinguish process liveness from readiness to serve valid work.

## Observability and Operability

Logs, metrics, traces, and audit records use consistent correlation identifiers and tenant-safe metadata. Sensitive values and educational records are excluded from diagnostic output unless an approved, protected workflow requires them. Operators must be able to determine which module, tenant context, release, and integration caused a failure without reading private payloads.

Each module defines service-level indicators for its critical paths. Queues, outbox publication, retries, quarantined work, migration state, authorization denials, and tenant-isolation signals are observable. Runbooks describe recovery and replay without bypassing domain rules.

## Architecture Governance

Changes that alter system authority, module ownership, tenancy, data placement, consistency, externally consumed contracts, security boundaries, or deployment topology require an ADR. Architecture fitness checks should enforce import boundaries, migration ownership, tenant-scoped persistence, and forbidden dependency directions in continuous integration.

Technical debt is recorded in concrete engineering work, not normalized through undocumented exceptions. A temporary exception has an owner, a bounded impact, an expiry condition, and review evidence.

## Assumptions

- OwnID remains available as the sole identity provider and can provide verifiable identity assertions suitable for OwnSIS authorization.
- Moodle remains an external learning platform and does not become the authoritative store for OwnSIS academic or administrative state.
- PostgreSQL remains the authoritative transactional database for the foreseeable platform horizon.
- Organizations require logical isolation by default; regulatory or scale needs may later require physical isolation for selected tenants.
- Delivery is performed by teams able to own bounded capabilities and maintain published contracts.
- Durable application-event and integration-event delivery uses at-least-once semantics unless a specific contract proves stronger end-to-end semantics; their consumers therefore cannot depend on exactly-once delivery.
- Institutional variation is expressed through explicit policy and configuration, not tenant-specific forks of the product.
- The platform can accept incremental internal evolution while preserving externally committed behavior and data integrity.

## Future Evolution

The modular monolith is the durable default, not a temporary phase. Evolution should first improve boundaries, internal contracts, read models, and operational isolation within that form.

When evidence shows that a module needs independent scaling, release cadence, fault isolation, regulatory placement, or team autonomy, it can be extracted behind its existing contract. Extraction requires demonstrated boundary stability, owned data, mature observability, idempotent integration behavior, and an ADR comparing the operational cost with the measured benefit.

Tenant placement may evolve from shared infrastructure to cells, dedicated databases, or dedicated deployments. Event transport may evolve from in-process durable dispatch to external infrastructure. Read workloads may gain specialized projections or search stores. None of these changes may weaken tenant isolation, alter source-of-truth ownership, or expose internal persistence as a public contract.

The architecture will be reviewed periodically against production evidence, security findings, changes in educational regulation, and the supported Python, FastAPI, PostgreSQL, Next.js, TypeScript, Docker, `uv`, and Alembic ecosystems. Evolution is recorded as deliberate decisions rather than silent drift.
