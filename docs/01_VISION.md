# OwnSIS Vision

## Purpose

This document defines the long-term engineering and product vision for OwnSIS. It describes the outcomes the platform must make possible, the qualities it must preserve, and the principles used to evaluate major investments over a lifespan of at least fifteen years.

## Scope

The vision applies to the full OwnSIS platform and its open-source ecosystem. It covers the intended institutional value, architectural posture, experience goals, operational qualities, and measures of durable progress.

It does not specify individual education workflows, screen designs, APIs, database models, commercial packaging, or a release schedule. Those artifacts must remain consistent with this vision while being developed through their own validation and governance processes.

## Vision Statement

OwnSIS will be a dependable, comprehensible Education ERP that lets schools, colleges, and universities govern their academic and administrative information on a shared platform without surrendering organizational isolation or institutional autonomy.

The platform will combine a stable core with explicit module and integration boundaries. Institutions will be able to adopt capabilities incrementally, configure their own organizational context, and integrate with identity and learning systems without fragmenting the codebase into customer-specific products.

## Intended Outcomes

### Institutional control

Each organization can operate with its own identity context, users, permissions, branding, domains, integrations, and subscriptions. Configuration is explicit, governed, and isolated. Institutional data remains portable and understandable rather than being trapped in undocumented implementation behavior.

### Trustworthy records

Academic and administrative information has clear ownership, validation, provenance, access control, and lifecycle rules. The platform makes consequential change observable and supports recovery and investigation as first-class operational concerns.

### Sustainable change

Teams can change one business capability without needing broad knowledge of every other capability. Module boundaries, domain language, automated verification, controlled migrations, and documented decisions keep the cost of change proportional to the change itself.

### Coherent integration

OwnID, Moodle, and other approved systems interact through explicit, versioned, observable boundaries. Integration failure cannot silently corrupt authoritative data or erase tenant context. External capability can evolve without becoming hidden ownership of the OwnSIS domain.

### Responsible automation

MCP-enabled AI capabilities operate under the same authorization, tenancy, audit, and domain rules as other actors. Automation is reviewable and bounded according to impact. The platform remains useful and operable when an AI capability is unavailable.

### Open engineering

An external contributor can understand why the system is shaped as it is, reproduce supported development and verification workflows, and propose changes without relying on private architectural knowledge. Governance favors durable public artifacts over informal convention.

## Product Principles

1. **One platform, many organizations.** Multi-tenancy is native to every capability and is never retrofitted at the edge.
2. **Institutional configuration over institutional forks.** Valid variation is modeled deliberately; organization-specific source branches are not a product strategy.
3. **Own the ERP domain.** OwnSIS remains authoritative for academic and administrative data and does not blur that ownership for integration convenience.
4. **Identity is delegated; authorization is contextual.** OwnID alone authenticates identities. OwnSIS determines what an authenticated identity may do within an organization.
5. **Learning is integrated, not absorbed.** Moodle owns learning delivery. OwnSIS and Moodle collaborate without duplicating product boundaries.
6. **Capabilities are cohesive.** A module represents a meaningful business capability, not a technical layer or arbitrary directory.
7. **Defaults are safe.** Secure isolation, least privilege, auditability, and data protection do not depend on optional configuration.
8. **Complexity must earn its place.** A more distributed, asynchronous, generic, or abstract design requires evidence that it solves a present platform need.
9. **Compatibility is explicit.** Contracts and supported behavior evolve through versioning and migration policy, not accidental coupling.
10. **Clarity is a feature.** Readability, useful documentation, actionable failures, and operational transparency are part of product quality.

## Engineering Vision

OwnSIS is developed as a domain-oriented modular monolith. Its modules execute as a cohesive system while retaining explicit ownership of behavior, data access, and contracts. This gives the platform transactional and operational simplicity without accepting an undifferentiated codebase.

Domain-Driven Design supplies the language and boundary discipline. Event-driven collaboration is used where a meaningful fact must cross boundaries, where temporal decoupling is valuable, or where reliable side effects require explicit handling. Direct collaboration remains appropriate when an immediate result is part of a single use case and the dependency is allowed.

The backend uses Python 3.14 and FastAPI, durable relational information is held in PostgreSQL, and database change is managed through Alembic. The web application uses Next.js and TypeScript. Docker provides reproducible runtime packaging, and `uv` provides a consistent Python dependency and execution workflow. Technology choices must be wrapped by domain and module boundaries so that framework change does not redefine business meaning.

## Fifteen-Year Design Posture

Long-term evolution is achieved through disciplined change rather than prediction. The platform therefore favors:

- explicit bounded contexts and ownership over global abstractions;
- stable domain vocabulary over framework terminology;
- additive contract evolution and controlled deprecation over surprise breakage;
- reversible migrations and tested recovery over one-way operational assumptions;
- architectural fitness checks over rules enforced only in review;
- replaceable adapters around external systems over integration logic in the domain;
- supported extension points over source forks;
- recorded decisions over organizational memory;
- accessible observability over diagnosis through database inspection; and
- incremental delivery of coherent vertical capabilities over large horizontal rewrites.

The architecture does not assume that current frameworks, deployment environments, or organization structures will remain unchanged. It does assume that domain meaning, data integrity, tenant isolation, and decision traceability must survive those changes.

## Quality Attributes

### Security and privacy

Every operation is performed in an authenticated, authorized, and tenant-aware context where applicable. Sensitive information is minimized, protected throughout its lifecycle, and excluded from unnecessary disclosure. Security controls are testable and default to denial when context is absent or ambiguous.

### Correctness and integrity

Domain invariants are enforced at the owning boundary. Cross-module and external side effects account for retries, duplication, partial failure, and reordering where those conditions are possible. Migration and recovery procedures protect the semantic integrity of stored information.

### Maintainability

A contributor can locate the owner of a capability, understand allowed dependencies, and test a change without reconstructing hidden conventions. Code favors explicit behavior and common language over compactness, metaprogramming, or premature generalization.

### Evolvability

Modules, contracts, and stored information can evolve through documented and testable transitions. The platform can replace an integration or framework adapter without rewriting unrelated domain behavior.

### Operability

Operators can determine system health, tenant-scoped impact, integration state, and the outcome of consequential operations without exposing protected data. Failure modes are visible, bounded, and recoverable through documented mechanisms.

### Performance and scalability

The platform measures real workloads and scales the simplest constrained component first. Tenant isolation and correctness are never traded for throughput. Capacity decisions use observed demand and defined service objectives rather than speculative distribution.

### Accessibility and international readiness

User-facing capabilities are designed for inclusive access and for institutions operating with different languages, locales, calendars, time zones, and regulatory contexts. These concerns are architectural inputs, not late presentation-layer corrections.

### Portability

Supported environments use reproducible builds, explicit configuration, and controlled state transitions. Institution-owned information can be exported in a documented, usable form subject to authorization and retention obligations.

## Experience Vision

People should experience OwnSIS as one coherent institutional system even though the internals are modular. Navigation, terminology, authorization feedback, and error behavior should be consistent across capabilities. The system should reveal enough context for users to understand which organization they are acting in and the consequence of a material action.

Administrators should be able to distinguish platform behavior from organization configuration and integration state. Developers and operators should receive errors with actionable context while protected data remains protected. Accessibility, localization, and responsive interaction are baseline concerns for every user-facing capability.

## Explicit Non-Goals

The vision does not include:

- reproducing OpenSIS internals or preserving undocumented OpenSIS behavior;
- using OwnSIS as an identity provider alongside OwnID;
- rebuilding Moodle learning capabilities inside OwnSIS;
- making services independently deployable without demonstrated operational need;
- allowing modules to share internal models or storage access for convenience;
- permitting tenant-specific forks as the routine way to support institutional variation;
- treating events as a substitute for clear ownership or transaction design;
- allowing AI agents to bypass application capabilities, approval controls, or authorization; or
- selecting technology solely for novelty or reducing source-code line count.

## Measures of Progress

Progress toward the vision is demonstrated through evidence rather than feature count alone:

- every released capability has a named owning module and documented tenant behavior;
- automated checks prevent known cross-tenant access paths and forbidden module dependencies;
- accepted decisions and current documentation explain material architecture choices;
- supported builds, migrations, rollback or recovery procedures, and deployments are reproducible;
- integration contracts have ownership, compatibility rules, observability, and failure handling;
- security and accessibility reviews are incorporated into delivery gates;
- operational signals allow impact to be identified without exposing sensitive records;
- contributor workflows can be executed from repository documentation; and
- deprecations and breaking changes follow an explicit, published lifecycle.

Quantitative service objectives belong to the operational requirements for a defined deployment and workload. They must be measured before they are used to justify architectural distribution.

## Responsibilities

This document is responsible for:

- expressing the durable direction of the platform;
- defining outcome and quality priorities used to evaluate trade-offs;
- aligning product, domain, architecture, security, operations, and contribution practices;
- setting explicit non-goals that protect the system boundary; and
- providing stable criteria for roadmap and architecture review.

Product and engineering leadership are responsible for keeping investments aligned with the vision. Module owners are responsible for translating it into bounded requirements and observable outcomes. Reviewers are responsible for challenging changes that improve a local concern by weakening platform-wide qualities.

## Assumptions

- OwnSIS will serve organizations with materially different scale, policy, language, and integration needs.
- Multiple organizations will share platform resources while requiring strong logical isolation.
- Organizations expect long-lived access to accurate academic and administrative records.
- OwnID will remain the sole authentication authority, while OwnSIS will retain organization-specific authorization responsibilities.
- Moodle will remain the learning platform and will evolve independently of OwnSIS.
- AI capabilities will change faster than the core ERP and must remain replaceable, governed integrations.
- Contributors and operators will change over the lifetime of the project, making explicit documentation and automation essential.
- Regulatory and security obligations will vary across deployments and will become more demanding over time.
- The modular monolith can satisfy expected needs until measured constraints demonstrate otherwise.

## Future Evolution

The vision is reviewed when evidence changes a foundational premise: the product boundary, tenancy model, authoritative-system relationships, supported institutional scope, or expected operating model. Refinement may add stronger quality expectations, clearer governance, or new classes of extension without discarding the principles of explicit ownership and controlled evolution.

If a module develops a sustained need for independent scaling, isolation, release cadence, or ownership, it may become a candidate for extraction. Extraction is an evolution of an already enforced boundary, not a reason to weaken modularity in advance. The decision must be recorded through an ADR and must preserve contracts, tenant guarantees, data ownership, and observability.

New channels, analytics, regional capabilities, and AI-assisted workflows may expand the platform. They must enter through governed module or integration boundaries and remain subordinate to domain invariants, human accountability, and institutional control.
