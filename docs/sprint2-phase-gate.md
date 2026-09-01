# Sprint 2 phase gate

Status: **FAIL**

Date: 2026-09-01

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
- Raw batch execution with prior-history fitting, same-batch forecast freezing,
  persistence-before-outcome reveal, and common-target goal/result/corner scoring.
- Four portable model artifacts and four immutable raw forecasts per target, with artifact reload
  validation and retry convergence.
- Exact per-target artifact and forecast identities in retained prediction evidence.
- Common outcome-complete target planning and governed bitemporal outcome availability.
- Evaluation football-cutoff ranges and retry recovery for orphaned immutable artifact manifests.
- Durable preflight failure evidence without fabricated scopes or metrics.
- Pure locked-policy evaluation with predictive, calibration, coverage, reproducibility, and
  regression dimension results, including actuals and thresholds.
- Required subgroup diagnostics retained as deterministic Parquet evidence.
- Equivalent clean-run comparison and recorded artifact reload prediction deltas.

## Verified

`make integration` passed on 2026-09-01:

- Fresh temporary PostgreSQL database created.
- All migrations through `202608302200` applied successfully.
- Second migration pass reported no pending migrations.
- 47 integration tests passed, including governed corner-label publication, immutable batch
  fit/forecast retry, checksum rejection, cross-snapshot kickoff/history resolution, and
  unsupported geography.
- PostgreSQL 18.6, Redis 8.10, and Go operational checks passed.

Final `make check` passed on 2026-09-01:

- Ruff formatting and lint passed.
- Strict MyPy passed for 85 source files.
- Static health analysis reported 0 issues.
- 158 Python tests passed.
- Rust formatting, lint, test, and build passed.
- Go vet, lint, test, and build passed.
- Migration and shell validation passed.
- Python source distribution and wheel built successfully.

## Locked policy result

Sprint 2 remains `FAIL`. This is now a predictive result, not an evidence-production gap.

- Elo and Dixon-Coles 1X2 comparisons satisfy their non-inferiority limits; at least one improves
  both Log Loss and RPS.
- Dixon-Coles goal NLL and CRPS deltas are exactly `0.0`; non-inferiority passes, but the required
  point-estimate improvement does not.
- Corner Poisson NLL upper delta is `0.1334293494138387` against `0.03`.
- Corner Poisson CRPS upper delta is `0.2042466708474623` against `0.05`.
- Corner Poisson point deltas are `+0.07474906843946444` NLL and
  `+0.11220273633078141` CRPS, so neither improves.
- Corner MAE point delta is `+0.13830595219167047`, within the `+0.15` limit.

No threshold changed. No baseline or calibration artifact was promoted.

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
`verified_existing`. The post-label preflight produced evaluation run
`17bbf737-b235-557f-b882-8b6ef5951740`; later clean-tree execution advanced beyond this stage.

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
280/280 targets. The plan is the immutable input to the retained model-execution evidence.

Clean-tree review run `f348f40b-3935-5a33-922b-a539c99b0353` retained 280 predictions and
outcomes, 24,000 paired-bootstrap rows, 1,680 chronological calibration predictions, 200
calibration bins, and six calibration comparisons. Raw Dixon-Coles 1X2 log loss was
`1.0817300589925896`, Brier score was `0.6546549038961231`, and RPS was
`0.22571978686699795`. Equivalent clean run `009e3660-20d4-506e-bc87-4c84096ce52f` retained the
same target set and identical prediction, outcome, metric, bootstrap, and calibration file hashes.
These immutable runs remain unchanged; new complete runs record the policy decision separately in
their own report.

## Operator command

```bash
make sprint2-evaluate
```

The command retains:

```text
.local/reports/sprint2/run=<evaluation-run-id>/Sprint2EvaluationReportV1.json
.local/reports/sprint2/run=<evaluation-run-id>/Sprint2EvaluationReportV1.md
.local/reports/sprint2/run=<evaluation-run-id>/Sprint2EvaluationEvidenceManifestV1.json
.local/reports/sprint2/run=<evaluation-run-id>/subgroup_diagnostics.parquet
.local/reports/sprint2/run=<evaluation-run-id>/*.parquet
.local/reports/sprint2/run=<evaluation-run-id>/*.svg
```

Underlying CLI exit code `7` means `FAIL`; Make reports a failed target. The report identifies the
first blocking stage. A missing approved corpus is `corpus-resolution`; insufficient scored matches
is `coverage`; unresolved timezone-safe ordering is `chronology-resolution`; corner-label coverage
below 95% is `corner-label-coverage`; ambiguous dataset provenance is `execution-lineage`; an
undersized frozen target set is `target-plan-coverage`; and a model or publication failure is
`walk-forward-execution`. A complete run retains raw predictions, outcomes, proper scores, paired
chronological moving-block bootstrap evidence, chronological calibration diagnostics, subgroup
diagnostics, and plots, then applies `Sprint2BaselineGatePolicyV1` at stage `complete`. The first
clean run for a new Git commit records insufficient reproduction; a second equivalent clean run can
satisfy that dimension. Predictive failures still keep this corpus at `FAIL`. No failed preflight
emits placeholder model metrics.

## Required next gate action

Retain the failed result and review model changes against the same locked policy. Do not move
thresholds, promote any model, or begin a later phase. Any challenger requires new immutable
evidence and the same phase-gate review.
