# Canonical relational data model

## Ownership

PostgreSQL owns provider-neutral identity, source lineage, historical observations, match participation, and the lightweight event catalogue. It does not own raw provider payloads, full analytical event facts, or report bodies; those remain immutable filesystem and Parquet responsibilities.

The acquisition-side filesystem contract is documented in [Source acquisition](source-acquisition.md).

SQL migrations under `infrastructure/migrations/` are the only authority for PostgreSQL shape. Python and Go must not introduce competing ORM migrations.

## Identity chain

Every supported entity follows this chain:

```text
canonical UUIDv7
    → provider mapping
    → immutable source snapshot/resource
    → provider observation history
```

Canonical identities exist for competitions, seasons, teams, players, matches, and events. Provider identifiers remain text within a provider namespace; they are never primary keys.

## Dependency lineage

`DependencyEdgeV1` records immutable directed links between source resources,
observations, datasets, model artifacts, forecasts, and evaluations.
`dependency_edges` has a logical unique key, so retries return the same link.

`derived_state_events` records only specific correction results:
`REBUILD_REQUIRED`, `AFFECTED_BY_SOURCE_CORRECTION`, and `SUPERSEDED`. No event
means `VALID`. Both tables reject updates and deletes. A state event must name a
trusted real-provider `CanonicalChangeSetV1`; fixture change sets cannot start
this path. A replacement is a new object and a new `DERIVED_FROM` link; old
objects and their recorded bytes remain available.

Season provider identity is composite:

```text
provider + provider_competition_id + provider_season_id
```

This permits the same provider season identifier under different competitions without ambiguity.

## Source lineage

`source_snapshots` identifies one immutable acquisition-manifest scope at a provider revision. The manifest scope path is its `source_identity`; `source_revision` and `git_sha` retain the pinned provider revision. This permits several deterministic resource scopes at one Git revision without losing any manifest registration. `source_resources` records each preserved resource path, SHA-256, size, media type, acquisition time, and processing state. Composite foreign keys prevent an observation from claiming a resource belonging to another snapshot or provider.

Source paths must be relative and cannot contain parent traversal. Checksums use a constrained 64-character lowercase hexadecimal domain.

Contract fixtures are explicit source records, not a provider alias or a naming
convention. A fixture snapshot has `source_kind = CONTRACT_FIXTURE` and a
required `fixture_id`; a real source has `source_kind = REAL_PROVIDER` and no
fixture ID. The fixture registry binds processing attempts to that source class.
Normal analytical dataset creation rejects fixture snapshots, so fixture rows
cannot become model input through the dataset path.

## Canonical and historical records

Canonical tables contain stable identity and relationships only. Mutable names, match status, scores, provider metadata, and similar source facts live in observation tables.

Observation uniqueness prevents the same immutable snapshot from publishing the same provider entity twice. GiST exclusion constraints prevent overlapping system-knowledge intervals for one canonical entity and provider.

Concurrent first-seen identity creation must place canonical-row creation and provider mapping in one transaction. Under contention, PostgreSQL may abort the losing transaction with an exclusion violation or deadlock detection; both preserve one committed canonical identity. The ingestion layer must classify that outcome as retryable and read the winning mapping on retry.

Cross-provider identity decisions are append-only `ResolutionDecisionV1` records.
They retain evidence references, candidate canonical IDs, versioned rule and
confidence, actor/reason, status, and optional supersession. Similar names do
not auto-merge entities; unresolved ambiguity remains review-required or
quarantined, and corrections supersede prior decisions instead of rewriting
history.

Provider corrections append `BitemporalCorrectionV1` records linking the prior
and replacement observations, exact source lineage, football-valid range, and
knowledge time. Existing observations remain immutable, so historical queries
continue to reproduce what was known at each cutoff.

`DataResolutionPolicyV1` is scoped to one domain/resource/field. It records
eligible providers, explicit precedence, freshness/completeness requirements,
accepted validation states, conflict tolerance, and escalation action. Provider
precedence is never global; losing observations remain preserved and every
selected fact resolves against this versioned policy.

Conflicts are append-only `ConflictRecordV1` records. Every source observation
reference is retained; policy evaluation records `RESOLVED`, `REVIEW_REQUIRED`,
or `QUARANTINED` without averaging or silently dropping values. A resolved
record names the selected observation explicitly, while unresolved conflicts
remain blocked from canonical publication.

`reconcile_field_observations` records agreement as `CORROBORATED` only when
all eligible provider observations are within the field policy's tolerance. A
disagreement never picks a source from precedence implicitly: it records a
`REVIEW_REQUIRED` or `QUARANTINED` conflict with no winner. The bounded
Football-Data score route uses quarantine, retaining StatsBomb's pre-existing
Sprint 2 authority and both provider observations.

Match resolution requires canonical competition, season, home-team, away-team,
and timezone-aware kickoff context. A single context-qualified candidate may be
auto-accepted; ambiguity is review-required and no candidate is quarantined.
Names or date similarity alone never merge provider matches.

## Match and lineup structure

Lineups are decomposed into:

```text
match_team_participations
    → match_team_participation_observations
    → match_player_participations
    → match_player_participation_observations
        → player_position_stints
        → player_cards
```

Team side and player lineup attributes remain historical observations. `player_source_facts`
preserves each distinct provider player variant with exact snapshot/resource lineage. Canonical
player observation fields contain only same-snapshot consensus; disputed fields are null and
`fact_status = 'conflicting'`. Position rows preserve StatsBomb's provider-reported period/clock
spans. End period and clock are either both present or both absent; non-monotonic source spans
remain intact for later quality classification.

## Event catalogue boundary

`event_catalog`, `event_provider_mappings`, and `event_observations` retain event identity, match linkage, provider IDs, source ordering, minimal football time, and lineage. Detailed event facts and coordinates remain owned by normalized Parquet datasets.

Within one source snapshot, provider event IDs and `(provider_match_id, event_index)` are unique. Canonical traversal uses `event_index ASC`.

## Dataset registry

`dataset_versions` registers immutable normalized dataset identity, schema and normalizer versions, source snapshot, manifest checksum, and publication state. `dataset_inputs` binds each version to source resources from the same snapshot through composite foreign keys. `dataset_files` records relative Parquet paths, physical and logical SHA-256 checksums, row counts, sizes, and schema checksum.

Filesystem publication precedes database registration. A registration rollback therefore cannot erase an already published immutable artifact; an identical rerun verifies the files and manifest, then reconciles missing PostgreSQL rows. See [Event datasets](event-datasets.md).

## Validation registry

`validation_runs` identifies one immutable execution by dataset version, dataset manifest, quality-policy checksum, and validator version. `validation_findings` records policy-derived severity, action, scope, evidence, and optional file and source-resource lineage. Composite foreign keys prevent cross-dataset files and cross-snapshot resources. See [Data validation](data-validation.md).

`match_lifecycle_claims` records derived football completion separately from provider observations.
Each claim binds an exact match observation, dataset version/file/input resource, validation run,
terminal-event evidence, deterministic checksum, and knowledge time. Composite foreign keys prevent
cross-match, cross-dataset, and cross-snapshot lineage. See [Match lifecycle claims](lifecycle-claims.md).

`match_kickoff_claims` records derived UTC chronology separately from timezone-naive provider
observations. Each row binds exact lifecycle, match, and competition evidence; local date/time;
timezone policy and TZif checksum; UTC kickoff; deterministic identity; and knowledge time. Raw
`match_observations.kickoff_at` remains nullable and unchanged. See
[Match kickoff claims](kickoff-claims.md).

## Migration policy

Production migrations are forward-only. The initial canonical migration has no destructive Down section. Corrections require a new migration.

`202608291335_preserve_provider_position_spans.sql` removes the original normalized-interval ordering assumption after verification against the pinned StatsBomb fixture. Other position shape and non-negative clock constraints remain enforced.

`202608291500_event_datasets.sql` adds normalized dataset versions, source-resource lineage, and file metadata.

`202608291530_data_validation.sql` adds immutable validation runs, policy-classified findings, and exact dataset/source lineage constraints.
