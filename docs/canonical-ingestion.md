# Canonical ingestion

## Boundary

`football.ingestion.StatsBombCanonicalIngestor` consumes an `AcquisitionResult` and a PostgreSQL connection. It supports StatsBomb competition, season-match, lineup, and event resources. 360 resources are registered with pending processing state for a later phase.

Before opening a database transaction, ingestion re-reads the immutable manifest and every declared raw resource. Paths must remain beneath the configured data root, symlinks are rejected, reads are bounded, and sizes and SHA-256 checksums must match the manifest.

## Transaction and lineage

One transaction registers the provider, acquisition-manifest scope, and resources, then publishes all canonical rows, provider mappings, observations, lineup hierarchy, and event catalogue entries. Parsing, missing mappings, inconsistent teams, temporal ordering errors, and database failures cannot leave partial source registration or canonical state.

The deterministic manifest scope directory is stored as `source_identity`. Distinct scopes at the same pinned Git revision therefore remain independently registered. An identical completed rerun reuses the same source snapshot and creates no duplicate canonical, mapping, observation, participation, stint, or card rows.

Successfully consumed resources move to `parse_status = 'parsed'` and `validation_status = 'valid'`. A source snapshot becomes `validated` only when none of its resources remain pending.

## Canonical publication order

```text
competitions → seasons → teams → matches → match teams
                                      ↓
                         players → lineup participation
                                      ↓
                           position stints and cards
                                      ↓
                         ordered event catalogue
```

Canonical UUIDs stay provider-neutral. Provider identifiers live in mapping and observation tables. One provider-scoped advisory transaction lock serializes canonical publication without consuming one PostgreSQL lock per event. Event resources resolve referenced entities once, stage each match through PostgreSQL `COPY`, and publish mappings and observations with set-based statements. Later snapshots reuse mappings, advance `last_seen_at`, close the previous half-open knowledge interval, and publish a new source-linked observation.

Provider timestamps are parsed into `TIMESTAMPTZ` only when the source includes a timezone. Raw text is always retained when present; timezone-naive StatsBomb timestamps remain raw-only.

## Validation behavior

Required identifiers, JSON shapes, dates, local times, scores, lineup membership, jersey numbers, cards, event UUIDs, event clocks, periods, and source indexes are validated before publication. A lineup must contain exactly the match's two current teams. Event and possession teams must belong to the event's match. Duplicate players, event IDs, event resources, per-match event indexes, and conflicting same-snapshot event facts fail the whole ingestion.

Contradictory player metadata is preserved differently because the pinned source can legitimately
contain multiple variants for one provider player. Every lineup and event variant is registered in
`player_source_facts` with exact snapshot and resource lineage. Canonical player fields contain only
single-valued consensus; a disputed field is `NULL` and `fact_status` is `conflicting`. Validation
emits `SB_CONFLICTING_PLAYER_FACT` with all variants instead of selecting a winner or rewriting raw
provider bytes.

StatsBomb position `from`/`to` values are preserved as provider observations. Real source rows can be non-monotonic across periods and clocks, so ingestion validates presence, shape, positivity, and paired nullability without inventing corrected intervals. Raw bytes remain available for the later data-quality and quarantine phase.

Event resources can be ingested with their match bundle or as a later manifest scope. Existing rich team and player observations are reused; an event-only scope does not replace them with partial event references. New event observations close prior half-open knowledge intervals while retaining stable event identity and match linkage.
