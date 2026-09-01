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
- Dixon-Coles v2 analytic-gradient fitting with fail-closed projected-gradient stationarity checks;
  legacy v1 artifacts remain immutable and loadable.
- Dixon-Coles v3 centered team-effect shrinkage selected only from chronological folds inside the
  100-match pre-evaluation training window; v1 and v2 artifacts remain immutable and loadable.
- Corner v2 team-effect shrinkage selected only from chronological folds inside the 100-match
  pre-evaluation training window.

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
- Strict MyPy passed for 87 source files.
- Static health analysis reported 0 issues.
- 165 Python tests passed.
- Rust formatting, lint, test, and build passed.
- Go vet, lint, test, and build passed.
- Migration and shell validation passed.
- Python source distribution and wheel built successfully.

## Locked policy result

Sprint 2 remains `FAIL`. Dixon-Coles v3 clears every prior predictive and calibration blocker, but
the locked total-goal CRPS uncertainty limit still rejects the baseline.

- Elo passes: Log Loss upper delta is `-0.002278372399708321` and RPS upper delta is
  `-0.0070044470485929695`.
- Dixon-Coles 1X2 passes: Log Loss upper delta is `-0.022486676168745324`, RPS upper delta is
  `-0.00964547950364307`, and the point-improvement requirement passes.
- Dixon-Coles goal joint-NLL passes with upper delta `-0.008999741311145601`; its NLL point delta
  improves by `-0.051053914316576854`, satisfying the policy's at-least-one proper-score point
  improvement check; and MAE delta passes at `0.015090145608229135`.
- Dixon-Coles total-goal CRPS upper delta is `0.04227649806467279` against `0.02`, the sole
  predictive blocker. Its point delta is also inferior at `+0.01763435119191425`.
- Corner Poisson now passes every locked predictive check: NLL upper delta
  `0.010213157951468797`, CRPS upper delta `0.01626512742751341`, point improvement
  `-0.00390558919980915`, and MAE delta `-0.010237161540371936`.
- Calibration passes: 1X2 macro ECE is `0.04145927309850988`, over-2.5 ECE is
  `0.06437202688037094`, BTTS ECE is `0.038261377483660326`, and maximum absolute bias is
  `0.03976628154312785`.
- Coverage and regression dimensions pass with 280/280 targets and zero leakage, probability,
  normalization, runtime, test, bypass, or regression-budget failures. Equivalent clean runs are
  required to close reproducibility for the final commit.

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
Stage: complete
Registered matches: 380
Completed matches: 380
Scored targets: 380
Corner-labelled targets: 380
Walk-forward targets: 280
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

The remediation review did not alter the target plan, policy thresholds, retained v1 evidence, or
promotion state. Dixon-Coles v2 replaces the false-success finite-difference fit with analytic
SLSQP and rejects non-stationary solver success. Corner v2 applies the training-only selected
regularization strength `256.0`. Dixon-Coles v3 applies the training-only selected centered-effect
regularization strength `16.0` without shrinking the global scoring level. The resulting complete
locked-policy evaluation produces the metrics above and remains `FAIL`.

## Goal CRPS diagnostic

Retained clean run `7023ae81-d58b-53f4-9fde-b396166fb845` localizes the remaining failure to
heterogeneous total-goal CRPS, not model execution, calibration, coverage, or reproducibility. The
paired chronological moving-block distribution has median delta `+0.018055900362088505`, 2.5th
percentile `-0.006630599951364998`, 97.5th percentile `+0.0422727025769912`, and range
`[-0.022020445307986435, +0.06537431046976983]`. Of 2,000 replicates, 1,857 are above zero and 880
are above the locked `+0.02` limit.

Performance alternates across chronological blocks instead of improving monotonically with
history. Monthly point deltas are `+0.04752264730722793` in November, `+0.04720657445622578` in
January, and `+0.03754301839952209` in February, but `-0.007879608438146694` in March and
`-0.0033731751089293364` in April. Realized totals of zero, three, and six-or-more contribute
positive deltas of `+0.042403927006358665`, `+0.03594556256337469`, and
`+0.05775784962480092`; totals of four and five improve. Large individual losses occur in both
directions: overestimated totals in low-scoring matches and underestimated totals in high-scoring
matches. This is residual match/team heterogeneity, not a single global-rate bias suitable for a
post-hoc correction.

A follow-up using only the original 100-match warm-up compared time-decay half-lives `30`, `60`,
`90`, `180`, `365`, and disabled, with v3 regularization fixed at `16.0`. Disabling decay produced
the best pooled fold CRPS (`1.1110657803319448`) versus `1.111639373897392` at 365 days, a gain of
only `0.0005735935654472`, while moving over-2.5 signed bias from `-0.15711259116505255` to
`-0.1588878731118199`. This marginal, bias-worsening difference does not justify an adaptive v4
challenger after observing the gate. Retain v3 evidence, do not change policy, and do not promote.

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

## Post-gate governance decision

On 2026-09-01, the repository owner selected:

```text
RETAIN_FAIL_AND_STOP
```

One provisional shared Gamma-Poisson match-frailty family was tested in a precommitted disposable
feasibility prototype. Mathematical coherence, portable artifact round-trip, and scope integrity
passed. Stable deterministic fitting across every required synthetic case and the governed real
100-match warm-up was not demonstrated, so the result was `PROTOTYPE_FAIL`. No prototype defect
was identified, and no convergence or stationarity threshold was relaxed after observing the
result. The authoritative 280 targets were not loaded for challenger scoring.

Selected challenger is `NONE`. Dixon-Coles v3 remains retained failed evidence and is not
promoted. No Gamma-frailty modification or retry, alternate challenger, implementation,
authoritative challenger rerun, threshold or policy change, or promotion is authorized under this
route.

## Phase-priority override

On 2026-09-01, after retaining the Sprint 2 `FAIL` and closing challenger work, the repository
owner explicitly reprioritized Phase 1B and Phase 2B foundation work despite the predictive gate
result.

This authorization is limited to:

```text
Phase 1B
multi-source automated data acquisition,
resolution, quarantine, and acceptance evidence

Phase 2B
foundation hardening, dependency invalidation,
rebuild, observability, CI, recovery, integrity,
competition rules, and gate evidence
```

This priority change does not alter `Sprint2BaselineGatePolicyV1`, its thresholds, the frozen
target plan, retained evaluation evidence, the `FAIL` result, or the no-promotion decision. It does
not reopen Sprint 2 challenger work or authorize Gamma-frailty work, another goal-model family, an
authoritative challenger rerun, or Phase 3.

## Required next action

Proceed with bounded Phase 1B and Phase 2B tasks under their existing acceptance contracts. Retain
the Sprint 2 `FAIL` as authoritative evidence and stop at the Phase 1B/Phase 2B gate for review.
Phase 3 and later modelling remain blocked unless their prerequisites pass or the repository owner
makes a separate explicit governance decision.
