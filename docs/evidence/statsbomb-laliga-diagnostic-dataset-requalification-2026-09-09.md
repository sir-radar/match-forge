# StatsBomb La Liga diagnostic-dataset requalification — 2026-09-09

## Result

```text
DIAGNOSTIC_DATASET_REQUALIFICATION_FAIL
First failed gate: POINT_IN_TIME_SUITABILITY
Exact blocker: LIFECYCLE_COMPLETION_CONTRACT_UNSATISFIED
```

This is a bounded, read-only requalification. It did not republish data, create
claims, access protected outcomes, run diagnostics, fit a challenger, or alter
Sprint 2.

## Published dataset identity

```text
Provider:                    StatsBomb Open Data
Competition:                 La Liga
Season:                      2015/2016
Canonical competition ID:    01a051db-552e-782d-b2ac-b3f0ec58441b
Canonical season ID:         01a051db-553a-754a-9560-d79eceeb72b6
Dataset version:             670662d6-6ed7-5fa1-ba3c-1cfd561e524f
Source snapshot:             01a08471-f763-7787-80ca-4293316b7e44
Dataset identity SHA-256:    5516752680f5863a0efbada19b3208fac3c64efb12fbeaa2c1894767c291d5e4
Source manifest SHA-256:     f9f437ace6b96b1bf4cc4b5c8263e139ff31016fdb9460a757cdf266d40d88f6
Dataset manifest SHA-256:    cd32d1c44620116cedefc09860efeccb91da19db4e6006ace8b8b6df1dd8e4e
```

Publication remains `PUBLISHED`. The retained `football integrity dataset` run
passed for the manifest and every registered file. The sole validator run has
status `warnings`, not `quarantined` or `failed`.

## Corrected protected-population scope

The prior rejection incorrectly applied the Premier League 2015/16 cardinality
proof to La Liga 2015/16. Its exact scope is:

```text
Premier League competition ID: 01a051db-5565-70d1-85d4-ab6342d86baf
Premier League season ID:      01a051db-5566-7286-8ad7-40d945ab8253
Dataset version:              d62b97d6-f39b-5f14-9773-61f57f7b677b
Source snapshot:              01a0534c-cb84-702b-8249-a0a572a2f280
```

That corpus contains the 100-match admission population
`8f3813c9fa6d2053d3916e6ee242d7c3497da85745ad6fe614a5ec1f87b79f25`
and frozen target plan
`c5b9ff5860d9d00d55ab58fe3dc044d41d95af49501d27275fdc2e0831bff362`.

```text
Original 100 + 280 = 380 proof: Premier League 2015/16 only
Does it apply to La Liga 2015/16: NO
Previous cardinality rejection: INVALIDATED BY CORRECTED COMPETITION/SEASON IDENTITY
La Liga vs 100-match admission intersection: 0
La Liga vs frozen-280 intersection:           0
Protected population overlap: PASS
```

The zero intersections follow from distinct canonical competition and season
identities. A metadata-only canonical-ID intersection of the complete La Liga
and Premier League seasons is zero, and both protected populations are retained
subsets of that Premier League season. Protected outcomes were not loaded.

## Passing checks

```text
SEASON_COMPLETENESS: PASS
```

The immutable StatsBomb `data/matches/11/27.json` resource contains 380 match
records. Canonical metadata contains 380 La Liga 2015/16 matches, so the
missing canonical-match count is zero.

```text
CANONICAL_IDENTITY_AND_PUBLICATION_INTEGRITY: PASS
```

The publication has 380 distinct dataset files, 380 StatsBomb provider-match
mappings, and 380 current StatsBomb match observations. Aggregate checks found
zero missing or equal home/away team identities, zero missing local date/time
kickoffs, and zero null or negative scores. Dataset/source lineage binds 760
distinct source resources. Manifest and file integrity passed.

```text
MINIMUM_SAMPLE_REQUIREMENT: PASS
```

The canonical match count is 380, exceeding the 120-match threshold.

## Validator findings

All 648 findings are `WARNING` under
`schemas/quality/statsbomb-quality-policy-v1.json`; none is `FATAL` or
`QUARANTINE`.

| Rule | Count | Policy action |
| --- | ---: | --- |
| `SB_EVENT_LOCATION_OUT_OF_BOUNDS` | 9 | Exclude from derived spatial features |
| `SB_IMPOSSIBLE_EVENT_TIMESTAMP` | 126 | Use event index and exclude temporal features |
| `SB_NONMONOTONIC_POSITION_STINT` | 66 | Preserve and review |
| `SB_UNKNOWN_EVENT_TYPE` | 447 | Preserve with null canonical mapping |

```text
Validator classification: WARNINGS_RETAINED
Hard validator qualification blocker: NONE
```

## Point-in-time suitability blocker

The current lifecycle contract, `statsbomb-terminal-event-score-v1`, requires
exactly two period-2 `Half End` events and a maximum period of two before it
can publish a `completed` lifecycle claim. That claim is the existing
point-in-time provider's completed-history and outcome-exposure boundary.

For this La Liga source snapshot, every one of the 380 matches has four unique
period-2 `Half End` events (1,520 total). There are no duplicate provider event
identities and maximum period remains two, so this is a provider representation
incompatible with the existing exact-two-terminal-events rule, not duplicate
canonical data.

The existing lifecycle publisher would reject every La Liga match before a
completed lifecycle claim could be registered. The published dataset therefore
has zero lifecycle claims under that contract. Without those claims, the
existing point-in-time provider cannot establish eligible completed history or
a separated outcome-exposure boundary for this dataset.

```text
POINT_IN_TIME_SUITABILITY: FAIL
Reason: existing completed-lifecycle contract cannot represent the retained
        four-terminal-event La Liga evidence.
```

No lifecycle interpretation, source correction, or claim contract was
introduced here. A provider-compatible lifecycle-contract decision and its
validation require separate authorization.

## Reproducibility

```text
Publication execution SHA: 72361ca
Batching correction:       5ee7234
Source Git SHA:            4b73468fc5b0f1950f9f66fada70ad3a4f9327cb
Dataset version:           670662d6-6ed7-5fa1-ba3c-1cfd561e524f
Source snapshot:           01a08471-f763-7787-80ca-4293316b7e44
uv.lock SHA-256:           d14def6539f213b2af3011975062ed3e1e0bba2d86e8064803bd3d86d0a39e4e
```

## Boundaries retained

```text
Frozen target outcomes:            NOT ACCESSED
Existing admission population:     NOT REUSED
Shared-pace admission:             NOT RERUN
Candidate challengers:             NOT FIT
Frozen-DCv3 diagnostics:           NOT RUN
Authoritative evaluation:          NOT RUN / NOT AUTHORIZED
Sprint 2:                          FAIL
Model promoted:                    false
Phase 3:                           BLOCKED / UNAUTHORIZED
```
