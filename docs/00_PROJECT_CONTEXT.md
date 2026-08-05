# OwnSIS Project Context

## Purpose

This document establishes the shared context for OwnSIS. It defines the product boundary, the enduring constraints that shape engineering decisions, and the vocabulary used throughout the repository. It is the starting point for contributors who need to understand what the platform is before interpreting requirements, architecture, domain, or implementation guidance.

## Scope

This context applies to the entire OwnSIS platform, its maintained integrations, and every artifact in this repository. It covers product identity, system boundaries, strategic constraints, stakeholder needs, and the relationship between OwnSIS, OwnID, Moodle, and MCP-enabled AI capabilities.

It does not define education-sector workflows, public or internal APIs, database structures, user-interface behavior, deployment topology, or module implementation. Those details must be introduced through the appropriate requirements, domain, architecture, and decision records when there is sufficient validated context.

## Project Identity

OwnSIS is a modern, multi-tenant Education ERP platform for schools, colleges, and universities. It is intended to support academic administration and institutional operations without coupling the platform to a single type, size, jurisdiction, or operating model of educational organization.

OwnSIS replaces OpenSIS as a product choice, but it has no technical lineage relationship to OpenSIS:

- OwnSIS is a complete rewrite.
- OwnSIS is not a fork of OpenSIS.
- OwnSIS is not a migration layer around OpenSIS.
- OpenSIS source code, architecture, data structures, behavior, and compatibility constraints are not design authorities for OwnSIS.

Existing-system knowledge may inform problem discovery, but only validated OwnSIS requirements and decisions may shape the platform. Compatibility with a prior product is never implicit.

## Why the Project Exists

Education institutions need administrative software that can evolve as policy, organizational structure, teaching models, integration ecosystems, and technology change. A long-lived platform must keep institutional data trustworthy while allowing independent areas of the product to evolve at different rates.

OwnSIS exists to provide that durable administrative system of record. The project emphasizes explicit domain language, strong organizational isolation, replaceable integration boundaries, and understandable code. The expected lifetime is at least fifteen years, so ease of change and operational clarity take precedence over short-term implementation compression.

## System Context and Ownership Boundaries

OwnSIS is responsible for academic and administrative data. It defines the authoritative meaning, lifecycle, integrity rules, and access controls for the information within that boundary.

The surrounding platform has three explicit relationships:

- **OwnID** is the only identity provider. It authenticates people and supplies stable identity assertions. OwnSIS does not become a second credential authority. OwnSIS remains responsible for the organization-specific representation of a user, including membership, status, roles, permissions, and other authorization context owned by the ERP.
- **Moodle** is responsible only for learning delivery. Course delivery, learning activities, and other learning-platform concerns remain within Moodle. OwnSIS does not delegate ownership of academic or administrative records merely because Moodle consumes or contributes information through an integration.
- **MCP** is the integration mechanism for AI capabilities. AI is treated as a governed consumer or operator of platform capabilities, not as an authority that may bypass domain rules, authorization, tenancy boundaries, or audit requirements.

All cross-system interaction must preserve these ownership boundaries. Synchronization does not imply shared authority, and a local copy used for an integration does not silently become a new source of truth.

## Multi-Tenant Context

Each organization is one tenant and retains its own tenancy boundary. Each organization has independently governed:

- branding;
- domain configuration;
- users and organization membership;
- permissions;
- integrations; and
- subscriptions.

Multi-tenancy is a correctness and security property, not only a hosting optimization. Tenant context must remain explicit across requests, background processing, events, administrative operations, integrations, observability, exports, and support tooling. A feature is incomplete if its tenant isolation cannot be demonstrated.

The architecture may support relationships among organizations in the future, but such relationships must not weaken ownership or isolation. Cross-organization behavior requires an explicit model, authorization rule, and audit trail rather than an exception to tenant scoping.

## Engineering Context

The platform is built around the following technology and architectural commitments:

- Python 3.14 and FastAPI for backend application services;
- PostgreSQL for durable relational data;
- Next.js and TypeScript for the web application;
- Domain-Driven Design for modeling and maintaining business meaning;
- a modular monolith as the primary application architecture;
- event-driven collaboration where events improve decoupling and lifecycle clarity;
- Docker for reproducible packaging and execution;
- `uv` for Python project and dependency management; and
- Alembic for controlled database evolution.

These choices form a coherent baseline rather than a mandate to use every mechanism everywhere. In particular, event-driven architecture does not make every interaction asynchronous, and Domain-Driven Design does not require unnecessary abstraction for simple problems.

## Enduring Engineering Principles

1. **Preserve meaning.** Domain concepts and invariants must be explicit in language, code, documentation, and ownership boundaries.
2. **Make tenancy unavoidable.** Tenant isolation must be enforced by design and verified continuously.
3. **Prefer a cohesive system.** New capabilities begin within the modular monolith unless an accepted architecture decision demonstrates that independent deployment is necessary.
4. **Keep module boundaries real.** Modules own their behavior and data access. Collaboration occurs through defined contracts rather than internal reach-through.
5. **Separate authority from integration.** External systems may authenticate, teach, notify, or assist, but ownership of ERP information remains explicit.
6. **Optimize for readers.** Clear names, direct control flow, small comprehensible units, and visible trade-offs are more valuable than minimizing lines of code.
7. **Evolve deliberately.** Material decisions are documented, migrations are controlled, compatibility is intentional, and obsolete paths are retired through an auditable process.
8. **Operate what is built.** Security, observability, recovery, supportability, and data lifecycle concerns are part of feature design.
9. **Automate invariant checks.** Architectural, security, tenancy, quality, and migration rules should be enforced by tests or tooling wherever practical.
10. **Keep humans accountable.** AI assistance may accelerate work but cannot replace review, authorization, or ownership of consequential decisions.

## Stakeholders

The documentation and architecture must serve several groups without allowing one perspective to dominate the platform:

- educational organizations that depend on correct, available, and secure operations;
- people whose personal and academic information is processed by the platform;
- institutional administrators who configure organizations and integrations;
- educators and operational staff who rely on consistent workflows and data;
- developers and maintainers who need clear boundaries and safe change mechanisms;
- operators and security teams responsible for deployment, incident response, and recovery;
- integration owners responsible for OwnID, Moodle, and other approved systems; and
- open-source contributors and adopters who require transparent governance and reproducible engineering practices.

## Repository as the Source of Truth

The repository contains the authoritative engineering record for OwnSIS. Documentation, accepted architecture decision records, versioned contracts, tests, and implementation must agree. External discussions and issue trackers may provide context, but they do not silently override repository decisions.

Engineering conflicts are resolved using this authority order:

1. applicable law and explicit security obligations;
2. approved product and platform requirements and explicit domain-authority definitions;
3. accepted architecture decision records for the specific decisions they govern, provided they remain compatible with the higher-order obligations;
4. architecture, security, module, integration, and engineering standards;
5. implementation-level documentation, executable contracts, tests, and code.

A conflict discovered between these sources is a defect. A lower-order artifact cannot override a higher-order obligation through implementation alone. A decision that intentionally changes a higher-order obligation must update that obligation through its governance process and record the architectural consequences; it must not rely on an ADR or maintainer instruction as a silent override.

## Responsibilities

This document is responsible for:

- defining the stable identity and intent of OwnSIS;
- stating the high-level system and data-ownership boundaries;
- recording the enduring technology and architectural constraints;
- providing common terminology for all other foundation documents;
- distinguishing platform context from implementation detail; and
- giving reviewers a baseline against which proposals can be evaluated.

Every contributor is responsible for preserving this context in proposed changes. Maintainers are responsible for reviewing the document when a strategic assumption, product boundary, or platform-wide constraint changes. More specific documents are responsible for elaborating requirements and decisions without contradicting this context.

## Assumptions

- Each organization is one tenant and owns its configuration, subscription, authorization context, and data isolation.
- A single deployed OwnSIS platform may serve multiple organizations concurrently.
- OwnID remains available as the sole identity provider and exposes identity capabilities suitable for secure integration.
- Moodle remains an independently operated learning platform with an explicit integration boundary.
- OwnSIS remains authoritative for its academic and administrative data even when other systems exchange copies or derived representations.
- Education institutions vary materially, so the core must accommodate controlled configuration and extension without tenant-specific forks.
- The system will be operated in environments with differing regulatory, localization, scale, and integration needs.
- The platform will undergo continuous schema, module, dependency, and infrastructure evolution during its expected lifetime.
- Backward compatibility is a deliberate product and engineering decision, not an automatic obligation to reproduce OpenSIS behavior.
- Human maintainers remain accountable for architecture, security, data governance, and release decisions made with AI assistance.

## Future Evolution

This context is expected to be stable, but it is not immutable. It may evolve when the product boundary, authoritative-system relationships, tenancy model, supported institutional scope, or foundational technology changes.

Changes must include an impact assessment across requirements, architecture, security, domain ownership, integration contracts, operations, and contributor guidance. A change that reverses an accepted architectural position requires a superseding ADR. Historical decisions remain in the ADR record so future maintainers can understand why the platform changed.

Future capabilities should be incorporated by extending explicit boundaries rather than weakening them. New organization relationships, integration types, delivery channels, AI tools, or deployment models must retain tenant isolation, authoritative data ownership, auditable behavior, and module autonomy.

## Terminology

- **Organization**: a school, college, university, or independently governed institutional unit that constitutes one tenant and its isolation boundary.
- **Tenant context**: the verified organization identity under which an operation is authorized and executed.
- **Platform**: the complete OwnSIS product, including maintained applications, runtime components, integrations, and operational mechanisms.
- **Module**: a cohesive business capability with explicit ownership, boundaries, and collaboration contracts inside the modular monolith.
- **Domain event**: an expression that a meaningful domain fact has occurred; it is not an unrestricted data-change notification and does not by itself imply durable cross-boundary delivery.
- **Application event**: an explicitly versioned message used to communicate a fact across an OwnSIS module boundary, with compatibility and durability defined by the collaboration contract.
- **Integration event**: a durable, stable, versioned message intended to cross an external-system boundary.
- **System of record**: the system that owns the authoritative meaning and lifecycle of specified information.
- **Identity**: a human subject asserted by OwnID or an explicitly governed non-human service principal. OwnID is the sole identity provider; service authentication cannot create an alternative human identity path.
- **Organization user**: OwnSIS authorization and membership context associated with an OwnID identity inside an organization.
