# MatchForge Architecture

## Purpose

This document records durable system boundaries, language ownership, storage ownership, and dependency direction across MatchForge.

It does not replace `PLAN.md`, schemas, migrations, model contracts, current project-status records, or resolved owner/Wayfinder decisions.

## Implementation Status

This document defines architectural ownership and allowed dependency direction. It does not imply that every component described here is currently authorized, implemented, production-ready, or exposed through an API.

Current implementation, gate, and authorization state must be read from the repository's tracked project-status authority and the applicable resolved owner/Wayfinder decisions and evidence.

Where these sources disagree, the newer explicit owner/Wayfinder decision takes precedence over a stale architectural or planning checkpoint.

### Architecture V2 baseline

Architecture V2 starts from the final R3 head, `c46fa44f4fdae16f0dbff7c4dd7cd8a19f3dc365`, merged through PR #167. Phase 0 preserves the existing runtime before any schema or worker cutover. The remaining phases require implementation and acceptance evidence.

Run the capture from the repository root with the existing `.env` exported and `scripts/toolchain.sh` loaded:

```sh
uv run --locked python -m scripts.capture_architecture_v2_baseline \
  --output .local/remediation/matchforge-architecture-v2/new-baseline \
  --fixture-date 2026-10-14 --fixture-date 2026-10-15 --fixture-date 2026-10-16 \
  --cutoff 2026-10-15T23:29:06.806401Z
```

The output directory must not exist. The tool shares an exported PostgreSQL snapshot between a read-only repeatable-read transaction and the Compose PostgreSQL container's `pg_dump`. It retains a restorable database archive, schema, migration checksums, primary-key and row-hash inventories, current projections, historical cutoff hashes, source registrations and verified source bytes, champion checksum, history coverage, queue state and observable locks. Database row contents stay in the local backup; row inventories contain keys and hashes. API captures are separately timed observations because live sync remains enabled.

Missing or unverifiable legacy source bytes are reported individually and produce `PASS_WITH_WARNINGS`; they are never silently repaired. The dump preserves their registrations. An interrupted capture remains `INCOMPLETE`. Keep all output under ignored `.local/` storage, with the same access restrictions as the original data, and leave old R3 evidence untouched.

Restore `database.dump` using PostgreSQL 18's `pg_restore --exit-on-error --no-owner --no-acl` into a new, empty database. Never restore over the operating database. Then select the restored database through `DATABASE_URL` and run:

```sh
uv run --locked python -m scripts.capture_architecture_v2_baseline \
  --output .local/remediation/matchforge-architecture-v2/new-restore-verification \
  --verify-restored-baseline .local/remediation/matchforge-architecture-v2/phase-0
```

Verification requires exact table and historical-cutoff hashes, the original dump checksum, and intact archived source bytes. Current-time views are captured for reference rather than compared at a later wall-clock time. A successful capture alone does not prove a successful restore or completion of Architecture V2.

### Versioned resource observations

The typed contracts in `football.contracts.observations` have a checked-in JSON Schema at `schemas/contracts/resource-observations-v1.schema.json`. Each resource has its own fields. Fixture scheduling excludes scores; results, lineups, availability, events, shots, xG, named statistics, standings and odds remain separate. An absent resource produces no observation. Within an observed resource, `null` means unreported or unknown; zero and false remain observed values. Unknown source values require an explicit mapping or quarantine before construction.

Native identifiers remain scoped to the named provider. A missing native ID requires a source-record locator, such as a CSV row; names never create canonical IDs. Canonical references remain null until independently resolved. Every observation binds a registered source snapshot, resource and byte checksum, and records separate provider-schema, adapter, normalizer, observation-contract and optional resolution versions. An unknown provider schema or unresolved identity stays explicit rather than acquiring a fabricated version.

`observed_at` records when the source was observed, `acquired_at` matches the registered raw resource, and `known_at` records when MatchForge could know the observation. Knowledge cannot precede observation or acquisition. Optional `event_time`, `provider_updated_at` and the half-open `[valid_from, valid_to)` interval describe football/provider time independently. None of these fields alone establishes eligibility for a historical forecast; the existing point-in-time contracts continue to govern it.

Canonical UTF-8 JSON sorts object keys, normalizes timestamps to UTC and integral numbers to integers, rejects nonfinite values and duplicate fields, and ends with a newline. Its SHA256 determines immutable observation identity. A correction, changed knowledge time or changed processing version creates a new observation. The schema fingerprint is immutable for each contract version.

`football.observations.storage.ObservationArtifactStore` writes immutable typed JSON files and registers only provenance, time, version and file metadata in PostgreSQL. This shared registry contains no EAV domain values. Source provenance is checked against raw registrations, and SQL rejects updates/deletes to artifacts and contract versions. File publication precedes registration; rollback can leave an unregistered immutable file, and an identical retry converges. The caller owns the transaction. These shadow artifacts do not admit identity, replace existing serving/history tables, or alter forecasts.

With `scripts/toolchain.sh` loaded, `uv run --locked python -m football.observations.cli schema` emits the schema. The `validate INPUT` command checks a document; `store INPUT --data-root PATH` registers it using `DATABASE_URL`. Use a migrated shadow database until the later parity and cutover gates pass.

`PointInTimeRepository.resource_observation_ids_at` reads this registry by exact contract and provider with an explicit `knowledge_cutoff`. It returns all immutable observations whose `known_at` is at or before that cutoff, ordered by knowledge time and observation ID. Provider update times and earlier football validity never backdate MatchForge knowledge. Later corrections add observations; the reader preserves earlier evidence and does not choose a conflict winner or latest normalizer.

An explicit `football_cutoff` restricts history to observations with a reported `event_time` strictly before it, excluding simultaneous, future and unknown event times. A requested `valid_at` requires a reported validity start and applies `[valid_from, valid_to)`; a null end is open. Without these filters, the query describes source facts known at the cutoff, including known future schedules or announcements. Returned IDs can be loaded separately through `ObservationArtifactStore`; they do not establish canonical identity, model-history eligibility or a sealed forecast context. The existing modelling and serving paths remain active during shadow migration.

### Provider-native records

`football.providers.native` describes each provider's JSON records independently. FotMob keeps numeric/string IDs and camel-case fields; PitchAPI keeps its own string IDs, status vocabulary and snake-case fields. API-Football models its own fixtures, teams, lineups, injuries, statistics and standings. football-data.org retains its v4 fixture, score and standing structures. OpenFootball retains source names and file/row identity rather than inventing team IDs. Football-Data.co.uk continues to use `FootballDataUkCsvRecordV1` and its receipt-verified CSV parser, preserving string values and empty cells.

`native_record(Model, payload)` checks required fields and native types, rejects nonfinite/non-JSON values, and returns an independent typed copy. It preserves additive fields, unknown status values, string spelling, timezone text, numeric representation, omitted fields and explicit nulls. Football meaning and canonical identity belong to subsequent normalization/resolution. These are field-shape readers, not assertions that an API resource is enabled, complete or historically eligible. Existing acquisition and serving paths remain active during shadow migration.

For offline inspection, `uv run --locked python -m football.providers.native.cli --model FotmobFixture INPUT` returns the parsed native record with the exact input-byte SHA256. Duplicate JSON keys are rejected. The static model list selects a decoder; runtime provider availability belongs to the later capability registry.

### Provider acquisition capabilities

`football.providers.sources.contracts` defines narrow fixture, result, competition, team, player, coach, lineup, availability, event, shot, xG, statistic, standing and odds ports. Implementations expose only acquisition methods backed by their existing clients. They return `ProviderPayload`: original immutable bytes, provider/resource identity, acquisition time, media type and available revision/cache/quota metadata. Football fields stay in the native payload until resource-specific normalization. A method's presence does not prove scoped coverage, access approval or historical eligibility.

HTTP implementations reuse the existing guarded FotMob, PitchAPI, API-Football and football-data.org clients. Queries and native season labels stay inside this boundary; football-data.org requires an explicit competition scope, and API-Football's current-only catalog filter remains in the resource key. FotMob's detailed capabilities share its physical match-details response; PitchAPI's xG capability uses its shot resource. Preserve those original bytes rather than creating synthetic provider responses. Coach and odds ports have no standalone acquisition implementation at this stage.

File implementations read existing Football-Data.co.uk receipts and pinned OpenFootball Git objects; they neither reacquire historical sources nor trust mutable working files or file modification times as knowledge evidence. StatsBomb retains its existing commit pin. These ports are for shadow ingestion; current production entry points remain active until the parity and cutover phases. Network work must finish before the later normalization/persistence transaction begins.

### Resource normalization

`football.providers.normalization.pipeline.normalize_resource` verifies the registered source checksum and dispatches an explicit provider/resource pair. Fixtures and results, participants, lineups, availability, events, shots, xG, named statistics, standings and retained CSV odds produce separate observations. Missing resources produce no measurements. Unknown values and unsupported fields produce structured findings; a bad record does not replace valid sibling records. Repeated statistics may corroborate each other, while contradictory duplicates quarantine the affected measurement. This decoder registry does not establish runtime provider availability.

V2 contracts in `football.contracts.observations_v2` add `EntityReferenceV2.source_record_key`. This identifies an exact field within the observation's source resource when a provider supplies no ID. JSON pointers, CSV record/column locations and ZIP member locations preserve anonymous participants without treating names or generated IDs as provider identity. V1 schema fingerprints and serialized bytes remain unchanged; both versions use the existing immutable artifact registry. Match-specific inputs must agree with native fixture IDs or registered request scope. A lineup coach does not establish a global manager tenure.

Provider update timestamps retain their declared timezone. A local timestamp without a verified timezone stays in raw evidence and a finding; normalization does not assume UTC. FotMob/PitchAPI coordinates remain unnormalized until their coordinate frame is verified. StatsBomb shots reuse the existing 120×80 coordinate contract. Third-party predicted lineups remain `UNKNOWN`, rather than acquiring MatchForge's `PREDICTED_REPEAT_XI` label. Football-Data.co.uk statistics remain aggregates, and odds remain separate from model features.

The offline command below reads registered retained bytes and writes an immutable report containing source lineage, processing versions, output identities and findings. It performs no provider requests. With `--persist`, all output registrations share one transaction; identical retries use the original registered acquisition/observation clocks. File publication may leave safe orphan files after rollback. Reports describe normalization outputs, not canonical admission or historical eligibility. Use the isolated shadow database until the cutover gate passes.

```sh
uv run --locked python -m football.providers.normalization.cli \
  --source-resource-id RESOURCE_UUID --resource shots --fixture-native-id NATIVE_MATCH_ID \
  --data-root .local/football-data --artifact-root .local/shadow-observations --persist
```

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

`IdentityRepository.mapping_at` reads recorded states of the five existing provider-mapping tables: competition, season, team, player and match. Those tables remain the identity owners. `provider_mapping_history` records their inserts, identity changes and deletions atomically with the original write, retaining the original mapping, canonical and source-snapshot IDs. Routine `last_seen_at` touches leave the identity history unchanged. Mapping IDs and history rows are immutable; truncation cannot bypass recorded changes.

Each read requires a football-validity instant and an explicit `knowledge_cutoff`. Mapping validity follows the existing half-open ranges, where null bounds are unbounded. Season native IDs require their native competition scope. The reader selects the known state before matching its native key, so a renamed or deleted mapping cannot resurrect its earlier key. Initial capture establishes knowledge at capture time; it does not reconstruct unrecorded earlier states. Source and mapping clocks can delay knowledge, and subsequent states cannot move knowledge backwards.

A returned mapping is an identity claim with provenance. Qualification stays with the existing decisions: `admitted_identity_at` reads R2 admissions and revocations, and delegates team corrections to `product_team_identity_at`. Confidence alone does not create admission. The resolution-decision and R3 fixture-resolution owners remain in place; an R3 version label does not make its mutable rows an immutable historical record. Existing lineup participation and coach observations retain their fixture and time scope. Continuous membership or management tenure requires independent evidence. The new mapping capture is rehearsed in shadow/test databases before the controlled cutover.

Team corrections extend the R2 `product_identity_admissions` log. A correction
links one source mapping to a verified target mapping and the original fixture
contradiction using `corrects_decision_id` and `target_mapping_id`. It preserves
the original provider mapping, fixture decisions and source observations. Its
database-stamped `decided_at` makes it eligible prospectively; source acquisition
is recorded separately and never substituted for an admission time.

`product_team_identity_at(mapping_id, knowledge_cutoff)` resolves immutable
admissions at the requested cutoff. Current operational views expose effective
IDs without rewriting physical records. History qualification appends snapshots
with the eligible IDs; `product_eligible_history_at` keeps earlier snapshots
unchanged after corrections and revocations. Forecast refresh and historical
fixture context resolve target teams at the same cutoff as their history reads.
Team admission does not merge fixtures; fixture reconciliation retains its own
competition, season, orientation and conflict checks.

The typed correction operation and deployment procedure are documented in
[MVP-HISTORICAL-BACKFILL.md](MVP-HISTORICAL-BACKFILL.md#independent-team-identity-corrections).

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

For product forecasts, a qualifying history decision or a changed future fixture
adds affected fixture IDs to `football.product_forecast_refresh_work` in the same
database transaction. The existing sync runner retries pending work in batches of
at most 32 fixtures. A batch marks its work complete in the same transaction as
its forecast and availability updates; interrupted batches remain pending. The
forecast builder still applies each fixture's football and knowledge cutoffs and
publishes immutable revisions only when its predictive inputs change.
New product forecasts use the `rolling-ten-v2` predictive-input hash and the
`transferable-rolling-goals-poisson-v1-rolling10-v2` product algorithm label.
The fitted model and probabilities are unchanged; older forecast versions remain
readable and are never rewritten.

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

## Multi-model Forecast Boundary

Python constructs one immutable, point-in-time forecast snapshot per fixture and passes
that same snapshot to every eligible model through the model registry. One model failure
is recorded without suppressing successful forecasts from other models. Model artifacts,
per-model forecasts, evaluations, and external probability benchmarks have separate
append-only storage; the existing production forecast table remains the champion-serving
contract.

The canonical joint score distribution is the source for 1X2, totals, BTTS, clean-sheet,
and simulation inputs. Context features retain structured competition type, home/away
splits, missingness, rest, opponent-adjusted form, and recency-weighted head-to-head data.
External provider predictions are benchmark-only and require exact fixture mapping.

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
- [Engineering testing](testing.md)

Current project state belongs in the tracked project-status authority and applicable Wayfinder/evidence records rather than this document.
