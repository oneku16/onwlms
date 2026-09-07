# ADR-0006: Use a Deterministic, Explainable Scheduling Heuristic

- **Status:** Proposed
- **Decision date:** 2026-08-05
- **Decision owners:** OwnSIS scheduling and architecture maintainers

## Purpose

Define a useful first timetable generator without prematurely choosing a
specialized optimizer or claiming globally optimal schedules.

## Context and Decision Drivers

The first release requires manual timetable editing, immediate conflict
detection, locked sessions, regeneration, hard constraints, soft preferences,
and an explainable proposal. Institutional weights and representative workloads
are not yet validated, so a genetic algorithm or solver commitment would encode
speculative policy.

## Decision

Scheduling exposes a replaceable generator port. The first adapter is a
deterministic greedy heuristic: preserve locked sessions, order remaining work
by the fewest feasible resources and stable identifiers, enumerate the configured
time grid in stable order, reject hard conflicts, and choose the candidate with
the lowest named soft-constraint penalty. Equal candidates use stable UUID/order
tie-breaking.

The result includes proposed sessions, unresolved hard conflicts, named soft
violations, and an explainable quality score. Hard constraints are never traded
for a better score. Manual changes use the same conflict detector. Generation
does not publish an official timetable until an authorized user explicitly
accepts the proposal.

## Consequences and Risks

Results are reproducible, testable, and explainable, and locked-session
regeneration is straightforward. The heuristic may leave a feasible schedule
unresolved or produce lower-quality gap distribution than a mature optimizer.
The UI and API must label it as a proposal and expose unresolved conditions.

## Alternatives Considered

- **Genetic algorithm:** deferred because convergence, reproducibility, weights,
  and operational tuning are not validated.
- **Constraint-programming dependency:** a credible future option, deferred
  until workload and licensing/maintenance review justify it.
- **Manual scheduling only:** rejected because the release explicitly requires a
  replaceable generator contract and useful deterministic implementation.

## Assumptions and Reassessment

First-release workloads are small enough for enumerating feasible time/resource
combinations. Reassess against representative institutions using success rate,
runtime, unresolved hard conflicts, and accepted soft-quality measures.
Acceptance requires scheduling-domain and architecture review plus locked,
conflict, determinism, and explanation tests.
