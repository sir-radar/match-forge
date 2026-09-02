# MatchForge Model Routing

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
- documentation
- straightforward refactors
- lint/type fixes
- deterministic mapping tables
- simple adapter methods after contracts are frozen

## L2 — Terra

Use `gpt-5.6-terra` for normal production engineering:

- multi-file features
- provider adapters
- HTTP clients
- retry logic
- rate limiting
- persistence
- repositories
- integration tests
- moderate refactoring
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
- bitemporal semantics
- cross-provider resolution authority
- dependency invalidation architecture
- immutable artifact identity
- gate-policy logic
- governance
- security-sensitive design
- difficult concurrency
- difficult database transaction semantics
- final review of high-risk changes
