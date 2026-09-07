# OwnSIS Engineering Roadmap

## Purpose

This roadmap defines the ordered engineering outcomes required to move the
current OwnSIS first-release implementation toward a sustainable production
platform. It is organized by evidence-based gates rather than dates or feature
volume. A gate is complete only when its exit evidence is reviewable and the
resulting capability can be maintained by the project.

## Scope

The roadmap covers engineering governance, platform construction, tenant and
identity trust boundaries, modular domain delivery, integration readiness,
production operations, and long-term open-source stewardship. Its current-state
snapshot classifies implementation evidence without converting it into gate
acceptance.

It does not schedule education workflows, commit to release dates, duplicate the
versioned API/schema contracts, or rank institution-specific feature requests.
Domain capabilities continue to require validated language, ownership,
invariants, and acceptance evidence even when a reversible implementation exists.

## Roadmap Rules

- Gates are ordered by dependency and risk reduction, not calendar time.
- Work within a gate may proceed in parallel when it does not assume an unproven earlier outcome.
- A demonstration is insufficient when the gate requires repeatable automation or operational evidence.
- Tenant isolation, authorization, data integrity, accessibility, and recovery are part of each capability; they are not deferred hardening phases.
- Architecture grows from validated needs. Distributed services, generic extension systems, and broad abstractions do not enter the roadmap without evidence and an accepted ADR.
- Every gate leaves the repository, documentation, and verification workflows in a coherent state.
- Production promotion requires satisfaction of all applicable earlier gates, even when implementation work overlaps.

## Current First-Release Evidence Snapshot

This snapshot describes the repository state, not a release certification. The
classifications mean:

- **Implemented:** executable code and automated repository evidence exist for a
  bounded local or controlled use case.
- **Partial:** a real capability exists, but important user, operational,
  compatibility, recovery, or governance evidence is incomplete.
- **Credential-gated:** the boundary has production-shaped code or contracts, but
  verification against the real external system requires secrets, tenants, and a
  controlled environment not stored in this repository.
- **Deferred:** the capability is intentionally unavailable or remains a contract
  only; no caller may present it as working behavior.

| Area | Classification | Current evidence and remaining gate |
| --- | --- | --- |
| Repository foundation and modular monolith | Implemented, governance partial | Project requirements, module boundaries, architecture tests, engineering workflows, and ADR-0001 are present. ADR-0002 through ADR-0009 remain Proposed and must not be treated as accepted production decisions. |
| Reproducible local engineering system | Implemented locally, partial as a gate | Locked Python/npm dependencies, Docker services, Alembic, OpenAPI generation, linting, strict typing, tests, dependency audits, and runtime image builds are automated. Independent clean-environment reproduction, artifact provenance, supported-upgrade matrices, and exercised recovery remain gate evidence. |
| Tenant and identity boundary | Implemented with controlled tests, credential-gated | Exact tenant actor context, active memberships, permissions, PostgreSQL tenant policies, negative tests, encrypted server sessions, and OwnID OIDC relying-party behavior exist. Real OwnID issuer/JWKS/refresh/revocation/logout compatibility and deployment-specific security review require provider credentials and controlled tests. |
| Core domain modules | Implemented vertical slices, partial product coverage | Organizations, People, Entitlements, Academics, Admissions, Grading, Scheduling, Audit, Outbox, Provisioning, Notifications, Integrations, self-service reads, and resumable accepted-applicant conversion have real application and persistence paths. Some portal pages remain read-only or explicitly unavailable, and the complete critical journey still requires controlled end-to-end and institutional-policy evidence. |
| Scheduling | Implemented bounded heuristic, partial | Manual scheduling, constraints, versioning, locked sessions, deterministic proposal generation, and tests exist. The heuristic is not represented as a production-grade optimizer; load, quality, and institution-specific policy validation remain open. |
| Moodle | Partial and credential-gated | Tenant configuration, encrypted tokens, mappings, supported REST calls, provisioning seams, duplicate-safe grade evidence/status, and mapped-user deadline reads exist. Deadline results are bounded live evidence from the mapped user's enrolled courses, with observation time and source version; there is no persisted deadline cache. Authenticated grade-event ingress, selected-term reconciliation, grade-scale/course-enrollment mapping, retries/quarantine, and official-grade acceptance are not implemented. Real Moodle version, permission, outage, and throttling exercises also require a controlled instance. |
| MCP | Implemented read-only foundation, credential-gated | OwnID RS256 verification, bounded JWKS caching, scope checks, per-invocation membership/permission/resource/tenant/entitlement validation, minimum-data tools, and audit evidence exist. Real OwnID-issued MCP tokens, client compatibility, provider retention/region review, and adversarial evaluation remain gated. |
| Notifications and provisioning | Partial | In-app notification state, preferences, retries, persistent provisioning jobs, bounded attempts/leases, local recording adapters, and explicit unavailable production adapters exist. Real external notification, OwnID provisioning, Moodle provisioning, and Microsoft 365 adapters are not implemented for production; credentials alone cannot enable them. |
| Frontend experience | Partial | The Next.js shell, organization context, role/permission/entitlement navigation, several administrative actions, connected self-service reads, and explicit unavailable states exist. Comprehensive workflow UX, accessibility, localization, browser compatibility, and end-to-end coverage remain incomplete. |
| Production operation | Deferred as a gate | Health/readiness, structured diagnostics, containers, and recovery guidance are foundations only. Service objectives, monitoring/alerts, managed hosting, backup restore, incident exercises, privacy lifecycle, load/noisy-tenant tests, penetration review, release/rollback, and on-call ownership are not proven. |
| Deferred product areas | Deferred | Attendance, Finance/payment balances, HR, Library, Dormitory, advanced analytics, production-grade optimizer selection, object storage, custom-domain automation, and destructive data-lifecycle policy remain outside the working release. |

### Gate Assessment

No gate is declared complete by this document. Current evidence places Gates 0
through 4 in partial progress: their implementation foundations exist, but their
exit conditions still require governance, independent reproduction, provider,
or operational proof. Gates 5 and 6 are not met. Gate 7 supplies useful practices
now but cannot be evidenced as routine continuous evolution before supported
releases exist.

## Gate 0 — Foundation Is Authoritative

### Outcome

The repository contains a coherent engineering source of truth that gives contributors the same understanding of product identity, system boundaries, requirements, architecture, domain language, module rules, integrations, security, coding practices, agent behavior, and decision governance.

### Required evidence

- Foundation documents use consistent terminology and have named scopes and responsibilities.
- The modular-monolith decision is accepted through ADR-0001 and linked from architecture guidance.
- Requirements have stable identifiers and a defined evidence model.
- Repository and AI-agent rules protect the read-first, approval, boundary, security, and review expectations.
- The ADR process defines how decisions are proposed, accepted, superseded, and retained.
- Review confirms that no foundation document treats OwnSIS as an OpenSIS fork or migration.
- Review confirms OwnID as the only identity provider, Moodle as the learning platform, and OwnSIS as the academic and administrative system of record.

### Exit condition

A new contributor can explain the platform boundary and evaluate a proposed technical direction using only versioned repository material. Material contradictions among foundation documents have been resolved.

## Gate 1 — Engineering System Is Reproducible

### Outcome

The project has a minimal, production-shaped engineering system in which backend, frontend, database evolution, containers, and automated verification can change safely without yet carrying unvalidated business behavior.

### Required evidence

- Supported Python 3.14, FastAPI, Next.js, TypeScript, PostgreSQL, `uv`, Alembic, and Docker workflows are reproducible from a clean checkout.
- Build artifacts identify their source and dependency state and do not contain development secrets.
- Formatting, linting, type checking, testing, dependency review, secret detection, and container checks run consistently in the contribution workflow.
- Configuration is explicit, validated, environment-independent at build time, and safe by default.
- Database migration verification exercises supported upgrade paths and a risk-appropriate recovery procedure.
- Runtime health, readiness, structured logging, correlation, and safe error handling have a documented baseline.
- Architecture fitness checks can enforce module dependency and layering rules as modules appear.

### Exit condition

Two independent contributors can produce equivalent verified artifacts and execute documented validation workflows without private setup knowledge.

## Gate 2 — Tenant and Identity Trust Boundary Is Proven

### Outcome

The platform can establish who is acting, for which organization, and under which OwnSIS authorization context. Tenant isolation is demonstrated as a platform property before broad domain delivery begins.

### Required evidence

- OwnID is the sole human authentication path, and invalid, expired, revoked, incorrectly targeted, or untrusted assertions fail closed.
- OwnSIS organization membership and permission evaluation remain distinct from authentication.
- Trusted tenant context propagates across interactive, background, event, cache, observability, and administrative boundaries.
- Organization-scoped branding, domain configuration, users, permissions, integrations, and subscription context have explicit ownership boundaries without implementing their future business workflows prematurely.
- Automated negative tests attempt cross-tenant access through every available execution path.
- Privileged support or platform operations use separate authorization and produce attributable audit evidence.
- Threat models cover identity establishment, tenant resolution, privilege change, organization lifecycle, and credential handling.

### Exit condition

Reviewers can trace any representative operation from OwnID assertion through tenant and permission evaluation, and the verification suite proves denial when any required context is absent, inconsistent, or belongs to another organization.

## Gate 3 — Modular Domain Delivery Is Repeatable

### Outcome

The modular monolith supports delivery of coherent domain capabilities without cross-module storage access, shared mutable models, or framework concerns defining domain meaning.

### Required evidence

- A repeatable module template defines ownership, public application capabilities, domain isolation, persistence isolation, tests, documentation, and operational signals.
- Bounded contexts and ubiquitous language are captured through domain discovery before implementation.
- Automated checks reject forbidden dependencies and access to another module's private persistence.
- Direct module collaboration and event-driven collaboration have clear selection criteria and testing patterns.
- Reliable event publication and consumption demonstrate correlation, tenant context, compatibility, duplication handling, retry bounds, terminal failure, and recovery.
- Transaction boundaries and cross-module consistency expectations are explicit and verified.
- A representative vertical capability passes the full requirements evidence model from user boundary through domain behavior, persistence, audit, and operations.

### Exit condition

A second independent vertical capability can follow the established path without copying internals from the first, expanding shared code with domain behavior, or bypassing module contracts.

## Gate 4 — External Boundaries Are Governed

### Outcome

OwnID, Moodle, and MCP interactions are replaceable, tenant-aware, observable adapters whose failures cannot silently redefine or corrupt the OwnSIS domain.

### Required evidence

- Each integration has a named owner, authority matrix, supported compatibility policy, tenant configuration model, security model, and operational runbook.
- Moodle exchanges preserve Moodle's learning boundary and OwnSIS ownership of academic and administrative information.
- Synchronization behavior demonstrates validation, bounded retries, deduplication where required, conflict handling, reconciliation, and recovery from extended unavailability.
- MCP exposes bounded application capabilities rather than unrestricted internal access.
- AI-assisted actions use the initiating identity and tenant context, pass ordinary authorization and domain validation, and produce proportionate audit evidence.
- Consequential AI actions are separated from read-only analysis and invoke human approval according to risk policy.
- Contract and failure-path tests run against supported external-system versions or faithful controlled substitutes.
- Disabling an integration leaves the authoritative OwnSIS state valid and the operational impact visible.

### Exit condition

The platform can demonstrate normal operation, dependency failure, replay or retry, reconciliation, and safe disablement for each foundational integration without cross-tenant leakage or ambiguous data authority.

## Gate 5 — Production Operation Is Defensible

### Outcome

The platform is deployable for controlled institutional use with explicit service objectives, monitored risks, exercised recovery, and a support model that does not depend on direct database manipulation.

### Required evidence

- Service objectives and capacity thresholds are based on documented user needs and representative workloads.
- Load, concurrency, and failure testing demonstrate that one organization's workload is bounded and that shared-resource pressure remains observable.
- Backup restoration, failed-migration recovery, integration-backlog recovery, and credential-compromise procedures have been exercised and recorded.
- Security review covers application, dependency, image, configuration, infrastructure, and operational access risks.
- Privacy, retention, export, correction, and erasure mechanisms can enforce an organization's applicable policy while preserving required record integrity.
- Accessibility and localization verification cover supported user-facing paths.
- Operational dashboards and alerts distinguish user impact, integration impact, and tenant-scoped impact without leaking protected data.
- Release, rollback, support, incident response, and security update procedures have clear ownership and evidence trails.

### Exit condition

An operations team can deploy, observe, diagnose, recover, and update a release using maintained procedures, and an independent readiness review finds no unresolved critical risk against the stated production scope.

## Gate 6 — Enterprise Open-Source Release Is Sustainable

### Outcome

The project can accept external use and contribution without relying on private knowledge, inconsistent quality gates, or unclear stewardship.

### Required evidence

- The supported-version, compatibility, deprecation, release, and security-reporting policies are published and exercised.
- Contribution and review workflows apply the same engineering gates regardless of contributor affiliation.
- Module ownership, decision authority, escalation paths, and maintainer responsibilities are discoverable.
- Third-party dependencies and assets have recorded provenance and compatible licensing.
- Installation, upgrade, configuration, backup, recovery, integration, and troubleshooting documentation is verified against a clean supported environment.
- Release artifacts are reproducible, traceable, scanned, and accompanied by accurate change and migration information.
- A feedback path converts operational evidence and domain learning into requirements, ADRs, roadmap decisions, and deprecation plans.

### Exit condition

An organization outside the core team can evaluate, deploy, operate, upgrade, and contribute to OwnSIS using public artifacts and established governance.

## Gate 7 — Continuous Evolution Is Routine

### Outcome

Long-term change is managed as a normal platform capability. Modules, contracts, data, dependencies, and operational practices can evolve without recurring rewrites or uncontrolled compatibility burden.

### Required evidence

- Architecture fitness measures identify erosion in module boundaries, dependency direction, tenancy enforcement, and contract ownership.
- Migration telemetry and upgrade exercises cover the maintained version window.
- Deprecations have usage evidence, migration guidance, support windows, and verified removal conditions.
- Operational reviews feed measured reliability, performance, security, and support findings into prioritized engineering work.
- Module extraction criteria are measurable, and no extraction proceeds without evidence and an accepted ADR.
- Framework and dependency upgrades are rehearsed as incremental maintenance rather than accumulated into platform-wide replacement projects.
- Documentation is reviewed with each material change and periodically checked for stale or contradictory guidance.

### Exit condition

The project demonstrates multiple compatible capability and platform evolutions while preserving tenant isolation, data integrity, operability, and contributor comprehension.

## Repeatable Capability Lifecycle

After Gate 2 establishes the trust boundary and Gate 3 establishes the module path, every domain capability follows the same outcome sequence:

1. **Discover:** establish domain language, actors, ownership, invariants, tenant behavior, data sensitivity, and external authority from validated stakeholder evidence.
2. **Specify:** record capability requirements, negative cases, quality constraints, and traceability to platform requirements without prescribing unvalidated interfaces or storage.
3. **Design:** identify the owning bounded context, allowed dependencies, consistency needs, integration boundaries, threat model, and operational signals.
4. **Deliver:** implement a coherent vertical slice with tests and documentation at each relevant boundary.
5. **Prove:** demonstrate security, tenancy, accessibility, migration, failure, recovery, and operational evidence proportionate to risk.
6. **Operate:** measure outcomes and service behavior, investigate deviations, and feed evidence back into the domain and platform record.
7. **Evolve:** change contracts and stored information through compatible transitions, explicit deprecation, and recorded decisions.

This lifecycle prevents the roadmap from becoming a list of disconnected features while allowing multiple modules to progress independently once their dependencies are proven.

## Sequencing Constraints

- Domain delivery may explore concepts during Gate 0 and Gate 1, but production domain behavior does not bypass the proven tenant and identity boundary.
- Integration adapters may be prototyped before Gate 3, but no prototype establishes a domain contract or production authority boundary without review.
- Production pilots require Gate 5 evidence for their declared scope; reduced feature scope does not justify reduced isolation, security, or recovery controls.
- Public release requires Gate 6 even if controlled deployments already operate successfully.
- Gate 7 begins as soon as the first supported artifact exists and becomes the standing mode after the first public release.

## Risks and Controls

| Risk | Roadmap control |
| --- | --- |
| Premature domain implementation | Gate 0 authority and the discover/specify lifecycle require validated language and ownership first. |
| Modular monolith degrades into a coupled codebase | Gate 1 fitness checks and Gate 3 dependency evidence enforce module boundaries continuously. |
| Tenant isolation is retrofitted | Gate 2 proves tenant propagation and negative paths before broad capability delivery. |
| Identity and authorization become conflated | Gate 2 separately verifies OwnID authentication and OwnSIS organization authorization. |
| Events hide inconsistent behavior | Gate 3 requires explicit consistency, reliability, and recovery evidence. |
| External systems redefine ERP records | Gate 4 requires authority matrices, translation boundaries, and reconciliation. |
| AI bypasses application controls | Gate 4 limits MCP to authorized application capabilities with validation and audit. |
| Production readiness is inferred from feature completion | Gate 5 requires measured service and exercised recovery evidence. |
| Open-source operation relies on core-team knowledge | Gate 6 requires independent deployment and contribution from public artifacts. |
| Fifteen-year ambition causes speculative abstraction | Every gate requires present evidence; extraction and generalization have explicit criteria. |

## Responsibilities

This roadmap is responsible for sequencing platform outcomes and defining the evidence needed to advance. It does not replace capability requirements, delivery plans, release notes, or operational runbooks.

- Project maintainers own gate definitions and ensure advancement reflects evidence rather than schedule pressure.
- Architecture maintainers validate dependency, domain-boundary, integration, and evolution evidence.
- Security maintainers validate trust-boundary, threat, privacy, and recovery evidence.
- Domain and product owners validate that capability discovery reflects institutional needs without prematurely prescribing implementation.
- Module owners supply traceability and proof for the capabilities they deliver.
- Operators validate service objectives, failure behavior, recovery, and support readiness.
- Reviewers record gate decisions and unresolved risks in repository-governed artifacts.

## Assumptions

- Roadmap funding and contributor capacity may vary, so sequence must remain useful without calendar commitments.
- Platform and domain discovery can overlap when unproven assumptions do not enter production contracts.
- OwnID, Moodle, and MCP integrations can be exercised in controlled environments before production use.
- Representative organizations will participate in domain validation and operational readiness review.
- Deployment-specific service objectives will be derived from measured needs rather than treated as universal constants.
- The modular monolith remains the default architecture throughout the roadmap unless extraction criteria are demonstrated.
- Each gate can produce evidence incrementally while preserving a coherent main branch and documentation set.

## Future Evolution

The roadmap will be revised when evidence changes dependencies, risk, or the cost of a gate. Reordering may occur only when the new sequence preserves all prerequisite outcomes and is documented with its rationale. Dates and release packaging may be maintained in delivery planning, but they do not weaken gate criteria.

As the platform matures, Gate 7 becomes the continuing roadmap: capability discovery, compatible evolution, measured operation, security response, dependency renewal, and selective module extraction repeat throughout the product lifetime. New institution types, regions, delivery channels, integrations, or AI capabilities enter through the repeatable capability lifecycle and the same tenant, authority, security, and operability gates.
