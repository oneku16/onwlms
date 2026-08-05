# OwnSIS Platform Requirements

## Purpose

This document defines the platform-level requirements that every OwnSIS capability must satisfy. It converts the project context and vision into verifiable engineering obligations while intentionally leaving education workflows, interfaces, and persistence structures to later domain discovery and design.

## Scope

These requirements apply to the maintained OwnSIS backend, web application, background execution, data management, integrations, deployment artifacts, and contributor workflows. They govern all modules and all supported organizations.

This document does not specify domain processes, endpoint shapes, event payloads, database schemas, screen layouts, pricing models, or infrastructure-provider choices. A capability-specific requirement may add stricter obligations, but it may not weaken these platform requirements without an accepted architecture decision and corresponding update to this document.

## Requirement Language and Traceability

The terms **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are normative:

- **MUST** and **MUST NOT** define conditions required for acceptance.
- **SHOULD** defines an expected choice that may be varied only with documented rationale and review.
- **MAY** identifies an allowed option, not a commitment.

Requirement identifiers are stable references. Rewording must preserve an identifier only when its obligation remains materially the same. Superseded requirements remain discoverable in version history and, when architectural, in the ADR record.

Every delivered capability MUST identify the platform requirements that apply to it and provide reviewable evidence appropriate to its risk. Evidence may include automated tests, architecture checks, migration exercises, security analysis, operational demonstrations, or maintained documentation.

## Product and Ownership Requirements

### Product identity

- **OWN-PROD-001:** OwnSIS MUST operate as an independent product and codebase. It MUST NOT depend on OpenSIS source code, runtime components, undocumented behavior, or data structures.
- **OWN-PROD-002:** Compatibility with any external or predecessor system MUST be an explicit, documented integration or import concern. It MUST NOT constrain the core implicitly.
- **OWN-PROD-003:** The platform MUST support schools, colleges, and universities without encoding one institution type as the universal domain model.
- **OWN-PROD-004:** Institutional variation SHOULD be supported through governed configuration, extension, and integration mechanisms rather than organization-specific source forks.

### Authority and data ownership

- **OWN-DATA-001:** OwnSIS MUST be authoritative for the academic and administrative data within its declared product boundary.
- **OWN-DATA-002:** Every category of exchanged information MUST have one documented authoritative owner and a documented conflict policy.
- **OWN-DATA-003:** Replication, caching, reporting, export, or synchronization MUST NOT silently transfer authority to another module or system.
- **OWN-DATA-004:** Changes to authoritative information MUST pass through the owning domain capability and its validation and authorization rules.
- **OWN-DATA-005:** Data lineage sufficient to explain the origin and consequence of material imported, synchronized, derived, or automated changes MUST be retained according to the applicable data policy.

## Multi-Tenancy Requirements

### Tenant boundary

- **OWN-TEN-001:** Each organization MUST be one tenant and the boundary for its data, configuration, authorization, integrations, subscription, and operational context.
- **OWN-TEN-002:** Every tenant-owned operation MUST execute with a verified organization context. Missing, ambiguous, or untrusted tenant context MUST result in denial before domain behavior is invoked.
- **OWN-TEN-003:** Tenant isolation MUST apply consistently to interactive requests, background work, scheduled work, events, integrations, caches, search, reporting, exports, observability, and administrative tooling.
- **OWN-TEN-004:** Tenant-scoped identifiers alone MUST NOT be treated as proof that an actor may access the identified organization or resource.
- **OWN-TEN-005:** Privileged cross-organization operations MUST be modeled separately from ordinary tenant operations, use explicit authorization, minimize accessible scope, and produce an audit record.
- **OWN-TEN-006:** A module MUST NOT infer tenant context from mutable presentation data such as a user-entered domain, branding value, or request field without verification against trusted platform context.
- **OWN-TEN-007:** Data structures, queries, caches, event metadata, logs, and storage paths that hold tenant-owned information MUST use an isolation mechanism appropriate to their failure risk.
- **OWN-TEN-008:** Automated tests MUST exercise both permitted same-tenant behavior and denied cross-tenant behavior at module and system boundaries.

### Organization autonomy

- **OWN-TEN-009:** Each organization MUST be able to maintain its own branding, domain configuration, user membership, permissions, integrations, and subscription context without changing another organization.
- **OWN-TEN-010:** Organization configuration MUST have explicit ownership, validation, and audit behavior and MUST NOT be implemented as ungoverned global settings.
- **OWN-TEN-011:** Organization lifecycle controls MUST preserve legal, contractual, retention, export, and recovery obligations while preventing suspended or inactive contexts from continuing unauthorized operations.
- **OWN-TEN-012:** Future relationships between organizations MUST be expressed through authorized domain concepts; they MUST NOT be implemented by weakening the tenant boundary.

## Identity and Access Requirements

### Authentication through OwnID

- **OWN-IAM-001:** OwnID MUST be the only identity provider and the only authority permitted to assert a human identity to OwnSIS.
- **OWN-IAM-002:** OwnSIS MUST NOT store or verify human passwords, issue an alternative interactive identity, or provide an authentication path that bypasses OwnID.
- **OWN-IAM-003:** Identity assertions MUST be validated for issuer, intended audience, integrity, validity period, and other protocol-required properties before use.
- **OWN-IAM-004:** The association between an OwnID identity and OwnSIS organization context MUST use a stable identity attribute and MUST NOT depend solely on mutable display attributes.
- **OWN-IAM-005:** Loss, revocation, or invalidation of an OwnID session or credential MUST fail closed at the OwnSIS trust boundary.
- **OWN-IAM-006:** Non-human workload identities, if introduced, MUST have explicit ownership, authentication, purpose, rotation, and least-privilege authorization. Their authentication mechanism MUST NOT operate as another identity provider, issue human identities, or permit implicit human impersonation.

### Authorization within OwnSIS

- **OWN-IAM-007:** OwnSIS MUST own organization membership, status, roles, permissions, and authorization policy for ERP capabilities.
- **OWN-IAM-008:** Authentication MUST NOT imply organization membership or permission.
- **OWN-IAM-009:** Authorization MUST be enforced at the application capability boundary and MUST NOT depend solely on user-interface visibility.
- **OWN-IAM-010:** Permission evaluation MUST include the verified tenant context and the specific requested capability.
- **OWN-IAM-011:** Access MUST default to denial when identity, tenant, membership, permission, or policy context is missing or inconsistent.
- **OWN-IAM-012:** Material changes to membership, privilege, and access policy MUST be auditable without exposing authentication secrets.

## Architecture Requirements

### Modular monolith

- **OWN-ARC-001:** OwnSIS MUST begin and remain a modular monolith unless an accepted ADR authorizes extraction of a defined capability.
- **OWN-ARC-002:** Each module MUST represent a cohesive business capability with an explicit public boundary, named ownership, and documented responsibilities.
- **OWN-ARC-003:** A module MUST own its domain model and access to its persisted information. Other modules MUST NOT query or mutate that information through private storage structures.
- **OWN-ARC-004:** Dependencies between modules MUST be explicit, directional, and enforceable through automated architecture checks.
- **OWN-ARC-005:** Shared technical facilities MUST remain domain-neutral and MUST NOT become an informal location for cross-module business behavior.
- **OWN-ARC-006:** Framework, transport, persistence, and external-system concerns MUST be kept outside the core domain model.
- **OWN-ARC-007:** A new distributed runtime component MUST demonstrate a concrete need for independent scaling, isolation, lifecycle, or ownership and MUST be approved through an ADR.

### Domain-Driven Design

- **OWN-DDD-001:** Domain language MUST be developed with domain experts and used consistently in requirements, documentation, code, tests, and operational communication.
- **OWN-DDD-002:** Bounded contexts MUST be defined by differences in meaning and responsibility rather than by technical layer.
- **OWN-DDD-003:** Domain invariants MUST be enforced by the module that owns the affected concept.
- **OWN-DDD-004:** References across bounded contexts MUST use stable contracts or identifiers and MUST NOT share mutable domain objects.
- **OWN-DDD-005:** Translation between external or neighboring models and an owning domain model MUST occur at an explicit boundary.
- **OWN-DDD-006:** Abstractions MUST reflect demonstrated domain concepts or engineering constraints; speculative generalization MUST NOT replace clear capability-specific language.

### Event-driven collaboration

- **OWN-EVT-001:** Events MUST represent meaningful facts with a named owner and defined consumers; they MUST NOT be generic notifications of database changes.
- **OWN-EVT-002:** The choice between direct and event-driven collaboration MUST reflect consistency, latency, failure, and ownership requirements rather than a blanket preference for asynchrony.
- **OWN-EVT-003:** Events that cross a module or system boundary MUST have explicit versioning and compatibility rules.
- **OWN-EVT-004:** Consumers MUST handle the duplicate delivery, retry, reordering, and partial-failure conditions permitted by their delivery mechanism.
- **OWN-EVT-005:** Publication coupled to an authoritative state change MUST use a reliability mechanism that prevents an accepted state change from being silently disconnected from its required event.
- **OWN-EVT-006:** Event metadata MUST carry sufficient trusted context for authorization, tenancy, correlation, and observability without exposing unnecessary protected information.
- **OWN-EVT-007:** Event processing failures MUST be observable and recoverable through a documented operational mechanism.

## Integration Requirements

### General integration boundary

- **OWN-INT-001:** Each integration MUST have a documented purpose, owner, authority boundary, tenant configuration model, security model, compatibility policy, and failure behavior before production use.
- **OWN-INT-002:** External representations MUST be translated at an adapter boundary and MUST NOT become the OwnSIS domain model by default.
- **OWN-INT-003:** Integration credentials and configuration MUST be isolated by organization where the external relationship is tenant-specific.
- **OWN-INT-004:** External calls MUST have bounded time, explicit failure handling, and observable outcomes.
- **OWN-INT-005:** Retries MUST be bounded and safe for the operation. An integration MUST NOT retry a non-idempotent effect without a mechanism that prevents unintended duplication.
- **OWN-INT-006:** Integration status and synchronization failures MUST be diagnosable without requiring disclosure of protected payloads.
- **OWN-INT-007:** Removing or disabling an integration MUST leave authoritative OwnSIS information in a valid and explainable state.

### Moodle

- **OWN-MDL-001:** Moodle MUST be treated as the learning platform and MUST NOT become the authoritative owner of OwnSIS academic or administrative data.
- **OWN-MDL-002:** The Moodle integration MUST explicitly document the authority, direction, timing, and conflict behavior of every exchanged information category.
- **OWN-MDL-003:** Moodle unavailability or rejected data MUST NOT silently corrupt, discard, or reclassify authoritative OwnSIS information.
- **OWN-MDL-004:** Reconciliation MUST be possible for exchanges where either system can accept a change independently of the other.
- **OWN-MDL-005:** Moodle-specific concepts MUST remain in the integration boundary unless they have independently validated meaning in the OwnSIS domain.

### MCP and AI

- **OWN-AI-001:** AI integrations MUST use MCP as their governed capability boundary.
- **OWN-AI-002:** An AI actor MUST authenticate, establish tenant context, and pass the same authorization and domain validation as a non-AI actor performing an equivalent operation.
- **OWN-AI-003:** MCP tools MUST expose bounded application capabilities and MUST NOT provide unrestricted database, filesystem, secret, or internal module access.
- **OWN-AI-004:** Consequential actions MUST be distinguishable from read-only analysis and MUST support human approval where risk policy requires it.
- **OWN-AI-005:** AI-generated input MUST be treated as untrusted and validated before it influences authoritative state or an external side effect.
- **OWN-AI-006:** Use of AI MUST be auditable to the initiating identity, organization, invoked capability, and outcome without retaining unnecessary prompt or protected content.
- **OWN-AI-007:** A core ERP capability MUST remain safe and operable when an AI provider or MCP integration is unavailable.
- **OWN-AI-008:** Model behavior MUST NOT be relied upon to enforce access control, tenancy, domain invariants, or deterministic recordkeeping.

## Data and Persistence Requirements

- **OWN-PER-001:** PostgreSQL MUST be the durable relational data platform for authoritative OwnSIS information.
- **OWN-PER-002:** All production schema evolution MUST be represented by version-controlled Alembic migrations and reviewed with the related application change.
- **OWN-PER-003:** Migrations MUST have automated verification from every supported starting version and MUST include a documented recovery approach appropriate to the risk of the change.
- **OWN-PER-004:** Deployment sequencing MUST prevent incompatible application and schema versions from causing silent data corruption.
- **OWN-PER-005:** Transaction boundaries MUST align with the invariants owned by a module. Cross-boundary consistency MUST be made explicit rather than assumed.
- **OWN-PER-006:** Stored information MUST have an identified owner, sensitivity classification, lifecycle, and retention basis before production collection.
- **OWN-PER-007:** Time, locale, and calendar representations MUST preserve the context needed to interpret institutional records correctly.
- **OWN-PER-008:** Destructive or irreversible data operations MUST be explicit, authorized, auditable, and exercised against recovery procedures before production use.
- **OWN-PER-009:** Backup restoration MUST be tested on a defined operational cadence, and the result MUST be recorded and reviewable.
- **OWN-PER-010:** Derived data MUST be reproducible from or traceable to its authoritative inputs where its use affects decisions or institutional records.

## Security, Privacy, and Audit Requirements

- **OWN-SEC-001:** Threat modeling MUST cover tenant boundaries, identity flows, privileged operations, integrations, and protected data before a capability is released.
- **OWN-SEC-002:** Least privilege and separation of duties MUST be applied to application actors, operators, integrations, and infrastructure identities.
- **OWN-SEC-003:** Secrets MUST NOT be committed to the repository, embedded in images, included in client bundles, or written to logs.
- **OWN-SEC-004:** Protected information MUST use current, reviewed protection mechanisms in transit and at rest for the supported environment.
- **OWN-SEC-005:** Logs, metrics, traces, diagnostics, and error responses MUST minimize personal, credential, and tenant-sensitive information.
- **OWN-SEC-006:** Security-relevant and materially consequential actions MUST produce tamper-resistant audit information with actor, tenant, action, time, target context, and outcome as applicable.
- **OWN-SEC-007:** Audit information MUST be access-controlled and retained independently of ordinary mutable presentation data.
- **OWN-SEC-008:** Dependencies and container artifacts MUST be scanned for known vulnerabilities, and release policy MUST define how severity and exploitability affect promotion.
- **OWN-SEC-009:** Supported security updates MUST be deployable without requiring unrelated feature adoption.
- **OWN-SEC-010:** Data export, correction, retention, and erasure capabilities MUST be enforceable according to the applicable organization policy and legal basis without violating record-integrity obligations.

## User Experience Requirements

- **OWN-UX-001:** The user experience MUST make the active organization context visible anywhere an action could affect tenant-owned information.
- **OWN-UX-002:** User-interface terminology MUST align with the owning domain language and MUST remain consistent across modules unless a bounded-context distinction is intentional and explained.
- **OWN-UX-003:** The web application MUST enforce authorization for presentation but MUST NOT be the authoritative enforcement point.
- **OWN-UX-004:** Supported user-facing capabilities MUST meet the accessibility standard adopted by project governance, with automated and human verification appropriate to the interaction.
- **OWN-UX-005:** User-facing content and data formatting MUST support localization without embedding one language, time zone, or locale as domain truth.
- **OWN-UX-006:** Material actions and failures MUST provide enough context for an authorized user to understand the outcome and a safe next step.
- **OWN-UX-007:** Sensitive information MUST not be exposed through browser storage, URLs, telemetry, cached pages, or error details beyond documented need.

## Reliability and Operability Requirements

- **OWN-OPS-001:** Each deployable runtime MUST expose machine-readable health and readiness information that distinguishes process availability from dependency readiness.
- **OWN-OPS-002:** Logs, metrics, and traces MUST support correlation across a use case and its permitted asynchronous work while preserving tenant and privacy controls.
- **OWN-OPS-003:** Every production capability MUST define observable success and failure conditions before release.
- **OWN-OPS-004:** Timeouts, concurrency limits, retry policies, and resource bounds MUST be explicit for external and asynchronous work.
- **OWN-OPS-005:** Background work MUST record ownership, tenant context, attempt outcome, and terminal failure in an operable form.
- **OWN-OPS-006:** A failure in one organization's workload SHOULD be contained so it does not exhaust shared capacity or prevent diagnosis for other organizations.
- **OWN-OPS-007:** Service objectives and capacity thresholds MUST be defined from an identified user need and workload before they are used as release or scaling criteria.
- **OWN-OPS-008:** Recovery procedures for data loss, failed migration, integration backlog, and compromised credentials MUST be documented and exercised at a cadence proportional to risk.
- **OWN-OPS-009:** Production configuration MUST be explicit, validated at startup, and separable from build artifacts.
- **OWN-OPS-010:** Operational changes MUST be attributable, reviewable, and reversible where the underlying operation permits reversal.

## Engineering and Delivery Requirements

- **OWN-ENG-001:** Backend code MUST target Python 3.14 and FastAPI; frontend code MUST target Next.js and TypeScript.
- **OWN-ENG-002:** Python dependency resolution and project execution MUST use `uv`; dependency versions used for a release MUST be reproducible.
- **OWN-ENG-003:** Supported runtime components MUST be packaged with Docker using reproducible, reviewable build definitions.
- **OWN-ENG-004:** Builds MUST avoid environment-specific source changes and MUST identify the source revision and dependency state from which an artifact was produced.
- **OWN-ENG-005:** Static analysis, formatting, type checks, unit tests, module-boundary checks, and security checks defined by repository policy MUST pass before merge.
- **OWN-ENG-006:** A change to a domain invariant MUST include automated tests at the owning module boundary.
- **OWN-ENG-007:** A change to an integration or event contract MUST include compatibility and failure-path verification.
- **OWN-ENG-008:** A change affecting tenancy, authorization, protected data, or destructive behavior MUST receive focused review and negative-path tests.
- **OWN-ENG-009:** Readability and explicit intent MUST take priority over reducing line count or introducing generalized mechanisms.
- **OWN-ENG-010:** Generated code or AI-assisted output MUST meet the same authorship, licensing, security, testing, and review requirements as human-written work.
- **OWN-ENG-011:** Documentation and accepted ADRs affected by a change MUST be updated in the same reviewed change set.
- **OWN-ENG-012:** Supported developer workflows MUST be documented and executable from a clean checkout without private setup knowledge.

## Governance and Open-Source Requirements

- **OWN-GOV-001:** Material architectural decisions MUST be recorded as ADRs with context, decision, consequences, and status.
- **OWN-GOV-002:** Module ownership and review responsibility MUST be discoverable in the repository.
- **OWN-GOV-003:** Contributions MUST pass the same quality and security gates regardless of contributor affiliation.
- **OWN-GOV-004:** Third-party code and assets MUST have provenance and licensing compatible with the project's adopted license and distribution model.
- **OWN-GOV-005:** Breaking changes, supported versions, deprecation, and security reporting MUST follow published project policies.
- **OWN-GOV-006:** Repository documentation MUST be sufficient for an authorized contributor to understand, build, verify, and review the platform without relying on private institutional knowledge.
- **OWN-GOV-007:** Exceptions to normative engineering rules MUST be narrow, time-bounded by an explicit removal condition, owned, and reviewable; an exception MUST NOT silently redefine the rule.

## Acceptance Evidence

Compliance is demonstrated at the earliest boundary capable of proving the property and again at higher-risk integration boundaries. The minimum evidence model is:

| Requirement area | Required evidence |
| --- | --- |
| Tenant isolation | Automated positive and negative tests, architecture review, and operational context inspection |
| Identity and authorization | Trust-boundary tests, denied-path tests, privilege-change audit verification, and security review |
| Module boundaries | Automated dependency checks, public-contract tests, and ownership documentation |
| Domain correctness | Executable invariant tests using domain language and reviewed examples |
| Events and integrations | Contract, compatibility, duplication, retry, timeout, and reconciliation tests as applicable |
| Persistence | Migration verification, deployment-sequence analysis, integrity checks, and recorded recovery exercise |
| Security and privacy | Threat model, dependency and artifact scans, secret checks, focused tests, and audit inspection |
| User experience | Accessibility checks, tenant-context review, localization review, and authorization verification |
| Operations | Health signals, correlated telemetry, failure injection appropriate to risk, and recovery runbooks |
| Delivery and governance | Reproducible clean build, required CI gates, documentation review, and ADR linkage |

A document alone does not prove a runtime property, and a passing test does not excuse a missing ownership or operational model.

## Responsibilities

This document is responsible for establishing platform-wide acceptance obligations and a common traceability language. It is not responsible for inventing or approving domain behavior.

- Product and domain owners are responsible for validating capability requirements and authoritative data boundaries.
- Architecture maintainers are responsible for preserving module, dependency, event, persistence, and integration coherence.
- Security maintainers are responsible for defining risk-based controls and reviewing trust-boundary changes.
- Module owners are responsible for mapping applicable requirements to implementation and evidence.
- Operators are responsible for validating service objectives, recovery practices, and production observability.
- Contributors are responsible for identifying affected requirements and including the necessary evidence in each change.
- Reviewers are responsible for rejecting a change whose evidence does not demonstrate its stated obligations.

## Assumptions

- Organizations share a platform runtime while retaining independent data and configuration boundaries.
- OwnID provides standards-based identity assertions suitable for validation by OwnSIS.
- OwnSIS can own organization-specific authorization without becoming an identity provider.
- Moodle provides supported integration mechanisms while remaining independently available and versioned.
- PostgreSQL, Alembic, Docker, `uv`, Python, FastAPI, Next.js, and TypeScript remain supported within the project's release policy.
- The deployment environments can provide protected secret storage, encrypted transport, backup storage, and operational telemetry.
- Quantitative availability, recovery, latency, and capacity objectives depend on validated deployment and user needs and will be recorded as operational requirements before production commitment.
- Legal and regulatory obligations vary by operator and jurisdiction; the platform provides enforceable mechanisms while deployments supply applicable policy.
- New domain capabilities will be discovered and validated without weakening these platform-wide controls.

## Future Evolution

Requirements will evolve through version-controlled review as operational evidence, regulation, domain discovery, and platform scale change. New obligations should be added at the narrowest correct scope, with stable identifiers and explicit verification evidence.

Changes to foundational requirements for tenancy, identity authority, data ownership, module boundaries, or integration authority require an impact analysis and an accepted or superseding ADR. A requirement may become more stringent without forcing unrelated redesign when module boundaries and contracts remain explicit.

Quantitative service levels, supported compatibility windows, accessibility conformance targets, retention profiles, and regional controls will be incorporated when their operating context is approved. They must be expressed as verifiable policy rather than universal numbers detached from workload, risk, or jurisdiction.
