# Sprint 1 one-match round-trip findings

## Purpose

Validate the Sprint 1 source, identity, temporal, storage, ingestion, validation, lineage, idempotency, and recovery contracts before production implementation.

## Fixture

- Provider: StatsBomb Open Data
- Match: Argentina vs France, 2022 FIFA World Cup Final
- Competition ID: `43`
- Season ID: `106`
- Match ID: `3869685`
- Source Git SHA: `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`
- Attribution: Data provided by StatsBomb

Five pinned resources were acquired and byte-verified: competitions, season matches, events, lineups, and 360.

## Execution

- Tested code Git SHA: `2b293a7051c3e9d4f52afab22da315ed3acbc438`
- Runtime: CPython `3.13.14` arm64 through uv `0.12.1`
- PostgreSQL: `18.6-bookworm`
- PyArrow: `25.0.1`
- Polars: `1.44.1`
- Quality policy: `statsbomb-quality-policy-v1`
- Normalizer: `statsbomb-normalizer-v1`

Final evidence:

- JSON: `.local/prototype/sprint1-roundtrip/reports/ac79bf36-5f06-40de-b88f-dc500433cf4f/PrototypeRoundTripReportV1.json`
- JSON SHA-256: `3b63c647e766471b0ccc45095818943c2219402e89a8b4ab2ec283d549988340`
- Markdown: `.local/prototype/sprint1-roundtrip/reports/ac79bf36-5f06-40de-b88f-dc500433cf4f/PrototypeRoundTripReportV1.md`
- Markdown SHA-256: `746c7ef074f40c42bba82e0a23e9777b8e3449a98d8fe1af77b44e71f006699a`
- Source manifest SHA-256: `5c8b5adf4da329b31bc3e1224823b975efae5cd065bc53f4f91261bcfefa3f93`
- Dataset manifest SHA-256: `bcef5ac3c199af9998334d6ef31eb0f039da91d95f91483a6b95a6d9b7e195ac`

## Observed evidence

- Raw bytes: `12,970,079`; all five resource checksums survived storage and read-back.
- Events: `4,407` raw, `4,407` normalized, `0` quarantined, `0` unexplained difference.
- Lineups: `50` source players, `50` participants, `60` position stints, `8` source cards, `8` stored cards, no unexplained difference.
- 360: `3,683` frames normalized.
- Event and 360 datasets published as versioned Parquet.
- PostgreSQL contained relational identity, mapping, history, lineup, catalogue, quality, and lineage state; full event payloads remained Parquet-owned.
- `34` players referenced by both lineups and events resolved to the same canonical identities.
- Event order survived Parquet read-back; `1,391` duplicate football timestamps demonstrated why `event_index` is authoritative.
- Source coordinates survived unchanged.
- Forward event-to-source and reverse dataset-to-source lineage both passed.
- Historical point-in-time query returned observation A before revision and B afterward; current-state-only query demonstrated the leakage trap.
- Identical second ingestion created zero duplicate source snapshots, resources, entities, mappings, observations, events, dataset inputs, dataset versions, or files.
- Identical rerun modified zero raw files and zero published files.
- Clean rebuild reproduced schema, row count, logical checksum, and physical Parquet checksum.

## Failure-injection matrix

| Injection | Expected | Result |
| --- | --- | --- |
| Source checksum mismatch | Fatal; abort scope | PASS |
| Malformed event JSON | Quarantine resource | PASS |
| Unknown provider event type | Preserve value; null canonical mapping; warn | PASS |
| Out-of-bounds coordinate | Preserve; do not clip; omit derived coordinate; warn | PASS |
| Duplicate event index | Quarantine event component | PASS |
| Unknown additive field | Preserve and continue | PASS |
| Lineup transaction interruption | Roll back all partial rows | PASS |
| Parquet staging interruption | No final artifact; recognizable staging state | PASS |
| Post-publication registration failure | Preserve artifact and reconcile database | PASS |

## Observed deviation

The researched toolchain selected CPython `3.13.15`, but uv `0.12.1` has no managed macOS arm64 build for that version. Gate A changed the pin to CPython `3.13.14`, the newest available uv-managed 3.13 build. [ADR 0001](../adr/0001-python-managed-runtime-pin.md) records the evidence and consequence. All prototype checks were rerun on `3.13.14`.

No other contract change was required.

## Recommendation

`PROCEED`

Gate A passed. Production Sprint 1 data-foundation implementation may begin within the approved boundary. Sprint 2 remains blocked until the production Gate B Definition of Done passes.
