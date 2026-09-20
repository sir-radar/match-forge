# StatsBomb La Liga 2015/16 corrected publication retry — 2026-09-09

## Result

```text
Canonical publication: PUBLISHED
Diagnostic dataset qualification: NOT QUALIFIED
```

The corrected canonical publication completed after the prior in-flight
publication was interrupted and rolled back. This record covers that operational
retry only; it does not authorize a diagnostic corpus, forecasts, model fitting,
or promotion.

## Aborted publication and rollback

The original command was:

```text
uv run football --source-git-sha 4b73468fc5b0f1950f9f66fada70ad3a4f9327cb ingest season 27 --competition-id 11
```

Immediately before interruption, its application process (PID `55765`, parent
`55761`) had an observed elapsed runtime of `05:24:43`. It was sent `SIGINT`.
Both processes then exited without PostgreSQL backend cancellation or
termination.

Post-interrupt PostgreSQL checks found:

```text
Old application backend:       NONE
Old transaction:               NONE
Ungranted transaction locks:   0
Detail source snapshot:        NOT REGISTERED
Detail dataset version:        NOT REGISTERED
```

The only pre-retry StatsBomb records for the pinned source revision were the
previously committed catalog and match manifests. The 760-resource detail
manifest was not registered until the corrected transaction committed. This is
consistent with the complete canonical-publication transaction having rolled
back; no manual data repair was performed.

## Retry provenance and runtime

| Item | Value |
| --- | --- |
| Raw source Git SHA | `4b73468fc5b0f1950f9f66fada70ad3a4f9327cb` |
| Corrected execution SHA | `72361ca` |
| Batching fix | `5ee7234` (`perf: batch canonical event publication`) |
| Merge provenance | `72361ca` / merged PR #101 |
| Canonical-code changes after fix | None (`canonical.py` is unchanged from `5ee7234`) |
| Corrected process start | Observed at approximately `2026-09-09T04:31:28Z` |
| Detail source snapshot committed | `2026-09-09T04:34:16.547511Z` |
| Dataset published | `2026-09-09T04:40:06.433560Z` |
| Validation completed | `2026-09-09T04:42:47.557844Z` |
| Total observed run to validation completion | Approximately 11m19s |

The publication code has no per-method runtime telemetry, so an exact
`_publish_event_batch` duration was not available without adding instrumentation
outside this retry's authorized scope. The corrected source structurally invokes
`_publish_event_batch` once for the complete parsed detail bundle; the accepted
fix regression evidence verifies one call for multiple event resources. The
retry's observed PostgreSQL event-stage path was a single stage sequence, with
no repeated per-resource restaging.

## Raw reuse and immutable publication records

The existing detail manifest was reused through `SourceAcquirer`'s established
manifest/resource verification path. The completed retry registered:

```text
Source snapshot:       01a08471-f763-7787-80ca-4293316b7e44
Source manifest SHA-256: f9f437ace6b96b1bf4cc4b5c8263e139ff31016fdb9460a757cdf266d40d88f6
Source resources:      760 / 760 distinct inputs
Dataset version:       670662d6-6ed7-5fa1-ba3c-1cfd561e524f
Dataset identity SHA-256: 5516752680f5863a0efbada19b3208fac3c64efb12fbeaa2c1894767c291d5e4
Dataset manifest SHA-256: cd32d1c44620116cedefc09860efeccb91da19db4e6006ace8b8b6df1dd8e4e0
Normalized event files: 380
```

`uv run football integrity dataset 670662d6-6ed7-5fa1-ba3c-1cfd561e524f`
passed: the registered dataset manifest and every registered dataset file had
the expected SHA-256. The normal StatsBomb validator completed with status
`warnings` and recorded 648 warnings; it did not quarantine the dataset.

## Qualification boundary

Publication does not qualify this dataset for the blocked Sprint 2 diagnostic
route. `sprint2-diagnostic-corpus-resolution-2026-09-08.md` establishes that
the only 380-match eligible competition-season is fully partitioned by the
protected populations:

```text
100 shared-pace admission matches + 280 frozen Sprint 2 targets = 380 matches
```

Therefore a non-empty diagnostic population cannot be disjoint from either
protected population. Its diagnostic population checksum, point-in-time
suitability declaration, and disjointness proof cannot be produced for this
published season. The protected rows were not accessed during this retry.

The dataset is published and has verified immutable lineage, but the required
diagnostic qualification gates are not all satisfied. In particular,
frozen-280 disjointness and 100-match-admission disjointness fail by the
pre-existing cardinality proof. No
`DIAGNOSTIC_DATASET_QUALIFIED_AND_PUBLISHED` result is claimed.
