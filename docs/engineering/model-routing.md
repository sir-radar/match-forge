# MatchForge Model Routing

Use the lowest-cost model that can safely complete the work. Routing follows correctness risk, not task prestige.

## L1 — Luna

Use `gpt-5.6-luna` when all are true:

- requirements are already frozen;
- implementation shape is clear;
- behavior is easily verified;
- no architecture decision is required;
- no historical/statistical invariant changes;
- task is bounded to one coherent concern.

Typical MatchForge examples:

- Pydantic DTOs
- JSON schemas
- serializers
- Parquet readers/writers
- fixtures
- straightforward validation
- simple CLI plumbing
- provider capability declarations
- repository boilerplate
- repetitive unit tests
- documentation with no governance impact
- straightforward refactors and simple renames
- lint/type fixes
- deterministic mapping tables
- simple adapter methods after contracts are frozen

## L2 — Terra

Use `gpt-5.6-terra` for normal production engineering that needs judgment but does not introduce an unresolved high-risk architectural, historical, statistical, or security decision:

- multi-file features
- provider adapters
- HTTP clients
- retry logic
- rate limiting
- persistence
- repositories
- migrations whose semantics are already decided
- integration tests
- moderate refactoring
- focused performance work after profiling
- error handling
- idempotency
- observability
- CI work
- backup/recovery implementation
- implementation of already-approved architecture

Terra is the default implementation model.

## L3 — Sol

Use `gpt-5.6-sol` for:

- architecture decisions
- statistical models
- probability mathematics
- forecasting semantics
- chronological evaluation
- leakage-sensitive code
- `football_cutoff`, `knowledge_cutoff`, or `knowledge_mode` rules
- bitemporal semantics
- same-kickoff batching
- authoritative evaluation, gate policies, or thresholds
- model promotion and governance
- cross-provider resolution authority and MatchForge identity-resolution rules
- dependency invalidation architecture
- immutable artifact, model, or forecast identity
- security-sensitive design
- difficult concurrency
- difficult database transaction semantics
- final review of high-risk changes

A lower-tier model must not independently resolve these decisions.

## Escalation

Escalate `Luna → Terra → Sol` when:

- requirements conflict;
- a resolved contract is unclear;
- implementation requires changing architecture;
- the same substantive failure occurs twice;
- correctness cannot be established mechanically;
- completing the task would require weakening a test, gate, or invariant;
- an implementation path would alter a frozen decision.

Do not repeatedly retry a weaker model when the problem needs stronger reasoning.

## De-escalation

After Sol resolves architecture or ambiguity:

1. freeze the decision;
2. record it in the appropriate owner/Wayfinder/ADR/policy location;
3. return bounded implementation work to Terra or Luna where appropriate.

## Scope

Model escalation does not authorize scope expansion. If a stronger model concludes that a resolved contract should change, surface the conflict. Do not silently change the contract.

## Task routing preflight

Before substantial implementation:

1. Break the requested work into independent concerns.
2. Classify each concern as L1, L2, or L3.
3. Identify any L3 decision that blocks implementation.
4. Resolve architecture/high-risk decisions before delegating lower-risk work.
5. Use the cheapest appropriate model for bounded implementation where the environment supports model-specific delegation.
6. Never downgrade a task merely to reduce token usage.

## Wayfinder interaction

A Wayfinder ticket's type does not by itself determine the model level:

- a mechanical implementation ticket from a frozen contract may be L2;
- a research/grilling ticket that decides model mathematics is L3;
- a checksum-only evidence update may be L1 or L2;
- any ticket that can change an authoritative evaluation rule is L3.

Model choice never changes the ticket's authorization boundary.
