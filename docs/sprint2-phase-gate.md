# Sprint 2 phase gate

Status: **FAIL**

Date: 2026-08-31

## Implemented

- Point-in-time dataset and label-free forecast contexts.
- Elo, Dixon-Coles goal products, and Poisson/NB2 corner baselines.
- Portable immutable model artifacts with compatibility and reload verification.
- Immutable forecast publication with exact model and context identities.
- Chronological walk-forward windows and same-kickoff batching.
- Match-result proper scores, reliability analysis, Platt calibration, and isotonic calibration.
- Immutable evaluation reports and governed promotion events.
- Operator entry points: `football evaluate sprint2` and `make sprint2-evaluate`.
- Versioned immutable lifecycle claims with exact score, event-resource, dataset-file, and
  validation lineage.
- Versioned immutable kickoff claims with exact local-time, competition, timezone-data, and
  lifecycle lineage.
- Versioned immutable corner labels with exact event semantics, canonical team attribution,
  dataset checksums, validator evidence, and lifecycle lineage.
- Immutable label-free walk-forward target plan with prior-batch 10-match team and 100-match
  competition history eligibility, separate outcome reveal, and exact target checksum.
- Durable preflight failure evidence without fabricated scopes or metrics.

## Verified

`make integration` passed on 2026-08-31:

- Fresh temporary PostgreSQL database created.
- All migrations through `202608302200` applied successfully.
- Second migration pass reported no pending migrations.
- 46 integration tests passed, including governed corner-label publication, immutable retry,
  checksum rejection, cross-snapshot kickoff/history resolution, and unsupported geography.
- PostgreSQL 18.6, Redis 8.10, and Go operational checks passed.

Final `make check` passed on 2026-08-31:

- Ruff formatting and lint passed.
- Strict MyPy passed for 74 source files.
- Static health analysis reported 0 issues.
- 138 Python tests passed.
- Rust formatting, lint, test, and build passed.
- Go vet, lint, test, and build passed.
- Migration and shell validation passed.
- Python source distribution and wheel built successfully.

## Blocking evidence gap

Sprint 2 cannot receive `PASS` or model promotion yet. Repository has no completed end-to-end run
that repeatedly fits the baseline models on canonical historical windows, freezes forecasts before
outcome reveal, scores those out-of-sample forecasts, compares calibration challengers, and
publishes real evaluation metrics and calibration plots.

Implementation and deterministic tests pass, but implementation is not predictive-quality
evidence. No model artifact is approved by this gate.

## Executed phase gate

Before kickoff resolution, `make sprint2-evaluate` retained run
`c5c39fe9-babc-576f-b440-b35cb5b5a994` at `chronology-resolution`: all 380 scored targets had
timezone-naive local date/time but 0 governed UTC instants.

`football resolve sprint2-kickoffs` then published 380 claims across 199 chronological batches. An
identical retry returned `verified_existing`.

`football resolve sprint2-corners` published 380 labels from 4,107 exact StatsBomb corner-pass
events. All 380 labels have distinct deterministic hashes, lifecycle claims, event resources, and
dataset files; all resolve to one dataset and validator run. Match totals range from 1 to 25, and
13 matches legitimately contain a zero count for one team. An identical retry returned
`verified_existing`. The post-label gate produced evaluation run
`17bbf737-b235-557f-b882-8b6ef5951740`.

```text
Status: FAIL
Stage: walk-forward-execution
Registered matches: 380
Completed matches: 380
Scored targets: 380
Corner-labelled targets: 380
```

The pinned StatsBomb revision
`b0bc9f22dd77c206ddedc1d742893b3bbe64baec` supplied the EPL 2015/16 match list at
`data/matches/2/27.json`; the catalog omits that pair, so ingestion used the explicit
`--competition-id 2` contract and preserved match-list lineage. Full detail ingestion completed for
762 immutable resources and published:

```text
Source snapshot: 01a0534c-cb84-702b-8249-a0a572a2f280
Dataset version: d62b97d6-f39b-5f14-9773-61f57f7b677b
Matches: 380
Event observations: 1,313,773
```

Contradictory same-revision player facts no longer force an arbitrary winner. Exact lineup and event
variants retain snapshot/resource lineage in `player_source_facts`; disputed canonical fields are
null with `fact_status = 'conflicting'`. Validator v3 also corrected StatsBomb paired own-goal
semantics by counting `Own Goal For` once and not double-counting its paired `Own Goal Against`
event. Validation run `0a470aa5-5627-5ddb-ac35-ef650398422f` completed with `warnings` and 749
findings:

```text
SB_CONFLICTING_PLAYER_FACT:        7
SB_EVENT_LOCATION_OUT_OF_BOUNDS:   3
SB_IMPOSSIBLE_EVENT_TIMESTAMP:    139
SB_NONMONOTONIC_POSITION_STINT:    74
SB_UNKNOWN_EVENT_TYPE:            526
```

StatsBomb's `match_status=available` remains a data-availability status and is not mapped to football
completion. Instead, `football resolve sprint2-lifecycle` published 380 claims under
`statsbomb-terminal-event-score-v1`. Each claim binds an exact scored match observation, event
resource, normalized dataset file, validator v3 run, and regulation-time terminal-event evidence.
The raw provider observations remain `lifecycle = 'unknown'`.

All 380 claims have exactly two period-2 `Half End` events, maximum period 2, distinct match
observations, distinct event resources, distinct dataset files, and deterministic evidence hashes.
A repeated publication returned `verified_existing` for all 380 claims. Coverage therefore passes;
the added chronology preflight then exposed the missing timezone-safe ordering before any model fit.

All 380 match observations also contain a local date and local time but no provider timezone.
`statsbomb-england-local-kickoff-v1` binds each exact lifecycle claim and match observation to the
domestic England competition observation, `Europe/London`, pinned `tzdata 2026.3`, and an exact
TZif checksum. The resulting 380 distinct claim hashes cover 199 UTC batches from
`2015-08-08T12:45:00Z` through `2016-05-17T20:00:00Z`. All 380 raw
`match_observations.kickoff_at` values remain null.

`statsbomb-pass-type-61-corner-v1` counts only events whose provider event type is exactly
ID/name `30` / `Pass` and whose nested pass type is exactly ID/name `61` / `Corner`. This excludes
other events whose payload says `From Corner`. Labels remain separate from provider observations
and label-free forecast contexts. The gate now stops at `corner-label-coverage` unless at least 95%
of scored targets have governed labels; it no longer advances with a hard-coded zero label count.

`WalkForwardTargetPlanV1` then resolved 280 eligible targets after 100 warm-up exclusions, across
146 eligible kickoff batches from `2015-10-31T13:45:00Z` through `2016-05-17T20:00:00Z`. Minimum
eligible home-team, away-team, and competition histories are exactly 10, 10, and 100. Target-set
checksum `c5b9ff5860d9d00d55ab58fe3dc044d41d95af49501d27275fdc2e0831bff362` reproduced, immutable
publication retry returned `verified_existing`, and separate governed outcome reveal covered
280/280 targets. This freezes the evaluation universe but is not model execution evidence.

## Operator command

```bash
make sprint2-evaluate
```

The command retains:

```text
.local/reports/sprint2/run=<evaluation-run-id>/Sprint2EvaluationReportV1.json
.local/reports/sprint2/run=<evaluation-run-id>/Sprint2EvaluationReportV1.md
```

Underlying CLI exit code `7` means `FAIL`; Make reports a failed target. The report identifies the
first blocking stage. A missing approved corpus is `corpus-resolution`; insufficient scored matches
is `coverage`; unresolved timezone-safe ordering is `chronology-resolution`; corner-label coverage
below 95% is `corner-label-coverage`; missing retained model execution is
`walk-forward-execution`. No failed preflight emits placeholder model metrics.

## Required next gate action

Run the complete retained chronological evaluation: repeated model fitting, forecast-before-outcome
persistence, proper scoring, calibration analysis, subgroup regressions, and promotion review. Stop
for review after that gate evidence is produced. No later phase is authorized while status remains
`FAIL`.
