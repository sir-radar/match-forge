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
- Durable preflight failure evidence without fabricated scopes or metrics.

## Verified

`make integration` passed on 2026-08-30:

- Fresh temporary PostgreSQL database created.
- All migrations through `202608300200` applied successfully.
- Second migration pass reported no pending migrations.
- 40 integration tests passed.
- PostgreSQL 18.6, Redis 8.10, and Go operational checks passed.

Final `make check` passed on 2026-08-30:

- Ruff formatting and lint passed.
- Strict MyPy passed for 69 source files.
- Static health analysis reported 0 issues.
- 124 Python tests passed.
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

`make sprint2-evaluate` ran after the approved match corpus was registered and produced evaluation
run `304bde88-6bfe-56bd-a051-0fc3d145a979`.

```text
Status: FAIL
Stage: coverage
Registered matches: 380
Completed matches: 0
Scored targets: 0
Corner-labelled targets: 0
```

The pinned StatsBomb revision
`b0bc9f22dd77c206ddedc1d742893b3bbe64baec` supplied the EPL 2015/16 match list at
`data/matches/2/27.json`; the catalog omits that pair, so ingestion used the explicit
`--competition-id 2` contract and preserved match-list lineage. All 380 canonical matches and their
scores are registered. Their football lifecycle remains `unknown`, however, because StatsBomb's
`match_status=available` is a data-availability status rather than an approved mapping to
`completed`. The gate therefore correctly excludes all 380 from scored evaluation coverage.

Full detail acquisition completed with 762 immutable raw resources and three source manifests, but
canonical detail ingestion stopped before event publication at:

```text
error: player 3649 has conflicting source facts
```

The source contains contradictory same-revision player metadata. Examples include Karl Darlow
country IDs `68` (England) and `249` (Wales), Demarai Gray country IDs `68` (England) and `113`
(Jamaica), and differing player-name spellings. The canonical writer rejects those conflicts rather
than silently selecting or repairing an authoritative fact. No partial event dataset was published.
No walk-forward fit or score ran. Scope and metric fields remain `null`, preserving the distinction
between missing evidence and measured zero performance. The retained JSON report validates against
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
is `coverage`. No failed preflight emits placeholder model metrics.

## Required next gate action

Resolve and version two data-contract decisions before another authoritative run:

1. map a trustworthy source fact to football lifecycle `completed` without treating
   StatsBomb data-availability status as football lifecycle; and
2. define explicit, lineage-preserving handling for contradictory player facts within one pinned
   source revision without silently choosing a winner.

Then publish the approved event dataset and rerun `make sprint2-evaluate`. The gate must next
complete chronological model fitting, forecast-before-outcome persistence, proper scoring,
calibration analysis, subgroup regressions, and promotion review. No later phase is authorized
while status remains `FAIL`.
