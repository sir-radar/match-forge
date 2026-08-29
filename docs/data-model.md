# Canonical relational data model

## Ownership

PostgreSQL owns provider-neutral identity, source lineage, historical observations, match participation, and the lightweight event catalogue. It does not own raw provider payloads or full analytical event facts; those remain filesystem and Parquet responsibilities.

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

Season provider identity is composite:

```text
provider + provider_competition_id + provider_season_id
```

This permits the same provider season identifier under different competitions without ambiguity.

## Source lineage

`source_snapshots` identifies one immutable provider revision. `source_resources` records each preserved resource path, SHA-256, size, media type, acquisition time, and processing state. Composite foreign keys prevent an observation from claiming a resource belonging to another snapshot or provider.

Source paths must be relative and cannot contain parent traversal. Checksums use a constrained 64-character lowercase hexadecimal domain.

## Canonical and historical records

Canonical tables contain stable identity and relationships only. Mutable names, match status, scores, provider metadata, and similar source facts live in observation tables.

Observation uniqueness prevents the same immutable snapshot from publishing the same provider entity twice. GiST exclusion constraints prevent overlapping system-knowledge intervals for one canonical entity and provider.

Concurrent first-seen identity creation must place canonical-row creation and provider mapping in one transaction. Under contention, PostgreSQL may abort the losing transaction with an exclusion violation or deadlock detection; both preserve one committed canonical identity. The ingestion layer must classify that outcome as retryable and read the winning mapping on retry.

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

Team side and player lineup attributes remain historical observations. Position stints use ordered period/clock intervals; invalid or reversed intervals are rejected.

## Event catalogue boundary

`event_catalog`, `event_provider_mappings`, and `event_observations` retain event identity, match linkage, provider IDs, source ordering, minimal football time, and lineage. Detailed event facts and coordinates remain owned by normalized Parquet datasets.

Within one source snapshot, provider event IDs and `(provider_match_id, event_index)` are unique. Canonical traversal uses `event_index ASC`.

## Migration policy

Production migrations are forward-only. The initial canonical migration has no destructive Down section. Corrections require a new migration.
