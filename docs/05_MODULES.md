# OwnSIS Module Foundation

## Purpose

This document defines how OwnSIS is divided into modules and how those modules collaborate inside the modular monolith. It provides a taxonomy, boundary rules, ownership expectations, and the criteria used to turn validated domain discovery into module boundaries.

The capability concerns established by the project context are not implemented module specifications. Their language, invariants, ownership, and change patterns must be studied before a boundary is finalized.

## Scope

This document covers backend domain modules, supporting platform modules, integration adapters, reporting projections, and their relationship to the Next.js application. It defines dependency, persistence, event, tenancy, testing, and governance rules.

It does not define package trees, public endpoints, database schemas, entities, screen navigation, business workflows, or detailed feature allocation. It also does not authorize a one-to-one module for each capability concern named below.

## Responsibilities

The module model is responsible for:

- assigning every domain decision and persisted fact to one owner;
- making legal dependencies explicit and acyclic;
- protecting module internals from direct use by other modules;
- aligning transaction boundaries with true invariants;
- preserving tenant context through every collaboration path;
- enabling independent testing, ownership, observability, and eventual extraction;
- preventing framework, reporting, and integration convenience from eroding domain boundaries.

Each module has an accountable owning team or maintainer group. Ownership includes its language, application capabilities, migrations, operational signals, data classification, published contracts, compatibility, and documentation.

## Module Definition

A module is a cohesive, enforceable boundary inside the OwnSIS backend. It contains the behavior and data access for one bounded context or a closely related platform responsibility. A module is not merely a folder and is not automatically a deployable service.

Every module declares:

- its purpose and bounded language;
- the data and decisions it owns;
- its tenant behavior, including any justified platform-global state;
- its public application capabilities;
- the facts it publishes and consumes;
- its allowed dependencies;
- its authorization, privacy, audit, and retention obligations;
- its migration ownership and operational indicators.

The declaration describes contracts and authority, not internal classes or storage layout.

## Module Taxonomy

### Core domain modules

Core domain modules own the academic and administrative rules that make OwnSIS authoritative. They receive the highest modeling attention and avoid vendor-shaped concepts. A core module cannot delegate its source-of-truth decision to Moodle, an integration, or an AI system.

### Supporting domain modules

Supporting modules contain institutional policy needed by core capabilities, such as organization governance, access relationships, entitlements, and integration configuration. They remain domain modules even when their concepts are familiar from other products.

### Platform modules

Platform modules provide reusable technical capabilities such as audit recording, reliable message publication, notifications transport, file handling, and operational policy enforcement. A platform module exposes a narrow capability and does not absorb business rules from its consumers. For example, an audit facility owns the integrity and retention mechanics of audit evidence, while the originating domain module owns which domain action is meaningful and why it must be recorded.

### Integration modules

An integration module is an anti-corruption boundary for one external system or protocol concern. It translates between external contracts and OwnSIS application contracts, manages reliability and credentials, and exposes external failure explicitly. It does not own the academic or administrative facts being exchanged.

### Projection and reporting modules

Projection modules build read-optimized views from owned publications. They may combine information from several modules for authorized queries, analytics, or reporting. They are derived state: they cannot accept authoritative writes or become a shortcut around owning modules.

### User-interface composition

The Next.js application composes capabilities for a coherent user experience. Feature organization in the frontend should reflect backend language where practical, but a page can span several modules. The frontend never becomes the owner of an invariant, and its directory layout does not redefine backend boundaries.

## Boundary Rules

The following rules are mandatory:

1. A persisted fact has exactly one owning module.
2. Only the owning module writes its state or interprets its private persistence representation.
3. Consumers use a public application contract, a published event, or an authorized read model.
4. Imports into another module's internal domain, application implementation, adapter, or persistence code are prohibited.
5. Dependencies form an acyclic graph. A cycle is evidence that a boundary or workflow needs redesign.
6. Shared abstractions are admitted to the shared kernel only when their semantics are stable and identical for all consumers.
7. Cross-module transactions are exceptional. If two rules must always commit together, their ownership boundary must be reconsidered.
8. Events describe completed facts and cannot be used as concealed remote procedure calls.
9. Tenant context, actor context, correlation, and authorization outcome remain intact across direct and asynchronous collaboration.
10. No module exposes its database objects as a public integration contract.

Build-time dependency checks and architecture tests enforce these rules. Review convention alone is insufficient.

## Collaboration Patterns

### Direct application collaboration

A module may call another module's public application capability when it needs an immediate result owned by that module. The provider performs its own policy and tenant checks. The caller does not manipulate provider entities or participate in its private transaction.

### Events

A module may raise in-process domain events as part of its internal model. When another OwnSIS module needs a completed fact, the owner deliberately translates that fact into a versioned application event with an explicit compatibility policy. When an external consumer needs the fact, the owner publishes a durable, versioned integration event. Downstream consumers react independently and idempotently. The publisher does not know the list of consumers and cannot assume their immediate success.

### Orchestrated workflows

A named application workflow coordinates multiple modules when the overall process has visible progress, deadlines, compensating actions, or failure states. The orchestrator owns coordination state, not the internal state of participating modules.

### Read composition

Queries that span modules use application-level composition or purpose-built projections. Read convenience does not justify cross-module writes, unrestricted database joins, or duplicated authority.

## Persistence and Migration Ownership

PostgreSQL may be physically shared, but logical ownership is strict. Every Alembic change has one owning module and a documented compatibility impact. A module may retain derived references to another module's stable public identifier but cannot rely on the other module's private fields or lifecycle.

Moving data ownership between modules is a controlled architectural change. During a transition, one writer remains authoritative, synchronization is observable and reversible, and consumer contracts migrate before legacy access is removed.

## Tenant Behavior

Domain and supporting modules are tenant-scoped by default. Platform-global behavior requires an explicit statement of why it cannot belong to a tenant and how privileged access is controlled.

Module contracts accept trusted tenant context as part of the application invocation. Persistence, events, caches, work queues, projections, and integration configuration preserve that context. Modules fail closed when tenant context is absent or inconsistent. Tests for every tenant-aware module include cross-tenant denial and ambiguous-context cases.

## Capability Discovery Scope

This foundation commits to the organization concerns explicitly established by the project context without assigning them to implemented modules. Before implementation, domain discovery must establish ownership and boundaries for:

- the organization as a tenant and its lifecycle in OwnSIS;
- organization-specific branding and domain configuration;
- organization users, OwnID subject relationships, membership, permissions, and authorization policy;
- organization-specific integration configuration and authority boundaries;
- organization-specific subscription context and entitlements; and
- the academic and administrative information for which OwnSIS is authoritative.

These concerns are not a one-to-one module list. Discovery may group a tightly coherent set or split a concern where language, invariants, privacy, lifecycle, or ownership differ. Permission and subscription entitlement must remain distinct concepts even if their policies collaborate. OwnID remains external to every OwnSIS domain boundary, and Moodle remains responsible only for learning delivery.

The foundation intentionally does not enumerate education workflows or familiar ERP feature areas. Naming those areas here would assign scope and ownership before schools, colleges, and universities have validated the language and boundaries. Future module declarations must be justified by the criteria below and recorded in the module map when approved.

## Boundary Discovery Criteria

A proposed capability boundary is promoted to a module when its team can state:

- a coherent ubiquitous language and source of truth;
- the decisions and invariants it alone owns;
- a tenant and privacy model;
- independent reasons and cadence for change;
- the facts it requires and publishes;
- transaction and consistency expectations;
- an accountable owner and an operable failure boundary.

If two proposed boundaries share invariants that must commit atomically, they may belong in one module. If one proposed boundary contains conflicting language, independent policy, or separate lifecycle, it may need multiple contexts. Team convenience alone does not settle the boundary.

## Review and Conformance

A new or materially changed module is reviewed for authority, dependency direction, tenant isolation, data classification, public contract minimality, event semantics, migration ownership, and observability. Moving a boundary or adding a dependency that changes the context map requires an ADR.

Tests are layered: domain tests verify policy without infrastructure; application tests verify orchestration and authorization; adapter tests verify translation and failure behavior; architecture tests verify forbidden dependencies; integration tests verify persistence and contract compatibility. End-to-end tests validate a small set of cross-module outcomes without becoming the primary proof of domain correctness.

## Assumptions

- A module can be owned and tested independently even while released as part of one application.
- Most authoritative invariants can be located within one bounded context after sufficient domain discovery.
- PostgreSQL is initially shared by multiple modules and tenants, with ownership and isolation enforced logically and at the database boundary.
- Durable application-event and integration-event delivery is assumed to be at least once, so their consumers are idempotent.
- OwnID, Moodle, and MCP remain separate external contexts with their own evolution and failure modes.
- Module boundaries will be refined with schools, colleges, and universities before implementation.
- Repository tooling can enforce dependency and migration ownership rules in continuous integration.

## Future Evolution

The module map will become more precise as domain discovery produces stable language and production behavior reveals load, failure, and ownership patterns. Proposed boundaries will be merged, split, or renamed only with explicit changes to authority and contracts.

Modules that need stronger resource isolation can first receive separate process roles, queues, or database placement while remaining part of the modular monolith. Independent service extraction is considered only for a stable boundary with owned data, mature contracts, independent operational need, and a team prepared to carry the reliability cost.

Reporting projections may move to specialized storage, and selected tenants may move to deployment cells or dedicated databases. These are topology changes, not permission to weaken module ownership. Architecture checks, context maps, and module declarations will evolve with the repository so the implemented dependency graph remains visible and enforceable.
