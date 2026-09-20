# StatsBomb canonical-event staging performance investigation — 2026-09-09

## Scope and boundaries

This is a read-only investigation of the active StatsBomb La Liga 2015/16
canonical-event staging transaction. The publication process was not cancelled,
restarted, configured, or otherwise modified. No model, forecast, protected
target, or admission-population data was inspected.

Source: StatsBomb Open Data, competition `11`, season `27`, commit
`4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`.

Code SHA: `c733cc34be07009c8f5f1948123f075b35b63291`.

At investigation time, raw acquisition had completed for 380 matches and 760
detail resources, and the immutable detail manifest was present. The detail
source snapshot and dataset version were not yet committed because the complete
canonicalization transaction remained open.

## Runtime samples

| Sample (UTC) | Backend | Transaction age | Statement age | State | Wait | Lock blockers | Statement shape |
| --- | ---: | ---: | ---: | --- | --- | ---: | --- |
| 2026-09-09 02:31:40 | 597364 | 3h25m | 1m03s | active | none | 0 | stage update from `event_observations` |
| 2026-09-09 02:33:52 | 597364 | 3h27m | 26s | active | none | 0 | same stage update |
| 2026-09-09 02:35:28 | 597364 | 3h28m | 1m36s | active | none | 0 | same stage update |

The backend held the provider advisory lock and normal transactional relation
locks. `pg_locks` reported no ungranted lock for that backend and the explicit
blocker query returned `lock_blocker_count = 0`.

The active statement is the correlated update at
`python/football/src/football/ingestion/canonical.py:593`:

```sql
UPDATE football_event_stage AS stage
SET (...) = (
    SELECT ...
    FROM football.event_observations AS observation
    WHERE observation.source_snapshot_id = $1
      AND observation.provider_event_id = stage.provider_event_id
)
```

## Application path and transaction shape

```text
football.cli.application.FootballApplication.ingest_season
  -> StatsBombCanonicalIngestor.ingest
  -> _CanonicalWriter.ingest
  -> _CanonicalWriter._events                 (once per event resource)
  -> _CanonicalWriter._publish_event_batch    (once per match/event file)
  -> UPDATE football_event_stage ... event_observations
```

`StatsBombCanonicalIngestor.ingest` opens one transaction for the complete
parsed bundle (`canonical.py:65-81`). `_CanonicalWriter.ingest` loops over every
event resource (`canonical.py:97-104`). The selected season has 380 event
resources, so `_publish_event_batch` repeats the temp-table creation check,
truncate, COPY, ANALYZE, mapping update, observation update, checks, and inserts
up to 380 times within that one transaction.

The samples show the same observation-stage update on multiple occasions while
the overall transaction remained open for more than three hours. This is
evidence of repeated batch work, not a single lock wait. The exact completed
call count and per-call timings cannot be recovered because `pg_stat_statements`
is not installed and the temporary stage table is private to the active session.

## Relation and index evidence

| Relation | Estimated rows | Table size | Total size |
| --- | ---: | ---: | ---: |
| `football.event_observations` | 1,313,761 | 427 MB | 1,050 MB |
| `football.event_provider_mappings` | 1,313,773 | 245 MB | 439 MB |
| `football.event_catalog` | 1,313,773 | 100 MB | 219 MB |

The active observation predicate is `INDEX_SUPPORTED`: the unique btree index
`event_observations_source_snapshot_id_provider_event_id_key` matches
`(source_snapshot_id, provider_event_id)`. A non-executing closest-shape plan
used that index for the correlated lookup (estimated one row, cost `0.55..8.57`
per lookup). The actual temp-table update could not be explained directly
without accessing the active session; therefore that plan is supporting, not
conclusive, evidence for the live statement.

The corresponding mapping predicate is also `INDEX_SUPPORTED` by
`event_provider_mappings_provider_id_provider_event_id_key`.

Historical statistics show substantial cumulative sequential scanning:
`event_observations` reports 199,755 sequential scans and 1,865,162,711 tuples
read; `event_provider_mappings` reports 81,295 scans and 620,845,037 tuples
read. Those counters are database-wide and cannot be attributed solely to this
publication, but they make repeated whole-relation work a material risk. No
JSON/JSONB predicate is present in the observed statement.

No user-defined triggers exist on the three material event tables. Foreign keys,
unique indexes, and the GiST exclusion constraint are maintained for inserts,
but this investigation has no basis to call them the dominant cost.

## I/O and statistics

`pg_stat_statements` is unavailable. Database statistics show no deadlocks and
approximately 565M buffer hits versus 1.38M reads. The event-observation table
has 83.9M heap hits, 426k heap reads, 30.6M index hits, and 419k index reads.
There is some historical temporary work (17 files / 87 MB), but no sampled
evidence ties a spill to the active update. The evidence does not support a
primary lock, JSON-expression, or storage-I/O classification.

## Diagnosis

Primary bottleneck: **D. EXCESSIVE_WORK_AMPLIFICATION**.

The event writer performs a complete staging-publication sequence separately for
each of 380 match event resources while retaining one multi-hour transaction.
The same correlated observation update was sampled repeatedly. Each pass works
against event relations with roughly 1.31M rows and performs repeated staging,
planning, constraint/index maintenance, and transaction-local writes. The
logical workload is one 380-match season; the database work is multiplied by
the per-match batching loop.

Secondary bottleneck: **F. TRANSACTION_OR_WRITE_AMPLIFICATION**. The one
transaction spans the full bundle, retaining all event inserts, indexes, and
visibility changes until completion. No N+1 classification is made: entity
lookups are deduplicated within each event resource and this investigation did
not collect statement-call telemetry for them.

Evidence strength: **MODERATE**. The repeated call path, active-query samples,
transaction duration, and workload scale are direct evidence. Exact per-query
runtime and live update plan are unavailable without `pg_stat_statements` or
interaction with the active session, both outside this route.

## Recommended smallest correction (not implemented)

Change `_CanonicalWriter.ingest` to accumulate the already parsed event rows for
the selected bundle and call `_publish_event_batch` once for the complete detail
batch, preserving the existing stage schema and set-based SQL. This directly
removes up to 379 repeated staging cycles without changing raw resources,
manifest identity, canonical IDs, source lineage, snapshot semantics, or dataset
identity.

Expected effect: materially lower publication runtime by eliminating repeated
temp-table/COPY/ANALYZE/update/insert cycles. The exact improvement requires a
separate implementation and equivalence verification. Correctness impact:
**NONE EXPECTED, subject to equivalence verification**.

## Limitations

The active publication remains in progress. The evidence report is uncommitted.
No `EXPLAIN ANALYZE`, active-session setting change, maintenance command, index
change, publication rerun, or production-code change was performed.
