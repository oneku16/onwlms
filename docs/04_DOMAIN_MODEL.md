# OwnSIS Domain Model Foundation

## Purpose

This document establishes how OwnSIS models its domain using Domain-Driven Design (DDD). It defines the strategic modeling language, ownership rules, tenant invariants, and collaboration practices used to discover and maintain bounded contexts. It intentionally provides a foundation rather than a completed education-domain model.

## Scope

This document covers strategic and tactical DDD conventions, authoritative domain boundaries, context relationships, model lifecycle, and the distinction between identity, learning, academic, and administrative concerns.

It does not specify aggregates for individual capabilities, database entities, fields, workflows, endpoint contracts, validation formulas, or institution-specific policy. Those details are introduced only when supported by requirements and domain discovery.

## Responsibilities

The domain-modeling approach is responsible for:

- giving each business concept one clear meaning within a bounded context;
- locating invariants and business decisions with the context that owns them;
- separating stable domain policy from transport, persistence, and vendor representations;
- making tenant ownership an explicit invariant rather than an implicit filter;
- preventing OwnID, Moodle, and other integrations from dictating the internal model;
- expressing cross-context facts through deliberate, versioned contracts;
- preserving historical meaning as terminology and policy evolve.

Domain owners maintain their ubiquitous language, model decisions, published events, and compatibility commitments. Engineers, product specialists, security reviewers, and institutional subject-matter experts share responsibility for validating the language.

## Domain Authority

OwnSIS owns the official academic and administrative domain. “Official” means the state on which institutional policy, reporting, authorization, and audit depend. A copy held by another system does not transfer authority.

Authority is divided at external boundaries as follows:

- OwnID owns authentication credentials, identity proofing, identity-provider sessions, and the external subject identity it asserts.
- OwnSIS owns the relationship between a verified subject and an organization, including local access, permissions, and the academic or administrative meaning attached to that relationship.
- Moodle owns learning content, learning activities, and the delivery state of those activities.
- OwnSIS owns official academic structure, participation, outcomes, and administrative records. Learning data received from Moodle is external evidence until OwnSIS applies the relevant domain policy.
- MCP-enabled AI owns no institutional facts and makes no authoritative decision by itself.

This authority map is a model constraint. Any change to it requires an ADR and explicit data-governance review.

## Foundational Language

The following terms have stable architectural meanings. Capability-specific vocabulary is defined by the context that owns it.

- **Organization**: a school, college, university, or independently governed institutional unit whose data and configuration OwnSIS manages. Each organization is one tenant.
- **Tenant**: the isolation and policy boundary through which an organization uses the platform. Relationships among organizations require explicit modeling and do not merge their tenant boundaries.
- **Actor**: an authenticated human or approved system identity attempting an action.
- **Subject identity**: the identity asserted by OwnID. It is a reference to an external identity, not an OwnSIS credential.
- **Membership**: the tenant-bound relationship that permits a subject identity to participate in an organization. It does not by itself grant every action.
- **Permission**: a tenant-scoped authorization capability interpreted by OwnSIS policy.
- **Entitlement**: a tenant-scoped capability made available by subscription or platform policy. Entitlement and permission answer different questions and must not be conflated.
- **Integration**: a governed relationship between an organization and an external system, including its configuration, credentials, state, and contracts.
- **Official record**: OwnSIS-owned state accepted as authoritative by the relevant domain policy.

Terms with different meanings across institutional types must not be forced into a universal entity. A context may translate another context's language at its boundary.

## Strategic Domain Design

### Bounded contexts

A bounded context is the boundary within which a model and its language are consistent. It owns the rules that determine valid state and publishes only the facts or capabilities other contexts genuinely need.

Context boundaries are discovered using:

- distinct language and meanings;
- invariants that must change atomically;
- source-of-truth ownership;
- different rates or reasons for change;
- security, privacy, or retention boundaries;
- team ownership and operational behavior;
- integration pressure and vendor-specific concepts.

A bounded context is not inferred from a user-interface page, database namespace, team name, or list of nouns. A context may contain multiple application workflows, and one workflow may coordinate several contexts without merging their models.

### Context relationships

Every relationship between contexts declares an upstream owner and a downstream consumer. The downstream context translates upstream concepts into its own language where necessary. Shared representations are limited to published contracts and a deliberately small shared kernel.

OwnID, Moodle, MCP providers, and other external systems are separate contexts. Their objects never become OwnSIS domain objects merely because a client library exposes them. Anti-corruption layers protect internal semantics and isolate vendor change.

### Core, supporting, and generic capabilities

Capability classification guides investment without hard-coding the final module map:

- **Core capabilities** contain the institutional rules and trustworthy academic or administrative record that distinguish OwnSIS.
- **Supporting capabilities** enable the core domain but still contain organization-specific policy, such as tenant access, integration governance, and institutional configuration.
- **Generic capabilities** solve broadly understood technical problems and should use proven platform mechanisms where doing so does not surrender domain authority.

Classification is reviewed as product understanding grows. It does not authorize coupling or lower standards for supporting and generic capabilities.

## Tactical Modeling Rules

Tactical patterns are used only when they clarify behavior.

- An **entity** has identity and continuity within its context. Identity is context-specific; a database key is not a domain definition.
- A **value object** describes a value through its attributes and invariants and is immutable from the model's perspective.
- An **aggregate** is a consistency boundary with one entry point for state change. Aggregates remain small enough to protect true invariants without becoming object graphs of an entire institution.
- A **domain service** expresses domain behavior that does not naturally belong to one entity or value object. It is not a container for procedural application logic.
- A **repository** provides aggregate-oriented persistence from the domain's perspective. It does not expose another context's storage or generic query access.
- A **domain event** records a meaningful fact in past tense after the owning context accepts it.
- A **policy** expresses a named decision that may vary by institution, jurisdiction, time, or configuration while preserving common semantics.

Application services coordinate actors, authorization, repositories, transactions, and messages. Domain objects enforce the rules that make a state valid. Adapters translate transport, persistence, and external-system concerns. Framework annotations and vendor models do not belong in the domain layer.

## Tenant Invariants

Tenant ownership is part of domain identity wherever institutional state is involved. It is not inferred later from a request or recovered through an unrestricted query.

The model follows these rules:

- an operation acts in exactly one tenant context unless it is an explicitly governed platform operation;
- references between tenant-owned objects cannot cross tenants;
- a subject identity may participate in more than one organization only through distinct tenant relationships and independent authorization;
- permissions, entitlements, policies, integrations, branding, and domains are evaluated within their tenant;
- events and commands concerning tenant-owned state carry immutable tenant context;
- movement or merging of institutional data is a controlled domain process, never an identifier reassignment;
- platform support access is external to ordinary tenant roles and is separately authorized and audited.

These invariants are enforced by domain policy, application authorization, and persistence controls. Any model that requires tenant-free access to institutional records is considered unsafe until proven otherwise.

## Identity and Access Semantics

Authentication and authorization are separate models. OwnID answers who authenticated and with what assurance. OwnSIS answers whether that actor, in a specific tenant relationship and current policy context, may perform an action.

The OwnID subject identifier is an external reference. It must not be treated as a tenant membership, permission, person record, or academic role. Likewise, OwnSIS does not replicate OwnID credentials or introduce a local authentication fallback.

Permissions express authority; subscriptions and entitlements express availability. Branding and domain resolution select tenant experience but do not by themselves prove authorization. This separation prevents routing, commercial configuration, and security policy from collapsing into one model.

## Time, History, and Policy

Academic and administrative meaning is often time-dependent. Domain decisions therefore use an explicit effective time or business period when the capability requires it, rather than relying implicitly on the server clock. Historical records retain the policy and terminology needed to interpret them.

Corrections, reversals, and supersession should be modeled as meaningful operations when auditability matters. Destructive rewriting of accepted history is not a default modeling technique. The exact lifecycle belongs to each bounded context and is defined only with validated requirements.

## Events and Cross-Context Consistency

A domain event states a fact meaningful inside its bounded context. It is an internal, in-process modeling construct by default and is not inherently durable, versioned, or available to another context. When a fact must cross an OwnSIS module boundary, the owning application deliberately translates it into a documented, versioned application event. When it must cross an external-system boundary, the application publishes a durable, versioned integration event. The published form contains only the stable meaning consumers require, not a serialization of the publisher's internal entity.

Immediate consistency belongs within one aggregate or bounded context. A process spanning contexts acknowledges latency and partial progress. It uses an explicit application workflow, durable events, or both. Consumers are idempotent and decide how an upstream fact affects their own model.

Published event contracts evolve compatibly. A semantic change produces a new contract version or a new event meaning rather than silently redefining history. Sensitive data is minimized; an event is not a convenient broadcast of a complete record. Consumers cannot mutate the publisher's state by editing a message or reaching into its persistence.

## Persistence Independence

The domain model is not a mirror of PostgreSQL and does not expose Alembic migrations as business design. Persistence models may differ from domain objects when required for integrity, performance, or compatibility. Mapping remains inside the owning module.

Identifiers are stable and opaque outside their owning context. Foreign-key convenience does not grant another context write ownership. Read models may combine published information for reporting, but they do not become authoritative domain models and cannot be used to bypass source policies.

## Domain Discovery and Governance

Before introducing or materially changing a model, the owning team documents:

- the language used by domain experts and the meanings that conflict;
- the authority and tenant boundary;
- the decisions and invariants the model must protect;
- lifecycle events and temporal meaning;
- upstream facts consumed and downstream commitments published;
- privacy, audit, retention, and correction expectations;
- failure and concurrency behavior.

Model reviews include product, engineering, security, and relevant institutional expertise. A change that moves authority or combines bounded contexts requires an ADR. Examples in documentation and tests should use realistic language but must not accidentally establish unsupported product policy.

## Assumptions

- Schools, colleges, and universities share some concepts but may assign different meanings and policies to them.
- Organization-specific variation can be represented by explicit configuration and policy within coherent models rather than by tenant-specific source forks.
- OwnID exposes stable subject identity and authentication assurance while OwnSIS remains responsible for tenant authorization.
- Moodle can exchange learning-related facts without owning the official academic record.
- Business experts will participate continuously in refining ubiquitous language and invariants.
- Not all cross-context outcomes require immediate consistency, provided progress and failure are explicit.
- Regulatory obligations differ by jurisdiction and will be attached to the context that owns the affected data.

## Future Evolution

The model will evolve through domain discovery, production evidence, and institutional feedback. New terms are added to a context glossary with their authority and temporal meaning. Renaming a concept requires migration of contracts and documentation, not just a code symbol change.

As boundaries stabilize, context maps can become more detailed and validated capability boundaries can be promoted to owned modules. If an institutional type requires materially different semantics, OwnSIS should introduce an explicit policy, model variant, or bounded context rather than accumulating ambiguous flags in a universal model.

Future physical separation of modules or tenant deployments will not change domain authority. Historical event and record meanings will remain interpretable through versioned contracts and migration policy. AI-assisted capabilities may improve discovery and workflow assistance, but authoritative decisions will continue to pass through named OwnSIS policies with actor, tenant, provenance, and audit context.
