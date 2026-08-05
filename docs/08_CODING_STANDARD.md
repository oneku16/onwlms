# Coding Standard

## Purpose

This document defines the engineering standards for source code and code-adjacent artifacts in OwnSIS. It translates the platform's long-term architecture goals into consistent expectations for readability, correctness, change safety, and reviewability.

## Scope

The standard applies to Python, TypeScript, SQL migrations, configuration, tests, automation, and documentation that accompanies implementation. It governs how code is structured and assessed; it does not define business capabilities, public APIs, database schemas, or module contents.

Repository-enforced formatter, linter, type-checker, build, and test configurations are the executable expression of this standard. Changing a platform-wide quality rule is a deliberate repository change and may require an ADR when it affects architecture or long-term maintainability.

## Responsibilities

Authors are responsible for producing focused, understandable changes that satisfy this standard and for adding verification proportional to risk. Reviewers are responsible for evaluating behavior, boundaries, security, operability, and maintenance cost rather than relying solely on automated checks. Maintainers are responsible for keeping automated enforcement and written policy aligned.

## Core Priorities

When qualities compete, use this order of priority:

1. security, tenant isolation, and data integrity;
2. functional correctness and explicit failure behavior;
3. preservation of domain and module boundaries;
4. readability and maintainability;
5. testability and operational visibility;
6. measured performance;
7. brevity.

Shorter code is not inherently better. A design is preferred when a future maintainer can understand its responsibility, dependencies, invariants, and failure modes without reconstructing hidden conventions.

## General Source Standards

- Each unit has one coherent responsibility and a name that communicates domain intent.
- Public contracts are narrow, typed, documented, and stable enough for their consumers.
- Control flow and state changes are explicit. Hidden mutation, action at import time, global registries, and order-dependent initialization are avoided.
- Invalid states are prevented or rejected close to the owning boundary. Validation is not duplicated inconsistently across delivery mechanisms.
- Error handling preserves causality and distinguishes expected business outcomes from programmer errors and operational failures.
- Exceptions are not swallowed. Recovery, retry, fallback, and partial-success behavior must be intentional and observable.
- Constants replace unexplained literals when a value has domain or operational meaning.
- Comments explain rationale, constraints, safety properties, and unusual tradeoffs. Dead code and commented-out implementations are removed.
- Abstractions are introduced only after their stable responsibility and consumers are understood. Coincidental similarity is not sufficient justification.
- Files and functions should remain small enough to reason about, but arbitrary size limits must not split cohesive behavior or scatter an invariant.

## Naming and Language

- Use the ubiquitous language of the relevant bounded context.
- Use one term consistently for one concept within a context; do not accumulate synonyms for stylistic variety.
- Names describe intent and ownership, not implementation history.
- Avoid vague names such as `data`, `item`, `manager`, `helper`, or `utils` when a more precise responsibility exists.
- Boolean names state the condition they represent. Operations that cause effects use verbs; values and concepts use nouns.
- Acronyms are used only when they are established project or domain language and are written consistently.
- Legacy OpenSIS terminology has no authority unless it is independently validated for OwnSIS.

## Architectural Boundaries

- Domain code contains domain concepts and invariants and remains independent of FastAPI, PostgreSQL drivers, Moodle, OwnID clients, MCP clients, and other infrastructure.
- Application code coordinates use cases, transactions, permissions, domain objects, and ports without embedding transport or vendor concerns.
- Adapters translate between external protocols or persistence mechanisms and application-owned contracts.
- Delivery code handles protocol concerns and delegates decisions to the application layer.
- Modules expose deliberate public surfaces. Importing or querying another module's internals is prohibited.
- Cross-module contracts should contain the minimum information required by the consumer and must not leak persistence representations.
- Shared code is limited to genuinely stable, context-neutral concerns. Domain concepts remain with their owner even when their structures look similar.
- Dependency cycles are design failures and must be removed rather than hidden through dynamic imports or service locators.

## Domain-Driven Design Standards

- Business rules are expressed in the domain model using validated domain language.
- Aggregates define transactional consistency boundaries and protect their own invariants.
- Entities are distinguished by identity; value objects are defined by values and are immutable in meaning.
- Application services orchestrate; they do not become repositories for domain decisions.
- Domain services are used only for domain behavior that cannot naturally belong to an entity or value object.
- Repositories persist and retrieve aggregate boundaries through domain-oriented contracts.
- Domain events name completed facts in past-tense domain language and originate from the owner of the fact.
- Commands represent intent and are not treated as facts or broadcast as generic messages.
- Translation is explicit where bounded contexts use different models or language.

## Python Standards

- Python 3.14 language semantics are the baseline; compatibility workarounds for unsupported Python versions are not introduced.
- All application-facing interfaces and non-trivial functions use precise type annotations. Broad dynamic types require a narrow, documented boundary and runtime validation.
- Imports are explicit and do not rely on wildcard behavior or import-time side effects.
- Mutable state is owned and scoped. Mutable default arguments, ambient singletons, and implicit shared caches are prohibited.
- Data structures communicate intent. Domain behavior is not reduced to unvalidated dictionaries or loosely shaped payloads.
- Asynchronous code is used for actual concurrency needs, not as a blanket convention. Blocking operations must not run unnoticed on an asynchronous execution path.
- Resource ownership is explicit, and resources are released deterministically.
- Exceptions are specific enough for callers to make safe decisions; catching the broad exception hierarchy is restricted to true process boundaries where failures are logged and handled deliberately.
- Framework dependency injection remains at delivery and composition boundaries and does not enter domain objects.

## TypeScript and Next.js Standards

- TypeScript operates in strict mode, and types model real states rather than suppressing compiler feedback.
- The unrestricted dynamic type is not used in application code. Unknown external values are validated and narrowed at the boundary.
- Components separate rendering concerns from domain decisions and remote-effect orchestration.
- Server and client execution boundaries are explicit. Sensitive data, credentials, and privileged operations remain on the server side.
- Frontend authorization controls improve usability but never substitute for server-side authorization.
- Tenant context and identity-derived data come from trusted application boundaries, not mutable browser input alone.
- Effects are explicit, scoped, and deterministic. Rendering must not trigger hidden writes.
- Shared UI abstractions are introduced around stable interaction or accessibility patterns, not superficial visual similarity.
- User-facing states cover loading, empty results, expected rejection, operational failure, and successful completion where applicable.
- Accessibility and internationalization constraints are treated as design inputs, not post-implementation polish.

## Persistence and Alembic Standards

- PostgreSQL structures implement an approved domain and data design; storage convenience must not redefine domain ownership.
- Every tenant-owned record and query path must have an explicit, reviewable tenant-isolation strategy.
- A module does not read or mutate another module's owned persistence representation as an integration shortcut.
- Schema changes are delivered through Alembic migrations and reviewed together with the application behavior that depends on them.
- Migrations must account for existing data, transaction behavior, lock duration, deployment ordering, failure recovery, and rollback or forward-repair strategy.
- Destructive or irreversible changes require explicit approval, backup and recovery reasoning, and a staged compatibility plan.
- Applied shared migrations are immutable; corrections are delivered as new migrations so history remains reproducible.
- Queries are assessed for correctness and measured performance. Indexes and denormalization require evidence and ownership, not speculation.
- Persistence errors are translated at the owning boundary and do not leak vendor details into the domain model.

## Events and Integrations

- Events have a clear owner, semantic meaning, and versioning policy before consumers depend on them.
- Event handlers are safe under the documented delivery semantics, including duplicate delivery when relevant.
- Ordering, retries, timeouts, poison messages, and partial failure are explicit design concerns rather than infrastructure assumptions.
- External integrations are accessed through owned adapters and cannot bypass application authorization, validation, tenancy, or auditing.
- OwnID, Moodle, and MCP payloads remain external representations and are translated into OwnSIS-owned concepts at the boundary.
- Logs and traces identify an operation and tenant safely without exposing credentials or sensitive personal data.

## Security and Privacy

- Authentication results from OwnID are validated at a trusted server boundary. Authorization remains explicit for every protected OwnSIS operation.
- Tenant isolation is enforced server-side and tested across both allowed and denied paths.
- Input is treated as untrusted at every external boundary, including callbacks, files, integration events, and AI-generated content.
- Secrets are obtained from approved runtime mechanisms and never committed, embedded in images, returned to clients, or written to logs.
- Sensitive data collection, exposure, retention, and logging are minimized.
- Security-relevant actions produce sufficient audit evidence without recording prohibited content.
- AI output is untrusted input. It must be constrained, validated, authorized, and observable before it can influence OwnSIS state.

## Testing and Verification

- Tests demonstrate behavior and risks; they are not written solely to mirror implementation structure or increase a coverage number.
- Domain tests cover invariants and meaningful state transitions without infrastructure dependencies.
- Application tests cover orchestration, permissions, transaction boundaries, and failure behavior through owned contracts.
- Adapter and integration tests verify translation and interaction with real protocol or persistence behavior at the appropriate boundary.
- Contract tests protect module and external integration assumptions.
- Tenant-isolation and authorization tests include negative cases and attempts to cross boundaries.
- Regression tests reproduce the failure they prevent.
- Tests are deterministic, independent, and explicit about time, randomness, identity, tenant, and external effects.
- A change is not complete merely because tests pass; formatting, static analysis, migration review, security review, and documentation may also be required.

## Dependencies and Configuration

- Every dependency must have a specific use, an accountable owner, acceptable licensing, maintained provenance, and a reviewed security and upgrade profile.
- The standard library and existing approved dependencies are preferred when they provide a clear, maintainable solution.
- Runtime and development dependencies are declared and locked through the repository's uv and frontend package workflows; ad hoc installation is prohibited.
- Configuration is validated at startup, typed where practical, and separated from secrets.
- Environment-specific values do not create environment-specific source branches or hidden behavior.
- Defaults must be safe. A missing security-critical setting fails clearly rather than silently weakening protection.

## Observability and Operations

- Operationally significant paths emit structured, actionable signals with consistent correlation context.
- Logs describe events and outcomes without duplicating sensitive payloads.
- Metrics measure service health, capacity, latency, errors, and critical integration behavior; they do not encode unbounded identifiers.
- Tracing crosses owned asynchronous and integration boundaries where it materially improves diagnosis.
- Timeouts and resource limits are explicit at external and potentially blocking boundaries.
- Health signals distinguish process availability from dependency readiness without disclosing sensitive configuration.

## Documentation and Review

- Public and cross-module contracts document purpose, ownership, inputs, outputs, errors, authorization, tenancy, and compatibility expectations.
- Non-obvious architecture choices are linked to an accepted ADR.
- Documentation changes accompany behavior changes and remain accurate after refactoring.
- Reviews evaluate domain language, boundary integrity, failure modes, tenant safety, security, data migration, observability, tests, and maintainability.
- Automated output is reviewed with the same rigor as human-authored output.

## Assumptions

- OwnSIS is a greenfield Python 3.14 and strict TypeScript system with no requirement to retain legacy code conventions.
- The modular monolith and DDD boundaries described by accepted architecture documents govern code organization.
- Repository automation will progressively encode mechanical portions of this standard.
- Security, identity, tenancy, and data ownership requirements apply consistently across synchronous, asynchronous, administrative, and AI-assisted paths.

## Future Evolution

This standard will become more specific as real domain modules and operational constraints emerge. Language versions, automated quality gates, performance budgets, compatibility policies, and test layers may be refined through reviewed changes. Refinements must preserve the core priorities, avoid retroactive exceptions for convenience, and use ADRs when they alter architecture or platform-wide engineering policy.

