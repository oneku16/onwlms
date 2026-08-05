# OwnSIS Security Foundation

## Purpose

This document defines the security principles, trust boundaries, baseline controls, and review expectations for OwnSIS. Its primary objective is to protect each organization from unauthorized access, cross-tenant disclosure, integrity loss, and unaccountable change while preserving a platform that can evolve safely for at least fifteen years.

## Scope

This document applies to the Next.js application, FastAPI backend, PostgreSQL, background work, events, Docker runtime, software supply chain, OwnID, Moodle, MCP-enabled AI, other integrations, administrative operations, and development lifecycle.

It establishes control requirements but does not define endpoint-specific permissions, database schemas, organization-specific retention schedules, incident contacts, or jurisdiction-specific legal conclusions. Capability threat models and operating procedures refine this baseline without weakening it.

## Responsibilities

Security is a shared engineering responsibility with explicit accountability:

- maintainers preserve secure defaults, tenant isolation, supported dependencies, and review evidence;
- module owners define resource authorization, data classification, audit events, retention behavior, and abuse limits for their capabilities;
- the OwnID integration owner maintains identity-verification correctness and key lifecycle handling;
- integration owners protect credentials, minimize disclosure, and operate failure and revocation paths;
- operators enforce least privilege, separation of duties, backup protection, and incident readiness;
- reviewers challenge trust assumptions and verify controls through evidence rather than intent;
- contributors keep suspected vulnerability details out of public issues, commits, and discussions and use the project's confidential reporting channel once that channel is published.

No role may assume that another layer will compensate for a missing control.

At the foundation stage, OwnSIS does not claim that a confidential vulnerability-reporting channel already exists. Until maintainers publish one, a reporter should request private contact without including exploit details in the public request. A concrete confidential channel, response ownership, and disclosure policy are release prerequisites under Gate 6 of the [engineering roadmap](10_ROADMAP.md).

## Security Principles

### Deny by default

Access is denied unless a trusted identity, tenant context, permission, resource relationship, and current policy explicitly allow it. Missing, stale, ambiguous, or conflicting context fails closed.

### Defense in depth

Authentication, application authorization, tenant-scoped repositories, PostgreSQL enforcement, runtime isolation, and audit evidence are independent controls. User-interface hiding and client validation are never security boundaries.

### Least privilege and separation of duties

Human users, services, workers, integrations, database roles, CI jobs, and MCP tools receive only the capabilities and duration required. High-impact administrative actions require stronger assurance, independent approval, or both according to risk.

### Explicit trust boundaries

Browser input, events, integration payloads, uploaded files, model output, and data returned by external providers are untrusted. Internal network location is not proof of identity or authorization.

### Minimize and contain

OwnSIS collects, processes, logs, and exports only data necessary for an approved purpose. Sensitive operations are reversible where practical and constrained by tenant, actor, time, and resource.

### Auditable change

Security-relevant and authoritative changes produce durable evidence linking actor, tenant, action, target, policy decision, time, origin, and correlation. Audit does not replace prevention.

## Security Model and Trust Boundaries

The principal trust boundaries are:

- the user's browser and the public web edge;
- the Next.js runtime and FastAPI application boundary;
- module application contracts and background work;
- PostgreSQL and derived stores;
- OwnID as the sole identity provider;
- Moodle and all other external providers;
- MCP servers, models, tool clients, and model-supplied content;
- operator, support, CI/CD, and deployment control planes.

Data is revalidated when it crosses a boundary. A successful check at one boundary is not indefinitely transferable to another operation.

The threat model includes account compromise, privilege escalation, insecure direct object access, cross-tenant data leakage, injection, request forgery, malicious files, credential theft, dependency compromise, event tampering or replay, administrative abuse, data exfiltration through logs or AI context, denial of service, destructive error, and compromised external providers.

## Tenant Isolation

Tenant isolation is the highest-order security invariant. An organization must not observe, influence, infer, or consume another organization's data or capacity beyond explicitly public information.

Tenant context is resolved from trusted routing and verified OwnID identity context, then bound to an active OwnSIS tenant relationship. A hostname, request parameter, header, object identifier, or token claim alone is insufficient when it conflicts with the established relationship.

Isolation applies to:

- application commands and queries;
- authorization resources and policies;
- PostgreSQL access and migrations;
- caches, search indexes, files, exports, and backups;
- events, queues, retries, scheduled work, and quarantine;
- integration configuration, credentials, mappings, and rate limits;
- logs, traces, metrics, support tools, and analytics;
- MCP context, tool permissions, and model conversations.

Repositories are tenant-scoped by construction. PostgreSQL-enforced controls, normally row-level security or an equivalently strong mechanism, backstop application checks. Database roles used by ordinary application paths cannot casually bypass those controls. Platform-global access uses distinct capabilities, credentials, and audit paths.

Automated tests use at least two tenants and attempt cross-tenant reads, writes, references, event handling, cache collisions, exports, and privileged operations. Any cross-tenant exposure is treated as a security incident, not a routine defect.

## Authentication

OwnID is the only identity provider. OwnSIS does not store human passwords, authenticate local human credentials, or introduce a fallback provider. Identity assertions are accepted only after validating signature, trusted issuer, intended audience, validity window, key status, and relevant authentication assurance.

Key rotation and temporary verification failure fail safely without extending trust to unverifiable tokens. Subject identifiers are treated as opaque external references. Authentication state is not a substitute for tenant membership or permission.

Browser sessions use secure, HTTP-only, appropriately scoped cookies when cookies are part of the selected flow. Session material is protected from fixation, cross-site request forgery, leakage through URLs, and unintended cross-domain sharing. Logout, revocation-sensitive actions, and membership removal have defined effects even when an identity-provider session remains valid.

Service and integration identities are distinct from human identities. They may be authenticated only through explicitly approved workload mechanisms that identify non-human principals; those mechanisms are not identity providers, user-account systems, or fallback paths around OwnID. Shared credentials and long-lived unrestricted tokens are prohibited.

## Authorization

OwnSIS owns authorization. Every protected operation is authorized on the server against:

- the verified actor or service identity;
- the resolved tenant relationship;
- the requested capability and action;
- the specific resource and its tenant ownership;
- current permission, policy, entitlement, and security state;
- any required authentication assurance or approval.

Permissions and subscription entitlements are separate. An entitled feature does not grant a person access; a permission cannot activate a feature unavailable to the organization.

Authorization is performed at the application use-case boundary and reinforced within sensitive domain behavior. Background tasks and event consumers operate under a declared service authority and cannot inherit a user's authority indefinitely. Bulk, export, impersonation, configuration, credential, and support actions receive explicit policies rather than generic administrator bypass.

Emergency or support access is time-bounded, reason-bound, strongly authenticated, separately authorized, visible to audit, and reviewable. Silent impersonation and unrecorded database access are prohibited.

## Data Protection and Privacy

Each module classifies the data it owns and documents permitted purposes, disclosure, retention, correction, deletion, and recovery behavior. Educational, identity, contact, financial, authentication, and security data receive protection proportional to impact.

Data is encrypted in transit across trust boundaries and at rest in managed storage and backups. Encryption keys are separated from encrypted data, access-controlled, rotated, and recoverable through an approved process. Passwords and OwnID credentials are outside OwnSIS ownership; secrets that OwnSIS must hold use a dedicated secrets facility.

Logs, traces, metrics, events, error responses, analytics, and test fixtures minimize personal and confidential data. Production data is not copied into development or demonstrations without an approved, auditable de-identification process. Exports are authorized, time-limited, integrity-protected, and traceable.

Retention and deletion operate across source records, projections, files, integration copies under OwnSIS control, and backups according to documented policy. Deletion is not claimed complete where legal or recovery retention still applies; access and eventual expiry remain controlled.

## Application Security

FastAPI validates all external input at the transport boundary and the owning domain validates semantic rules. Queries and persistence operations use safe parameterization. Errors expose stable, non-sensitive meaning and do not reveal stack traces, credentials, SQL, tenant existence, or authorization internals.

The Next.js application treats rendered content and URLs as untrusted. Output encoding, content security policy, safe navigation, dependency controls, and avoidance of dangerous dynamic execution reduce cross-site scripting. State-changing browser operations include cross-site request forgery protection appropriate to their authentication mechanism.

Outbound network access is restricted to approved destinations and protocols. Redirects, remote content retrieval, webhook destinations, and file processing are designed against server-side request forgery. Uploads are size-limited, type-validated by content, stored outside executable paths, malware-assessed according to risk, and served with safe disposition.

Rate limits, quotas, pagination, request size limits, concurrency controls, and bounded work protect shared capacity. Limits are tenant-aware so one organization cannot exhaust the platform for others. Security controls themselves avoid becoming an oracle that reveals another tenant's existence.

## Database, Events, and Background Work

PostgreSQL access uses separate least-privilege roles for application runtime, migrations, operations, and read-only analysis. Migrations are reviewed for tenant scope, locking, data exposure, and rollback or forward-recovery behavior. Direct production data changes are exceptional, approved, scripted through a controlled mechanism, and audited.

Events and work items carry immutable tenant, origin, contract version, and correlation context. Producers authenticate to transport, and consumers validate origin and shape before processing. Duplicate delivery and replay are expected; authorization and idempotency prevent duplicate or stale messages from creating broader authority.

Quarantine and replay tooling applies the same tenant and permission boundaries as normal processing. An operator cannot edit a payload to bypass domain validation. Sensitive payloads are encrypted or referenced through controlled storage when transport-level protection is insufficient.

## Integration Security

Each organization's integration credentials are isolated, least-privileged, encrypted, rotated, and revocable. Credential material never appears in repository history, images, client bundles, logs, events, or error messages.

Incoming integration traffic is authenticated, integrity-checked, and protected against replay where supported. Outgoing requests use verified transport security, controlled destinations, bounded timeouts, and safe redirect behavior. Provider failure or compromise cannot redefine OwnSIS authority.

Moodle receives only the institutional data required for learning delivery. Moodle-originated information is untrusted external evidence until accepted by OwnSIS policy. OwnID assertions are verified but do not grant tenant authorization by themselves.

## MCP and AI Security

AI models and their output are treated as untrusted. MCP tools expose narrow application capabilities rather than databases, generic code execution, or ambient network access. Every invocation binds tenant, actor or service identity, declared purpose, permission, input classification, and correlation.

Prompt injection and malicious tool output are expected. External content cannot redefine system instructions, expand tool scope, retrieve secrets, or authorize follow-on actions. Retrieved context is minimized and isolated by tenant before it reaches the model.

Write operations are distinct from reads and pass through standard validation and authorization. Material academic, administrative, financial, privacy, security, deletion, bulk, or external-communication effects require explicit human confirmation or an independently approved automation policy. Generated recommendations retain provenance and are never represented as verified institutional facts without domain acceptance.

Model and tool activity is audited without retaining unnecessary private prompts or outputs. Provider training, retention, region, and subprocessors are evaluated before sensitive data is enabled.

## Secrets and Cryptographic Material

Secrets are supplied at runtime from an approved secrets manager and scoped by environment, service role, tenant where applicable, and purpose. Rotation is possible without source change. Development credentials cannot access production.

Cryptographic algorithms and libraries follow current, widely reviewed guidance. The platform does not invent cryptographic protocols. Key purpose is explicit; signing, encryption, and authentication keys are not interchangeable. Key compromise has a documented containment, rotation, and revalidation path.

## Software Supply Chain and Runtime

Python dependencies are resolved reproducibly with `uv`; frontend dependencies are locked. Dependency provenance, licenses, known vulnerabilities, and update posture are reviewed. Automated findings are triaged by exploitability and data impact, not ignored or accepted solely by age.

Docker builds are reproducible, minimal, immutable, and non-root. Build and runtime stages are separated. Images are scanned, signed or otherwise provenance-attested by the delivery environment, and promoted rather than rebuilt between environments.

CI credentials are short-lived and least-privileged. Protected branches, required review, verified checks, and artifact provenance protect releases. Untrusted contribution workflows cannot access repository, deployment, signing, or production secrets.

## Audit, Monitoring, and Incident Response

Audit evidence is append-oriented and protected from ordinary application mutation. It records security decisions and authoritative changes with actor, tenant, action, target reference, time, origin, outcome, reason where required, and correlation. It excludes credentials and unnecessary record contents.

Monitoring detects unusual authorization denials, support access, tenant-context failures, credential misuse, bulk access, export activity, integration anomalies, queue replay, and changes to security configuration. Alerts are actionable and preserve tenant privacy.

Incident response prioritizes containment, evidence preservation, tenant impact analysis, credential revocation, safe recovery, and required communication. Backups are encrypted, access-controlled, integrity-tested, and restored regularly in an isolated exercise. Recovery proves both availability and tenant isolation.

## Secure Engineering and Review

Every material capability receives a threat assessment proportional to its data and authority. Security-sensitive changes require reviewers with relevant expertise. Review examines tenant context, authorization coverage, input and output handling, data minimization, event/replay behavior, integration trust, audit evidence, operational access, and failure modes.

Automated checks include dependency and image scanning, static analysis, secret detection, architecture enforcement, migration review gates, and tenant-isolation tests. Penetration testing and focused abuse-case review are performed before high-impact capabilities or trust-boundary changes are released.

Vulnerabilities are tracked privately with severity, exposure, owner, remediation evidence, and coordinated disclosure. A security exception is time-bounded, risk-accepted by an accountable owner, monitored, and removed when its stated condition expires.

## Assumptions

- OwnID provides trustworthy, verifiable identity assertions and supports secure key rotation and revocation-related operations.
- OwnSIS remains responsible for authorization even when authentication succeeds at OwnID.
- All organizations require strict logical isolation; some may later require dedicated infrastructure or regional placement.
- PostgreSQL and the deployment platform provide mature encryption, access control, backup, and audit capabilities when configured correctly.
- External systems, browsers, networks, AI models, and integration payloads may be compromised or malicious.
- Regulatory and contractual obligations differ among tenants and will be applied through explicit data-governance policy.
- Exactly-once delivery is not assumed, and stale, duplicated, or reordered work must not weaken security.
- Maintainers can suspend risky integrations or capabilities when safe operation cannot be demonstrated.

## Future Evolution

Security controls will evolve through threat intelligence, incident learning, dependency changes, platform capabilities, and the regulatory environments of supported institutions. Periodic architecture review will reassess trust boundaries and verify that written controls match deployed behavior.

Tenant isolation may evolve from shared infrastructure with database enforcement to deployment cells, dedicated databases, regional storage, or dedicated installations. Such changes add containment but do not replace application authorization or audit.

Authorization may gain richer policy evaluation and stronger assurance signals while preserving deny-by-default behavior and explainable decisions. Cryptography, authentication standards, browser protections, and supply-chain attestation will be upgraded before existing choices become unsafe, using staged compatibility and recovery plans.

MCP and AI capabilities will expand only alongside evaluation for prompt injection, data leakage, harmful automation, and provenance. Tool scopes, human approval, and audit requirements will remain stricter than the convenience of model-driven execution. Any move toward greater automation requires measurable safety, revocability, and a documented security decision.
