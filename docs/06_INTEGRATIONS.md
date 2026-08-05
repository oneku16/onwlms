# OwnSIS Integration Architecture

## Purpose

This document defines how OwnSIS exchanges data and actions with systems outside its authority. It establishes source-of-truth boundaries, anti-corruption rules, tenant-specific configuration, contract evolution, reliability, security, and operational accountability for integrations.

## Scope

This document covers OwnID, Moodle, MCP-enabled AI capabilities, and future external providers. It applies to synchronous requests, event-driven exchange, scheduled synchronization, imports, exports, and operator-initiated replay.

It does not define endpoints, payload schemas, vendor-specific field mappings, business workflows, or provider selection. Each implemented integration must add a contract and operating guide consistent with this foundation.

## Responsibilities

The integration architecture is responsible for:

- preserving OwnSIS ownership of academic and administrative data;
- preventing external models from leaking into internal domain models;
- isolating each organization's configuration, credentials, data, and failures;
- making delivery semantics, freshness, partial failure, and reconciliation visible;
- ensuring repeatable and idempotent processing;
- protecting sensitive data and applying least privilege;
- evolving contracts without silently changing their meaning;
- providing auditable provenance from an external fact to its OwnSIS effect.

Every integration has an OwnSIS owner responsible for its contract, data classification, supported versions, operational signals, recovery procedures, and decommissioning. Vendor ownership never substitutes for internal accountability.

## Integration Principles

### Explicit authority

Every exchanged concept has one authoritative owner. Copies are identified as projections, caches, external evidence, or delivery state. Conflict resolution never defaults to “last writer wins” across authorities.

### Anti-corruption boundaries

Each external system is isolated behind an adapter that translates protocol, identifiers, terminology, lifecycle, and failure modes into OwnSIS application language. Vendor objects do not pass directly into domain models, persistence, events, or user interfaces.

### Minimal disclosure

An integration receives only the data and capability required for its declared purpose. Convenience, future speculation, and bulk object replication are not valid reasons to broaden disclosure.

### Tenant isolation

Configuration, credentials, cursors, rate limits, mappings, retries, logs, and reconciliation state are tenant-scoped. One organization's failure or suspension must not expose data to, or silently block, another organization.

### Observable reliability

Integration work has durable identity, tenant context, correlation, attempt history, and outcome. Operators can determine whether data is pending, delivered, rejected, retried, quarantined, or reconciled without inspecting sensitive payloads.

## Authority by Integration

| Boundary | External authority | OwnSIS authority | Prohibited interpretation |
| --- | --- | --- | --- |
| OwnID | Credentials, authentication, identity-provider session, asserted subject identity, authentication assurance | Tenant membership, permissions, entitlements, authorization, academic and administrative relationships | An OwnID assertion is not an OwnSIS permission or institutional record |
| Moodle | Learning content, learning activities, and native learning-delivery state | Official institutional structure, enrollment, academic policy, accepted outcomes, and administrative records | Moodle roster or result state is not automatically an official OwnSIS record |
| MCP and AI providers | Protocol execution and generated output within an approved tool invocation | All source data, authorization, policy decisions, accepted changes, and audit evidence | Generated content is not authoritative and the model has no ambient authority |
| Other external systems | Only the concepts explicitly assigned to that provider by an approved integration contract | All OwnSIS-owned academic and administrative concepts | Synchronization does not create shared ownership |

## OwnID Boundary

OwnID is the sole identity provider. OwnSIS relies on verified, standards-based identity assertions supported by OwnID and validates their issuer, audience, validity, signature, and authentication context. OwnSIS does not store local passwords, create a fallback login mechanism, or accept identity assertions from another provider.

OwnSIS maps an OwnID subject to tenant-specific membership and authorization state. Subject identity, membership, permission, and entitlement remain separate concepts. A valid OwnID session grants no OwnSIS action unless current OwnSIS policy authorizes it in the resolved tenant.

Provisioning and deprovisioning exchanges must tolerate ordering differences and retries. Removing a tenant relationship or permission in OwnSIS takes effect independently of any still-valid identity-provider session. OwnID outages may prevent new authentication but must not cause OwnSIS to weaken verification or activate a local credential path.

## Moodle Boundary

Moodle is responsible only for learning. OwnSIS sends the minimum institutional facts Moodle needs to deliver approved learning activity and receives the learning facts OwnSIS has agreed to consider.

The Moodle adapter translates between Moodle terminology and OwnSIS concepts. Moodle identifiers are external references, not OwnSIS domain identity. Moodle-side edits cannot silently overwrite official institutional structure, enrollment, or academic records.

Any learning result returned from Moodle is treated as external evidence with provenance, source version, and observation time. It becomes an official OwnSIS outcome only through the owning domain policy. Synchronization exposes rejected, stale, or ambiguous mappings for controlled resolution; it does not guess across tenants or entities.

Moodle failure must degrade learning synchronization, not the integrity of core OwnSIS records. Recovery uses idempotent replay and reconciliation against declared authority.

## MCP and AI Boundary

MCP is the protocol boundary through which approved AI capabilities discover context and invoke tools. It is not a bypass around application use cases.

Every MCP tool has a narrow purpose, explicit input and output classification, tenant scope, required permission, side-effect declaration, and audit behavior. Tool execution revalidates authorization at the time of use. Read and write capabilities are distinct; a model cannot convert read access into write authority through composition.

AI-generated output is untrusted input. It is validated by the owning application policy before use and clearly identified when presented for human judgment. Actions with material academic, administrative, financial, security, privacy, or external-communication effects require the same confirmation or human approval expected outside AI-assisted operation.

Context supplied to a model is minimized and protected against cross-tenant retrieval. Prompt injection, tool-output injection, fabricated identifiers, replay, and data exfiltration are treated as expected threats. Model providers receive no durable system credentials and no direct database access.

## Integration Contract Model

Each integration contract records, in human-readable form:

- purpose and owning teams;
- authoritative source for every exchanged concept;
- tenant and actor context;
- data classification and permitted use;
- semantic meaning and versioning policy;
- delivery, ordering, duplication, and freshness expectations;
- authorization and credential requirements;
- failure, retry, quarantine, reconciliation, and support behavior;
- retention, deletion, and decommissioning obligations.

A contract describes externally observable meaning without exposing internal database representation. Identifier formats are opaque. Optionality, default behavior, and time semantics are explicit. A schema alone is not a complete contract.

## Interaction Patterns

### Synchronous interaction

Synchronous calls are reserved for results required immediately to complete an application operation. They use bounded timeouts, cancellation, rate protection, and clear failure translation. OwnSIS does not hold a database transaction open across an avoidable external call.

### Event-driven exchange

Integration events publish completed, owned facts. State change and durable publication use a transactional outbox or equivalent mechanism. Consumers maintain idempotency and processing state. Delivery is assumed to be at least once; duplicates are normal, not exceptional.

### Scheduled synchronization

Scheduled exchange is appropriate when a provider lacks reliable event delivery or reconciliation is required. It uses durable cursors or checkpoints scoped to the tenant and contract version. Advancing a checkpoint occurs only after the corresponding work is safely accepted.

### Import and export

Bulk exchange is staged, validated, authorized, and auditable. Validation separates structural errors, semantic conflicts, and policy rejection. A partial result is explicit. An import does not bypass the same domain rules applied to interactive changes.

## Reliability and Recovery

Integration handlers are idempotent at the level of a meaningful external operation. Duplicate detection does not depend only on wall-clock timing. Where an external provider lacks stable operation identity, the adapter establishes a deterministic reconciliation strategy without claiming exactly-once delivery.

Retries use bounded exponential backoff with jitter and distinguish transient, throttling, authentication, validation, and permanent failures. Permanent or exhausted failures enter a quarantined state with reason, tenant, contract version, and safe replay instructions. A dead-letter destination is an operational queue, not an archive that can be ignored.

Circuit breaking and concurrency limits prevent a failing provider or noisy tenant from exhausting shared capacity. Reconciliation compares states according to declared authority and produces explainable differences. Manual replay reuses normal validation and authorization paths and is fully audited.

## Contract Evolution

Contracts evolve additively where possible. Consumers tolerate newly added information but never infer a new meaning from an old field. Breaking semantic change uses an explicit version transition with supported overlap, consumer readiness evidence, and a retirement policy.

Published events remain interpretable for their retention lifetime. Adapters isolate vendor version changes so the OwnSIS domain changes only when institutional meaning changes. A provider deprecation is handled as a planned compatibility change, not as an emergency rewrite of domain modules.

## Security and Privacy

Integration credentials are stored in an approved secrets facility, encrypted, scoped to one tenant and purpose, rotated, and never written to logs. Provider permissions use least privilege. Incoming communications are authenticated and protected against replay where the protocol permits; outgoing destinations are allowlisted to reduce server-side request forgery risk.

Payload logging is disabled by default for sensitive data. Diagnostic records contain safe identifiers, classifications, timings, and failure codes. Data residency, retention, deletion, and consent obligations follow the owning data classification and tenant policy even when a provider retains a copy.

Integration activation, credential changes, scope expansion, suspension, replay, and decommissioning are privileged, audited operations. Disabling an integration stops new exchange while retaining the evidence necessary to reconcile and satisfy retention obligations.

## Testing and Operational Readiness

Adapters are tested against owned contract fixtures and provider-compatible test environments. Tests cover duplication, reordering, timeout, partial response, throttling, invalid authentication, contract-version mismatch, tenant mismatch, replay, and recovery. Consumer-driven compatibility checks protect published contracts.

Operational readiness requires metrics for throughput, latency, freshness, error classification, retries, quarantine depth, credential expiry, reconciliation differences, and per-tenant rate pressure. Alerts identify user impact and authority risk rather than raw error count alone. Runbooks preserve normal domain and security controls during recovery.

## Assumptions

- External providers are independently deployed and may be unavailable, slow, duplicated, reordered, or semantically inconsistent.
- OwnID can provide verifiable identity assertions and a supported lifecycle for keys and authentication assurance.
- Moodle can exchange learning information while accepting OwnSIS authority for official institutional data.
- MCP providers and models are untrusted with respect to authorization and domain correctness.
- Most event delivery is at least once, and exactly-once behavior is not an end-to-end guarantee.
- Organizations may use different integrations, credentials, versions, and data-residency arrangements.
- PostgreSQL can durably support integration state, outbox publication, and reconciliation metadata unless a later ADR selects specialized infrastructure.

## Future Evolution

Integration transport may evolve from in-process durable dispatch to dedicated messaging infrastructure as throughput, isolation, or external consumer needs justify it. This change must preserve contract meaning, tenant context, idempotency, observability, and replay behavior.

Tenant deployment cells and dedicated databases may require region-aware routing and provider endpoints. Contract ownership and authority remain unchanged. Additional learning, finance, communication, reporting, or government integrations can be added only behind dedicated anti-corruption boundaries with explicit data-governance review.

MCP capabilities will expand through a curated tool catalog with progressively stronger evaluation, provenance, and approval controls. AI autonomy will increase only where measured safety and reversibility support it; no evolution grants a model ambient tenant access or authority over official records.

Integration contracts, supported provider versions, failure evidence, and security posture will be reviewed regularly. Obsolete contracts are retired through measured decommissioning that preserves audit and historical interpretation.
