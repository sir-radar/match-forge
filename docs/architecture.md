# MatchForge Architecture

## Purpose

This document records durable system boundaries, language ownership, storage ownership, and dependency direction across MatchForge.

It does not replace `PLAN.md`, schemas, migrations, model contracts, current project-status records, or resolved owner/Wayfinder decisions.

## Implementation Status

This document defines architectural ownership and allowed dependency direction. It does not imply that every component described here is currently authorized, implemented, production-ready, or exposed through an API.

Current implementation, gate, and authorization state must be read from the repository's tracked project-status authority and the applicable resolved owner/Wayfinder decisions and evidence.

Where these sources disagree, the newer explicit owner/Wayfinder decision takes precedence over a stale architectural or planning checkpoint.

## System Flow

```text
approved providers
        ↓
provider adapters
        ↓
immutable raw acquisition
        ↓
validation and normalization
        ↓
MatchForge identity resolution
        ↓
cross-provider reconciliation
        ↓
trusted publication or quarantine
        ↓
point-in-time dataset construction
        ↓
statistical models and feature systems
        ↓
match parameter generation
        ↓
optional Rust simulation
        ↓
probability aggregation and calibration
        ↓
immutable forecast registry
        ↓
API, evaluation, monitoring, governance
```

The learning layer estimates football capabilities and predictive distributions.

The simulation layer samples outcomes from an approved match context and parameter set.

These responsibilities remain separate.

## Language Boundaries

```text
Python:
football data, feature generation, statistical models, ML,
calibration, evaluation, model/forecast artifact creation

Rust:
pure deterministic high-volume simulation

Go:
production API, authorization, caching, job orchestration,
operational endpoints

SQL migrations:
relational persistence

Shared schemas/contracts:
cross-language messages and artifact shapes
```

### Python

Python owns:

- provider adapters;
- ingestion orchestration;
- normalization;
- point-in-time datasets;
- football feature engineering;
- Elo, Dixon-Coles, corner models, and later approved models;
- model fitting;
- calibration;
- walk-forward evaluation;
- forecast creation;
- model artifact creation;
- analytical reports.

Do not move football modelling logic into Go or Rust merely for symmetry.

### Rust

Rust owns:

- deterministic Monte Carlo simulation;
- simulation-specific random-number handling;
- parallel high-volume execution;
- simulation-specific numerical hot paths after profiling.

Rust must not own:

- provider ingestion;
- PostgreSQL data access for modelling;
- historical reconstruction;
- model fitting;
- feature engineering;
- HTTP serving.

Do not expand Rust modelling responsibilities before simulation is authorized.

### Go

Go owns:

- HTTP serving;
- request validation;
- authentication and authorization;
- rate limiting;
- cache coordination;
- job submission;
- health and readiness;
- observability;
- retrieval of already-generated forecasts and model metadata.

Go must not reimplement football model mathematics.

### SQL

SQL migrations are the sole schema authority.

Use the repository's approved migration framework.

Do not introduce a competing ORM migration authority.

## Storage Ownership

### Raw Provider Data

Use immutable filesystem or object-storage paths with checksums and exact source details.

Do not rewrite authoritative raw payloads.

### PostgreSQL

Use PostgreSQL for structured relational state and registrations, including:

- MatchForge competitions, seasons, teams, players, and matches;
- provider registry and provider-entity mappings;
- bitemporal source observations;
- lineup and availability observations where applicable;
- source snapshot and resource registration;
- provider sync policy, cursor, and job state;
- resolution decisions and quarantine state;
- `CanonicalChangeSetV1` registration where applicable;
- dataset and lineage registry;
- model artifact registration;
- forecast registration;
- evaluation report registration;
- promotion and governance events;
- durable operational state.

PostgreSQL should register model artifact identity, URI, checksums, compatibility, lineage, and governance metadata rather than opaque Python binaries.

### Parquet / Object Storage

Use Parquet or object storage for:

- normalized event history;
- StatsBomb 360 or equivalent high-volume data;
- curated modelling datasets;
- generated feature matrices;
- walk-forward predictions and outcomes;
- analytical evaluation and calibration outputs;
- simulation archives;
- model artifact files where appropriate.

### Redis

Use Redis only for ephemeral or cache concerns:

- prediction cache;
- simulation job state;
- API caching;
- other non-authoritative short-lived state.

Redis is never the authoritative model registry, forecast history, lineage store, or evaluation store.

### DuckDB

Use DuckDB for local analytical queries and dataset inspection.

It is not a second source of truth.

## Identity

MatchForge identity is provider-neutral.

Provider IDs live in mappings and source observations.

Names are attributes, not identifiers.

Do not merge entities solely because their names look similar.

Resolution must be explicit, deterministic, and traceable.

## Point-in-Time Contract

Historical forecast work separates:

```text
football_cutoff
knowledge_cutoff
knowledge_mode
```

Use separate contracts for:

```text
historical labelled training rows
label-free pre-match forecast context
post-prediction outcomes
```

Models do not independently query "previous matches" from current database state.

Current-state views are operational conveniences. They are not valid historical modelling inputs unless an explicit point-in-time reconstruction contract says otherwise.

When multiple matches could not legitimately observe each other's outcomes, forecast and freeze the whole batch before revealing any result.

## Dependency Direction

Preferred:

```text
raw provider data
→ validated provider observations
→ MatchForge records
→ point-in-time datasets
→ models
→ artifacts
→ forecasts
→ evaluation / simulation / API
```

Avoid cycles that allow downstream modelling state to mutate upstream source truth.

## Publication and Retry Boundary

Persistent publication must assume at-least-once execution.

Where applicable:

- immutable writes use deterministic identity and checksums;
- identical retries converge on the existing logical result;
- conflicting bytes fail closed;
- database registration and file publication have explicit recovery behavior;
- partial publication can be detected and reconciled;
- concurrency must not create multiple logical artifacts for one semantic identity.

Detailed retry and recovery behavior belongs in the owning subsystem document.

## Artifact Boundary

Canonical fitted model state should use transparent, portable formats where practical.

Persist immutable identity and checksums.

Do not make pickle, joblib, or cloudpickle the canonical production artifact format.

Published artifacts are immutable. A correction or refit creates a new artifact.

## Simulation Boundary

The simulator is downstream of learned football capabilities and match parameters.

Simulation count controls numerical precision; it is not evidence of predictive quality.

Move a hot path to Rust only after:

```text
Python correctness prototype
→ benchmark/profile
→ justified Rust implementation
→ equivalence tests
```

## API Boundary

The Go API exposes only capabilities supported by executed data and evaluation gates.

An endpoint's existence must not imply a model or data capability that has not been authorized and proven.

The API must not reimplement model mathematics owned by Python or simulation logic owned by Rust.

## Detailed References

Use the owning document for implementation-level detail:

- [Data platform architecture](data-platform-architecture.md)
- [Source acquisition](source-acquisition.md)
- [Data model](data-model.md)
- [Temporal model](temporal-model.md)
- [Canonical ingestion](canonical-ingestion.md)
- [Event datasets](event-datasets.md)
- [Data validation](data-validation.md)
- [Ingestion reports](ingestion-reports.md)
- [Backtesting](backtesting.md)
- [Model governance](model-governance.md)
- [Engineering testing](engineering/testing.md)

Current project state belongs in the tracked project-status authority and applicable Wayfinder/evidence records rather than this document.
