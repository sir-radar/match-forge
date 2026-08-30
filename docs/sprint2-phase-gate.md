# Sprint 2 phase gate

Status: **FAIL**

Date: 2026-08-30

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
- Durable preflight failure evidence without fabricated scopes or metrics.

## Verified

`make integration` passed on 2026-08-30:

- Fresh temporary PostgreSQL database created.
- All migrations through `202608302000` applied successfully.
- Second migration pass reported no pending migrations.
- 44 integration tests passed.
- PostgreSQL 18.6, Redis 8.10, and Go operational checks passed.

Final `make check` passed on 2026-08-30:

- Ruff formatting and lint passed.
- Strict MyPy passed for 70 source files.
- Static health analysis reported 0 issues.
- 125 Python tests passed.
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

`make sprint2-evaluate` ran after immutable lifecycle claims were registered and produced evaluation
run `cdd5cbd8-c38f-5b7f-a380-439151603f51`.

```text
Status: FAIL
Stage: walk-forward-execution
Registered matches: 380
Completed matches: 380
Scored targets: 380
Corner-labelled targets: 0
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
A repeated publication returned `verified_existing` for all 380 claims. Gate run
`cdd5cbd8-c38f-5b7f-a380-439151603f51` therefore passed coverage and remains `FAIL` at
`walk-forward-execution`: no complete retained chronological evaluation exists. No walk-forward fit
or score ran. Scope and metric fields remain `null`, preserving the distinction between missing
evidence and measured zero performance. The retained JSON report validates against
`Sprint2EvaluationReportV1`.

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
is `coverage`; missing retained chronological evidence is `walk-forward-execution`. No failed
preflight emits placeholder model metrics.

## Required next gate action

Run the complete retained chronological evaluation: repeated model fitting, forecast-before-outcome
persistence, proper scoring, calibration analysis, subgroup regressions, and promotion review. Stop
for review after that gate evidence is produced. No later phase is authorized while status remains
`FAIL`.
