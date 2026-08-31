# Sprint 2 backtesting

## Contract

Primary evaluation is chronological walk-forward. Random train/test splitting is not authoritative
evidence.

`PointInTimeScopeV1` binds dataset and source snapshot identity, feature version,
`football_cutoff`, `knowledge_cutoff`, `knowledge_mode`, quality policy, and target-set checksum.
`PointInTimeMatchDatasetProvider` applies the dual cutoffs before models receive data. It resolves
chronology through immutable kickoff claims linked to the exact lifecycle dataset; it does not read
timezone-naive provider values as UTC. Forecast contexts are label-free and have a canonical
checksum. Same-kickoff targets remain one batch. `WalkForwardTargetPlanV1` applies the frozen
10-match team and 100-match competition minimums from prior batches only, then retains the ordered
label-free target set and checksum. See [Walk-forward target plan](walk-forward-target-plan.md).

`WalkForwardEvaluator` defines expanding or rolling training windows, evaluation duration, and
retraining frequency. Evaluation observations keep prediction time, kickoff time, and
`outcome_known_at` separate. Calibration rejects any outcome not known strictly before its fit
cutoff. Under `retrospective-fixed-snapshot-v1`, the approved EPL regulation-time corpus uses the
existing conservative two-hour post-kickoff outcome-availability rule; strict bitemporal modes use
the governed claim timestamps instead.

`Sprint2WalkForwardExecutor` consumes the frozen target plan through explicit dataset and
persistence ports. For each batch it loads only prior eligible history, fits Elo, Dixon–Coles,
corner Poisson, and corner Negative Binomial state, forecasts every target, persists all four raw
forecasts, and only then requests target outcomes. Reference result, goal-Poisson, and
corner-Poisson forecasts are computed from the same prior history and retained in execution
results for common-target scoring.

## Match-result metrics

Sprint 2 implements:

- Log loss.
- Multiclass Brier score.
- Ranked Probability Score.
- Accuracy as a supporting metric.
- Reliability bins.
- Expected Calibration Error.
- Brier uncertainty, resolution, and reliability decomposition.

Raw execution scoring also implements joint goal-score negative log likelihood, total-goal CRPS,
MAE, RMSE, and Poisson deviance; and home, away, and total corner negative log likelihood, CRPS,
MAE, and RMSE for both corner families and the simple reference.

Calibration is a separate challenger layer. Authoritative 1X2 analysis uses multiclass vector
calibration so the simplex is preserved; Over 2.5 and BTTS use binary Platt and isotonic
challengers. Each chronological batch trains only from earlier out-of-sample predictions whose
outcomes were already known. Raw forecasts remain immutable. Acceptance requires ECE improvement
without exceeding the locked log-loss or Brier regression allowances.

Uncertainty uses one shared set of deterministic paired chronological moving-block resamples across
candidate/reference metrics: 2,000 replicates, block size 10, 95% intervals, and explicit seed
`20260831`. Evidence retains replicate deltas rather than only interval summaries.

## Leakage invariants

- Training matches have `kickoff_at < football_cutoff`.
- Target contexts contain no scores or post-match statistics.
- Historical observations use the exact source snapshot and bitemporal knowledge cutoff.
- Same-kickoff matches are forecast as one chronological batch.
- Earlier staggered kickoffs remain outside training history until their retrospective two-hour
  outcome-availability boundary has passed.
- Calibration outcomes require `outcome_known_at < calibration_cutoff`.
- Evaluation outcomes remain separate from persisted forecast payloads.
- Outcome reveal requires explicit frozen target IDs and exact lifecycle, corner-label, dataset,
  kickoff, and knowledge-cutoff lineage.

## Current evidence boundary

Unit and integration tests verify window chronology, same-time batching, calibration-cutoff
exclusion, metric mathematics, immutable reporting, and retry behavior. Batch execution tests also
prove persistence-before-reveal, four-artifact/four-forecast publication per target, portable state
reload, and semantic retry convergence. The approved corpus has
380 registered, completed, scored, corner-labelled, and UTC-resolved matches through exact immutable
lifecycle, kickoff, and corner claims. The immutable plan resolves 280 eligible targets after 100
warm-up exclusions, across 146 eligible batches. The authoritative operator command now composes
the executor, scoring, paired bootstrap, chronological calibration, and immutable JSON/Parquet/SVG
evidence publication. Complete execution stops for baseline-policy review; the implementation does
not assert that the corpus has passed predictive-quality or reproduction gates. See
[Sprint 2 phase gate](sprint2-phase-gate.md).
