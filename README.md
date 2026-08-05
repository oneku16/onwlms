# OwnSIS

## Purpose

This README is the entry point to the OwnSIS repository. It establishes the product boundary, the engineering intent, the selected technology stack, and the repository principles that all contributors must understand before proposing implementation work.

## What OwnSIS Is

OwnSIS is a modern, multi-tenant Education ERP platform for schools, colleges, and universities. It is a complete rewrite intended to replace OpenSIS; it is neither a fork of OpenSIS nor a migration of the OpenSIS codebase.

OwnSIS is the system of record for academic and administrative data. Each organization is an isolated tenant with its own branding, domain, users, permissions, integrations, and subscriptions. Tenant isolation is a foundational architectural property rather than an optional feature.

The platform has explicit responsibility boundaries:

- **OwnID** is the only identity provider. OwnSIS consumes identity and authentication outcomes but does not create a competing identity system.
- **Moodle** is responsible only for learning delivery. OwnSIS retains ownership of academic and administrative records.
- **MCP** is the integration approach for AI capabilities. AI features must remain governed, observable, permission-aware, and replaceable.

## Why It Exists

OwnSIS exists to provide a maintainable institutional platform whose architecture can evolve for at least fifteen years. The repository is organized around clear domain ownership, explicit boundaries, traceable decisions, secure tenant isolation, and incremental change. Readability, correctness, and operational clarity take precedence over minimizing the number of files, abstractions, or lines of code.

The rewrite creates a clean engineering foundation without inheriting legacy implementation constraints, database structures, APIs, or architectural coupling from OpenSIS.

## Scope

This repository contains the OwnSIS product source, architecture records, engineering standards, operational assets, and verification suites. At the current foundation stage, the documentation defines how future business capabilities will be discovered and implemented; it does not pre-empt that work by inventing business workflows, APIs, database schemas, or module internals.

The platform scope includes multi-tenant academic and administrative capabilities and the controlled integration boundaries required to work with OwnID, Moodle, AI tooling, and organization-specific services. Identity implementation belongs to OwnID, and learning delivery belongs to Moodle.

## Responsibilities

The repository must:

- preserve the ownership boundary between OwnSIS, OwnID, and Moodle;
- enforce tenant isolation across data, authorization, integrations, and operations;
- keep domain behavior inside explicit modular boundaries;
- record consequential architecture decisions as ADRs;
- make changes reviewable, testable, observable, and reversible where practical;
- keep documentation synchronized with the behavior and constraints it governs;
- support long-term evolution without premature distribution of the system.

Contributors are responsible for understanding the relevant project documents and accepted ADRs before changing behavior or architecture.

## Technology Stack

| Area | Technology |
| --- | --- |
| Backend language | Python 3.14 |
| Backend framework | FastAPI |
| Data platform | PostgreSQL |
| Database change management | Alembic |
| Frontend framework | Next.js |
| Frontend language | TypeScript |
| Architecture | Domain-Driven Design, Modular Monolith, Event-Driven Architecture |
| Packaging and dependency workflow | uv |
| Runtime packaging | Docker |
| Identity | OwnID |
| Learning platform | Moodle |
| AI integration | MCP |

The stack is a constraint, not a complete design. Detailed technology choices that materially affect longevity, security, operability, or coupling require documented justification and, when architectural, an ADR.

## Repository Philosophy

- **Documentation is part of the product.** Architecture, security expectations, coding standards, and decisions must be maintained with the implementation they govern.
- **Domain language is deliberate.** Names must reflect concepts validated through domain discovery rather than terminology inherited from a legacy system.
- **Boundaries are more important than directory aesthetics.** A modular monolith succeeds only when dependency direction and ownership are enforced.
- **Explicit code is preferred.** Readable intent, strong types, clear contracts, and straightforward control flow are favored over clever compression or hidden behavior.
- **Change is evidence-driven.** New abstractions, dependencies, infrastructure, and service boundaries require a demonstrated need.
- **Security is structural.** Tenant context, authorization, secrets handling, auditability, and least privilege are designed into every relevant path.
- **No legacy compatibility is assumed.** OpenSIS behavior, schemas, and interfaces have no authority unless separately adopted through OwnSIS requirements and decisions.

## Documentation Map

The numbered documents in `docs/` move from project context and requirements through architecture, domain boundaries, security, engineering standards, agent rules, and roadmap. The `adr/` directory records durable architecture decisions. The root `AGENTS.md` defines mandatory operating rules for AI agents working in this repository.

Task instructions and engineering authority are separate concerns. For agent behavior, system instructions and the user's explicit request take precedence. The root `AGENTS.md` and every closer applicable `AGENTS.md` then apply cumulatively; a closer file may add constraints but cannot weaken the root rules. An agent must stop when those instructions conflict. A task instruction can authorize work, but it does not silently rewrite a durable product or architecture decision.

For engineering decisions, approved requirements and domain authority define what the system must preserve. Accepted ADRs govern the specific architectural choices made within those constraints; architecture, security, module, integration, and coding documents elaborate their application. A maintainer direction that changes a durable decision must be recorded in the appropriate requirement, ADR, or governing document as part of the approved change. Any conflict that could alter behavior, scope, security, data ownership, or architecture must be raised and resolved in the source of truth rather than handled through undocumented precedence.

## Assumptions

- OwnSIS begins as a greenfield implementation with no obligation to preserve OpenSIS code, schemas, or interfaces.
- Each organization is one tenant and retains its own isolation boundary even when future domain relationships connect organizations.
- OwnID remains the sole identity provider, while OwnSIS remains responsible for authorization decisions over its own resources.
- Moodle does not become the source of truth for OwnSIS academic or administrative records.
- PostgreSQL is the authoritative transactional data platform for OwnSIS.
- The product will be maintained by changing teams over a horizon of at least fifteen years.
- Business capabilities and detailed domain rules will be established through deliberate domain discovery rather than inferred from legacy behavior.

## Future Evolution

The repository is expected to grow through bounded, reviewable increments. Domain modules, public contracts, storage models, deployment topology, and integration details will be introduced only when supported by requirements and documented decisions. The modular monolith may evolve internally or yield independently deployed components when measured operational or organizational needs justify that change; such evolution must preserve ownership, security, observability, and data consistency and must be recorded through ADRs.
