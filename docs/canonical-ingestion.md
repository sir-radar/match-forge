# Canonical ingestion

## Boundary

`football.ingestion.StatsBombCanonicalIngestor` consumes an `AcquisitionResult` and a PostgreSQL connection. It supports StatsBomb competition, season-match, and lineup resources. Event and 360 resources are registered with pending processing state for later phases.

Before opening a database transaction, ingestion re-reads the immutable manifest and every declared raw resource. Paths must remain beneath the configured data root, symlinks are rejected, reads are bounded, and sizes and SHA-256 checksums must match the manifest.

## Transaction and lineage

One transaction registers the provider, acquisition-manifest scope, and resources, then publishes all canonical rows, provider mappings, observations, and lineup hierarchy. Parsing, missing mappings, inconsistent teams, temporal ordering errors, and database failures cannot leave partial source registration or canonical state.

The deterministic manifest scope directory is stored as `source_identity`. Distinct scopes at the same pinned Git revision therefore remain independently registered. An identical completed rerun reuses the same source snapshot and creates no duplicate canonical, mapping, observation, participation, stint, or card rows.

Successfully consumed resources move to `parse_status = 'parsed'` and `validation_status = 'valid'`. A source snapshot becomes `validated` only when none of its resources remain pending.

## Canonical publication order

```text
competitions → seasons → teams → matches → match teams
                                      ↓
                         players → lineup participation
                                      ↓
                           position stints and cards
```

Canonical UUIDs stay provider-neutral. Provider identifiers live in mapping and observation tables. Advisory transaction locks serialize first-seen identity publication for each provider entity. Later snapshots reuse mappings, advance `last_seen_at`, close the previous half-open knowledge interval, and publish a new source-linked observation.

Provider timestamps are parsed into `TIMESTAMPTZ` only when the source includes a timezone. Raw text is always retained when present; timezone-naive StatsBomb timestamps remain raw-only.

## Validation behavior

Required identifiers, JSON shapes, dates, local times, scores, lineup membership, jersey numbers, cards, and position intervals are validated before publication. A lineup must contain exactly the match's two current teams. Duplicate players, conflicting same-snapshot entity facts, and reversed position intervals fail the whole ingestion. Raw bytes remain available for the later data-quality and quarantine phase; canonical ingestion never silently drops invalid lineup facts.
