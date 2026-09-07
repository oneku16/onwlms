# ADR-0002: Backstop Tenant Context with PostgreSQL Row-Level Security

- **Status:** Proposed
- **Decision date:** 2026-08-05
- **Decision owners:** OwnSIS architecture and security maintainers

## Purpose

Define a reversible first-release mechanism that makes organization context
explicit in application transactions and provides a database backstop against a
missing repository predicate.

## Context and Decision Drivers

OwnSIS serves multiple organizations from shared application and PostgreSQL
infrastructure. Application authorization and tenant-scoped repositories are
mandatory but a single omitted predicate must not expose another tenant. The
same schema must also allow future tenant placement in dedicated databases or
deployment cells without changing domain identity.

Platform administration needs global access to platform-owned organization and
plan metadata, but it must not imply permanent access to tenant academic data.
Migration tooling needs schema authority that the ordinary application must not
hold.

## Decision

Tenant-owned tables include a non-null `organization_id`, tenant-aware unique
constraints, supporting indexes, and PostgreSQL row-level security (RLS). At the
start of each tenant transaction, the database adapter sets
`app.organization_id` with `set_config(..., true)`. Policies compare the row's
organization to that transaction-local value. Missing or malformed context
matches no row.

RLS is forced for tenant tables. The ordinary `ownsis` runtime role is
`NOBYPASSRLS`, does not own tables, and receives only the DML permissions it
needs. The migration role owns schema evolution and is not used by request or
worker processes. Platform-global tables are deliberately enumerated and do not
receive a tenant policy.

Application authorization and tenant predicates remain mandatory. RLS is a
backstop, not a policy engine. Platform administrators use separate platform
capabilities for global metadata. Any support access to tenant data establishes
one explicit tenant context, requires a reason and dedicated permission, and
produces audit evidence; there is no general RLS-bypass path in the product.

## Consequences and Risks

This provides defense in depth and makes accidental context loss observable as
an empty/denied operation. Database integration tests must use the ordinary
runtime role because a migration owner can invalidate the evidence. Connection
pool reuse is safe because the context is transaction-local.

RLS increases migration and diagnostic complexity. Every new tenant-owned table
must be classified and receive a policy in the same migration. Operator queries
must use separately governed credentials. A future dedicated-database topology
can retain the column and application contract while simplifying its local RLS
policy.

## Alternatives Considered

- **Application predicates only:** rejected because one omitted predicate has a
  cross-tenant blast radius.
- **A schema or database per tenant immediately:** rejected because it adds
  routing, migration, pooling, and operations complexity before measured need.
- **A privileged runtime role with optional RLS bypass:** rejected because it
  would turn ordinary platform administration into ambient tenant-data access.

## Assumptions and Reassessment

PostgreSQL remains the first-release transactional store. This decision should
be reassessed when tenants move to dedicated placement, when PostgreSQL policy
behavior becomes a measured bottleneck, or when a supported reporting topology
needs a separately governed read model. Acceptance requires architecture and
security review plus real-role integration tests.
