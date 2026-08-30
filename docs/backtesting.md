# Sprint 2 backtesting

## Contract

Primary evaluation is chronological walk-forward. Random train/test splitting is not authoritative
evidence.

`PointInTimeScopeV1` binds dataset and source snapshot identity, feature version,
`football_cutoff`, `knowledge_cutoff`, `knowledge_mode`, quality policy, and target-set checksum.
`PointInTimeMatchDatasetProvider` applies the dual cutoffs before models receive data. It resolves
chronology through immutable kickoff claims linked to the exact lifecycle dataset; it does not read
timezone-naive provider values as UTC. Forecast contexts are label-free and have a canonical
checksum. Same-kickoff targets remain one batch.

`WalkForwardEvaluator` defines expanding or rolling training windows, evaluation duration, and
retraining frequency. Evaluation observations keep prediction time, kickoff time, and
`outcome_known_at` separate. Calibration rejects any outcome not known strictly before its fit
cutoff.

## Match-result metrics

Sprint 2 implements:

- Log loss.
- Multiclass Brier score.
- Ranked Probability Score.
- Accuracy as a supporting metric.
- Reliability bins.
- Expected Calibration Error.
- Brier uncertainty, resolution, and reliability decomposition.

Calibration is a separate artifact layer. One-vs-rest Platt and isotonic calibrators emit normalized
1X2 probabilities. Raw forecasts remain immutable. A configurable gate compares raw and calibrated
out-of-sample log loss, Brier, and ECE; calibration is rejected when permitted regressions are
exceeded or too few metrics improve.

## Leakage invariants

- Training matches have `kickoff_at < football_cutoff`.
- Target contexts contain no scores or post-match statistics.
- Historical observations use the exact source snapshot and bitemporal knowledge cutoff.
- Same-kickoff matches are forecast as one chronological batch.
- Calibration outcomes require `outcome_known_at < calibration_cutoff`.
- Evaluation outcomes remain separate from persisted forecast payloads.

## Current evidence boundary

Unit and integration tests verify window chronology, same-time batching, calibration-cutoff
exclusion, metric mathematics, immutable reporting, and retry behavior. The approved corpus now has
380 registered, completed, scored, and UTC-resolved targets through exact immutable lifecycle and
kickoff claims, forming 199 chronological batches. No repository command has yet executed full
model refits and forecasts across that corpus. See
[Sprint 2 phase gate](sprint2-phase-gate.md).
