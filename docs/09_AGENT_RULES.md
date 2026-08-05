# AI Agent Operating Rules

## Purpose

This document provides the day-to-day operating protocol for AI-assisted work on OwnSIS. It complements the mandatory repository rules in the root `AGENTS.md` by describing how an agent should orient, execute, verify, and hand off work.

## Scope

These rules apply to analysis, documentation, implementation, review, testing, repository maintenance, and external-tool use performed by an AI agent. They do not grant permission to modify the repository. Write authority must come from an explicit user request, and external side effects require authorization appropriate to their impact.

System instructions and direct human instructions take precedence over repository documentation. Within repository documentation, the root `AGENTS.md` governs agent behavior; a closer `AGENTS.md` may add local constraints. If instructions conflict or their precedence is unclear, the agent must stop and surface the conflict.

## Responsibilities

Agents must keep human maintainers in control while reducing the cost of well-scoped engineering work. They are responsible for evidence-based analysis, narrow changes, transparent assumptions, appropriate verification, and complete handoff. They must preserve architectural boundaries and must not manufacture product decisions to unblock themselves.

## Operating Protocol

### 1. Orient

Before proposing or changing anything, inspect:

- the user's exact request and acceptance criteria;
- the root and nearest applicable agent instructions;
- relevant project, architecture, domain, integration, security, and coding documents, including [`13_BACKEND_ENGINEERING_GUIDE.md`](13_BACKEND_ENGINEERING_GUIDE.md) before Python backend changes;
- accepted ADRs that govern the affected area;
- nearby source and tests for established patterns;
- current working-tree changes that could overlap the task.

Use repository evidence as the source of truth. Do not infer the current state from common framework conventions or from previous projects.

### 2. Bound the Work

State or internally establish the smallest coherent scope that achieves the requested outcome. Separate required work from attractive cleanup. Identify material assumptions early and distinguish reversible implementation detail from decisions that require human ownership.

If the request is an inspection, explanation, diagnosis, or review, remain read-only unless the user separately authorizes changes.

### 3. Plan Proportionally

Use a short plan when work crosses multiple files, boundaries, or verification stages. The plan must identify architecture or security-sensitive steps and expected checks. Simple, isolated tasks do not require ceremonial planning.

Parallel work is acceptable only when subtasks are independent, file ownership is clear, and results will receive a single integrative review. Delegation never transfers responsibility for correctness or instruction compliance.

### 4. Act Conservatively

Make focused changes using established repository patterns and tooling. Preserve unrelated edits. Avoid opportunistic refactors, dependency additions, broad formatting, generated churn, and speculative extensibility.

When new evidence invalidates the plan, pause, reassess scope, and communicate any material change. Do not force the original plan through conflicting repository facts.

### 5. Verify

Verification must match the risk and type of change. It can include inspecting the final diff, documentation consistency checks, formatting, static analysis, focused tests, broader regression tests, build checks, migration review, or security review. Never report a command, test, or outcome that was not actually observed.

A pre-existing failure must be distinguished from a change-induced failure with evidence. Repairing an unrelated failure requires separate authorization.

### 6. Hand Off

The final report must identify:

- the outcome achieved;
- the files or systems changed;
- the checks performed and their results;
- assumptions or decisions applied;
- remaining risks, limitations, or checks not run.

The report should be concise but must not hide uncertainty or omit a material failure.

## Architecture and Domain Guardrails

Agents must actively protect these constraints during all work:

- OwnSIS is a modular monolith governed by DDD boundaries and event-driven collaboration.
- Modules own their domain model, application behavior, and persistence representation.
- Cross-module use occurs through explicit public contracts; internal imports and direct persistence access are not shortcuts.
- Domain behavior is framework-independent and uses validated ubiquitous language.
- Tenant isolation applies to data access, authorization, caching, events, logs, jobs, integrations, and administrative operations.
- OwnID is the sole identity provider; OwnSIS remains responsible for authorization over OwnSIS resources.
- Moodle is restricted to learning responsibilities and cannot become authoritative for OwnSIS academic or administrative data.
- MCP-based AI functionality remains an untrusted, permission-aware integration and cannot bypass application rules.
- OpenSIS implementation details do not establish OwnSIS requirements.

An agent must not invent a missing domain rule, aggregate boundary, event contract, public API, permission model, or database structure. It may identify the missing decision and present evidence-backed options for a human to resolve.

## Evidence and Communication Rules

- Cite concrete repository paths, configuration, tests, or observed tool output when making claims about the current system.
- Label an inference as an inference and explain the evidence supporting it.
- Communicate a blocker as soon as it becomes material; do not conceal it behind partial completion.
- Use precise language about risk. Distinguish possible impact from observed failure.
- Do not expose secrets, credentials, personal data, or sensitive payloads in prompts, logs, reports, fixtures, or generated documentation.
- Do not use AI-generated material as authority for domain, legal, privacy, accessibility, or security decisions.

## Approval Boundaries

Agents may perform relevant read-only inspection within the user's stated scope. They must obtain explicit approval before:

- creating, editing, moving, renaming, or deleting files when the user did not request repository changes;
- broadening the task to unrelated cleanup or remediation;
- discarding or overwriting existing work;
- adding, removing, or upgrading dependencies;
- defining or changing architecture, public contracts, schemas, migrations, domain behavior, identity, permissions, or tenant isolation;
- introducing infrastructure, services, datastores, brokers, scheduled work, or external integrations;
- executing destructive, irreversible, production, deployment, release, publish, or third-party communication actions;
- using credentials, accessing sensitive data beyond the requested need, or accepting a security/privacy tradeoff;
- resolving an instruction or design conflict that would materially change the outcome.

Approval must be informed: describe the exact action, why it is needed, the affected scope, the principal risk, and the safer alternatives when they exist.

## Review Behavior

When asked to review, prioritize concrete defects and risks over stylistic preference. Each finding should identify the affected location, triggering conditions, impact, and the governing expectation. Do not claim a defect without a plausible execution path or violated requirement.

Review order is:

1. tenant isolation, authorization, confidentiality, and integrity;
2. correctness of domain behavior and transactions;
3. module ownership and dependency direction;
4. failure handling, concurrency, retries, and idempotency;
5. migration and compatibility safety;
6. observability and operational behavior;
7. test sufficiency and maintainability.

If no actionable findings are discovered, say so and identify the inspection or verification limits. Absence of findings is not a guarantee of correctness.

## Prohibited Agent Patterns

- Generating a large implementation before inspecting the repository.
- Treating passing tests as proof that architecture and security requirements are satisfied.
- Copying legacy code or inferred legacy behavior into the greenfield design.
- Creating generalized abstractions, compatibility layers, or extension points without demonstrated consumers.
- Silently relaxing typing, validation, authorization, tenancy, or error handling to make a check pass.
- Editing generated artifacts manually when a governed generation workflow exists.
- Performing drive-by formatting or refactoring outside the task.
- Presenting placeholders, stubs, or unverified output as completed work.

## Assumptions

- Human maintainers own product intent and approve material architecture, domain, security, and operational decisions.
- Agents have enough read access to inspect the evidence required for a scoped task; lack of necessary evidence is a reason to ask, not to guess.
- The repository will add more local agent instructions as modules and workflows mature.
- Automated checks support but do not replace agent self-review and human review.

## Future Evolution

These operating rules will be refined as CI, module ownership, release controls, data governance, and automated agent checks become concrete. Future revisions may encode risk tiers and required verification matrices. They must remain consistent with the root `AGENTS.md`, preserve explicit human authorization, and be reviewed as governance changes rather than ordinary editorial cleanup.
