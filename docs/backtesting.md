# Backtesting and Point-in-Time Evaluation

## Purpose

This document defines MatchForge's durable rules for historical forecasting, leakage prevention, chronological evaluation, and calibration fitting.

Specific Sprint/phase corpora, thresholds, metrics, and current decisions live in their versioned policies/evidence and owner/Wayfinder decisions.

## Two time axes

Every historical forecast must respect:

```text
football_cutoff
knowledge_cutoff
knowledge_mode
```

### Football time

A training observation must be football-historically eligible for the target.

No event/result after the approved football cutoff may enter training or features.

### Knowledge time

A fact must also satisfy the approved rule for when MatchForge could know it.

Where historical provider availability cannot be proven, use the approved weaker retrospective knowledge mode rather than pretending strict historical availability is known.

Do not collapse these concepts into one vague `as_of`.

## Contract separation

Use distinct contracts for:

```text
historical labelled training rows
label-free pre-match forecast context
post-prediction evaluation outcomes
```

The pre-match forecast context must structurally exclude target:

- score;
- result;
- corners;
- shots;
- possession;
- post-match statistics;
- any other outcome-derived field.

Do not rely on model code to ignore forbidden fields.

## One point-in-time dataset authority

Historical eligibility belongs to one provider-neutral point-in-time dataset layer.

Conceptually:

```text
PointInTimeMatchDatasetProvider
        ↓
eligible MatchForge history
        ↓
Elo / Dixon-Coles / corner models / challengers / evaluator
```

Models must not independently query current database state for "previous matches".

## Same-kickoff batching

Matches that could not legitimately observe each other's outcomes must be forecast as one batch.

Correct:

```text
state before batch
→ fit/update only from previously known history
→ forecast every target in the batch
→ persist/freeze every forecast
→ reveal outcomes
→ update state for future batches
```

Forbidden:

```text
forecast A
→ reveal A
→ update model/calibration
→ forecast simultaneous B
```

When temporal ordering is ambiguous, prefer conservative batching or exclusion.

Any confirmed same-batch leakage is blocking regardless of metrics.

## Walk-forward evaluation

Authoritative football evaluation is chronological walk-forward evaluation.

The evaluator owns:

- training-window policy;
- target selection;
- minimum-history policy;
- retraining cadence;
- chronological batching;
- target-outcome release;
- metrics;
- calibration comparison;
- reporting.

Models must not implement independent backtest loops.

Do not use random train/test splitting as authoritative football forecasting evidence.

## Reference models

Complex models must be compared against compatible simpler references on the same governed targets.

A model does not earn promotion because its standalone metric "looks good".

Complexity must earn its place.

## Proper scores

Use the versioned evaluation policy.

Common primary metrics include:

- Log Loss;
- Brier Score;
- RPS;
- NLL;
- CRPS.

Accuracy, MAE, and RMSE are supporting metrics unless a frozen policy says otherwise.

Do not change the scoring policy after seeing authoritative results.

## Paired comparison

When uncertainty intervals are required, use the frozen paired resampling policy.

Candidate and reference forecasts must use the same target blocks/samples.

Do not use a different resampling design to rescue a failed candidate after results are known.

## Calibration

Calibration is a separate model layer.

Never overwrite raw probabilities.

Keep:

```text
MODEL_RAW
MODEL_CALIBRATED
```

as distinct forecast variants.

Calibration may train only on:

```text
previously generated out-of-sample predictions
+
outcomes already known before the next calibration fit cutoff
```

Never fit calibration on:

- base-model in-sample predictions;
- future outcomes;
- the target match;
- the full season retrospectively and apply it as historical.

Calibration follows the same same-kickoff batching rules.

If calibration does not improve out-of-sample evidence, retaining raw probabilities is valid.

## Leakage tests

Historical modelling changes should test applicable cases:

- future match excluded;
- target match excluded;
- target outcome inaccessible before forecast;
- same-kickoff matches isolated;
- historical corrections obey knowledge time;
- current-state shortcuts cannot enter historical evaluation;
- calibration target excluded;
- feature lookbacks use prior history only.

A leakage defect is a hard failure.

## Authoritative target firewall

When a Wayfinder route or owner decision forbids access to an authoritative target population:

- do not load it;
- do not inspect it;
- do not join against it;
- do not forecast it;
- do not score it;
- do not derive new target-level diagnostics from it;
- do not tune against it.

A feasibility or training-only route must remain isolated from forbidden target material.

If the route defines `AUTHORITATIVE_TARGET_ACCESS` as a hard failure, any such access stops the route even if the model is technically correct.

## Frozen admission protocols

When a challenger has a precommitted training-only admission protocol:

- keep target/fold definitions unchanged;
- fit only from each fold's training history;
- do not use validation outcomes for tuning;
- apply the exact frozen inequalities;
- do not round or add tolerance after seeing the result;
- stop when a hard condition fails.

Passing feasibility does not imply admission.

Passing admission does not imply authoritative evaluation unless a later owner decision explicitly authorizes it.

## Reproducibility

An authoritative run must bind the applicable:

- dataset/source snapshot identities;
- build specification;
- model artifact identities;
- feature versions;
- cutoffs;
- knowledge mode;
- evaluation policy;
- code Git SHA;
- dependency lock;
- configuration;
- random seed where used.

A run is reproducible only when the same semantic specification reproduces the same logical target set and metrics within the documented tolerance.
