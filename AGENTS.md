# Instructions for AI Agents

## Purpose

This file defines mandatory operating rules for AI agents working in the OwnSIS repository. Its goal is to keep agent-assisted work safe, reviewable, architecturally consistent, and under explicit human control.

## Scope

These rules apply to every agent action in this repository, including inspection, analysis, documentation, source changes, tests, dependency operations, generated artifacts, version-control actions, and external integrations. More specific instructions may add constraints for a subdirectory, but they must not weaken this file. System instructions and explicit user directions take precedence.

## Responsibilities

An agent is responsible for:

- understanding the requested outcome and the limits of the authorization granted;
- reading the relevant project documentation, accepted ADRs, and local instructions before acting;
- preserving tenant isolation, domain boundaries, identity boundaries, and data ownership;
- making the smallest coherent change that satisfies the request;
- protecting unrelated work already present in the working tree;
- verifying changes in proportion to their risk;
- reporting changed files, verification performed, assumptions made, and unresolved risks;
- stopping when proceeding would require authority or a material decision the user has not supplied.

Agents advise and implement within scope; they do not silently become product owners, domain experts, security approvers, or architecture decision makers.

## Repository Rules

1. **Read by default.** Do not edit, create, rename, move, or delete files unless the user explicitly requested a change. If a requested outcome appears to require unapproved changes, stop and ask first.
2. **Respect scope.** Modify only files necessary for the requested outcome. Do not clean up, reformat, or reorganize unrelated content.
3. **Inspect before changing.** Check repository instructions, relevant documents, accepted ADRs, nearby conventions, and current working-tree state.
4. **Preserve user work.** Treat pre-existing modifications and untracked files as user-owned. Never discard or overwrite them to simplify an agent task.
5. **Use repository workflows.** Follow the configured package, migration, test, formatting, and build processes. Do not introduce parallel tooling without approval.
6. **Keep source and governance aligned.** A change that affects architecture, security, behavior, operations, or contributor expectations must update the governing documentation in the same change when that update is within the authorized scope.
7. **Record durable decisions.** Material architecture changes require an ADR. An implementation patch must not smuggle in an unrecorded architecture decision.
8. **Do not infer legacy compatibility.** OpenSIS code, APIs, schemas, naming, and behavior are not OwnSIS requirements.

## Architecture Rules

- OwnSIS is a Domain-Driven Design modular monolith. The core backend remains one deployable application until an accepted ADR authorizes another boundary.
- Modules must have explicit ownership and stable public boundaries. A module must not reach into another module's internal application, domain, or persistence details.
- Dependencies point inward: infrastructure depends on application and domain contracts; domain logic does not depend on delivery frameworks, persistence frameworks, or external vendors.
- Cross-module collaboration occurs through explicit contracts and events, not shared internals or incidental database access.
- Event-driven behavior must define ownership, delivery expectations, failure handling, idempotency requirements, and observability before implementation.
- PostgreSQL is shared infrastructure, not permission for an undifferentiated shared model. Logical ownership and transactional boundaries remain explicit.
- Tenant context is mandatory wherever tenant-owned data or behavior is involved. Tenant isolation cannot be added as a later filter or delegated only to the user interface.
- OwnID is the sole identity provider and the only authority for human authentication. OwnSIS owns authorization policy and resource permissions and may use explicitly approved non-human workload authentication, but it must not implement a second human credential store, user login path, or identity authority.
- Moodle owns learning delivery only. OwnSIS remains authoritative for academic and administrative data.
- AI integration uses MCP and must be permission-aware, auditable, bounded, and incapable of bypassing normal application rules.
- New service boundaries, datastores, brokers, frameworks, or platform-wide abstractions require explicit approval and architecture justification.

## Domain-Driven Design Rules

- Derive the domain model from validated OwnSIS requirements and domain discovery, never by copying legacy structures.
- Use one consistent term for one concept within a bounded context. When language differs between contexts, make the translation explicit.
- Keep invariants and domain decisions in the domain model. Do not distribute them across controllers, UI components, persistence callbacks, or integration adapters.
- Keep use-case orchestration in the application layer and external concerns in adapters or infrastructure.
- Treat aggregates as consistency boundaries, not object graphs or convenient containers.
- Reference concepts across aggregate or module boundaries by stable identity or explicit contract rather than mutable internal objects.
- Domain events describe facts that have occurred. Commands express requested intent. Do not use either as an untyped transport shortcut.
- Shared kernels must remain small, stable, and explicitly governed. Similar-looking domain concepts should not be merged merely to reduce duplication.
- Repositories represent domain persistence boundaries; they must not expose arbitrary storage queries into the domain model.
- Do not invent domain entities, workflows, invariants, APIs, or schemas when the source requirements are absent.

## Coding Philosophy

- Optimize first for correctness, readability, maintainability, and explicit intent.
- Prefer simple composition and visible control flow over metaprogramming, implicit registration, or clever compression.
- Use precise names and strong types. Avoid generic containers, ambiguous booleans, stringly typed concepts, and broad escape hatches.
- Keep units cohesive and interfaces narrow. Duplication is preferable to a premature abstraction that couples unrelated concepts.
- Make failure behavior explicit. Do not suppress exceptions, silently fall back, or convert operational failures into successful responses.
- Design for testability and observability without exposing internals solely for tests.
- Comments explain rationale, constraints, and non-obvious tradeoffs; they do not narrate syntax.
- Follow `docs/08_CODING_STANDARD.md` for language-independent and stack-specific standards.

## Forbidden Actions

Agents must not:

- modify files without explicit authorization;
- perform destructive version-control or filesystem operations unless the user explicitly requests the exact outcome and the target has been verified;
- erase, revert, or overwrite unrelated user changes;
- invent APIs, database schemas, domain rules, permissions, or compatibility behavior;
- introduce a microservice, cross-module data access, circular dependency, or hidden global coupling;
- create a human authentication path outside OwnID, present workload authentication as an alternative user login, or allow Moodle or an AI component to become authoritative for OwnSIS-owned data;
- bypass tenant scoping, authorization, validation, auditing, or application-layer rules;
- commit secrets, personal data, access tokens, private keys, production data, or sensitive values in logs and fixtures;
- add, remove, or upgrade dependencies solely for convenience or without reviewing security, licensing, maintenance, and architectural impact;
- execute network, deployment, release, migration, messaging, or other externally visible actions that were not requested;
- claim verification that was not performed or conceal a failed check;
- leave placeholders, silent stubs, or speculative abstractions presented as completed work.

## Working Behavior

Before making an authorized change, an agent must establish:

1. the requested deliverable and acceptance conditions;
2. the exact files and systems in scope;
3. the applicable documentation and accepted ADRs;
4. the state of related code and pre-existing local changes;
5. the verification appropriate to the risk.

During work, the agent must communicate material assumptions, scope changes, and blockers. It should favor reversible, incremental steps; keep diffs focused; and use evidence from the repository rather than memory when describing current behavior.

After work, the agent must inspect the resulting diff, run the relevant checks available within scope, and provide a concise handoff. If a check cannot be run, explain why and state what remains unverified.

## Review Process

Every change must be reviewable on its own merits. Agent self-review must cover:

- alignment with the user's request and absence of unrelated changes;
- compliance with architecture, DDD, security, and tenant-isolation rules;
- correctness of dependency direction and ownership boundaries;
- clear naming, typing, error behavior, and operational visibility;
- appropriate tests and verification for the changed behavior;
- documentation and ADR impact;
- migration, compatibility, and rollback implications where relevant;
- absence of secrets, sensitive data, generated noise, and unsupported claims.

Human review is required for architecture decisions, security-sensitive changes, identity and authorization behavior, tenant isolation, database migrations, public contracts, dependency changes, deployment behavior, and exceptions to repository standards.

## When to Stop and Ask for Approval

An agent must stop before acting when:

- the user has not explicitly authorized file or external-state changes;
- two reasonable interpretations would produce materially different behavior, data ownership, or architecture;
- the request conflicts with an accepted ADR, security rule, repository instruction, or existing contract;
- the work requires defining an absent business rule, permission policy, public API, database schema, migration behavior, or tenant model;
- the work would add or change a dependency, service, datastore, framework, external integration, deployment, or architecture boundary;
- the action is destructive, difficult to reverse, affects production or shared environments, or communicates with third parties;
- credentials, private data, legal or licensing judgment, or security acceptance is required;
- relevant user changes overlap the target and cannot be preserved safely;
- verification exposes a failure outside the authorized scope whose repair would require additional changes.

The approval request must identify the decision, the available evidence, the proposed action, and its impact. It must not disguise a material decision as a minor implementation detail.

## Assumptions

- Human maintainers retain final authority over product, domain, security, and architecture decisions.
- Repository documentation and accepted ADRs describe the intended state; existing code alone is not sufficient evidence that a pattern is approved.
- Multi-tenancy, OwnID exclusivity, Moodle's limited responsibility, and OwnSIS data ownership are non-negotiable platform constraints unless explicitly changed through governance.
- Agent output will be reviewed, and all significant claims must therefore be traceable to repository evidence or clearly identified assumptions.

## Future Evolution

These rules will evolve as the repository gains modules, build automation, security controls, release processes, and operational environments. Changes to this file require explicit human approval and should tighten or clarify governance without silently granting agents broader authority. Repeated exceptions should be resolved by improving standards, tooling, or ADRs rather than normalizing undocumented behavior.
