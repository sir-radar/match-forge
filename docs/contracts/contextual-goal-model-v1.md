# Contextual goal model V1

`MATCHFORGE_CONTEXTUAL_GOAL_MODEL_V1` applies governed context outside the production
baseline. It does not change the baseline model's internal mathematics.

For each team:

```text
log(lambda_final) = log(lambda_baseline) + contextual_adjustment
```

The adjustment uses only feature families with an immutable
`DEVELOPMENT_ACCEPTED` result. Rejected, insufficient-coverage, and protocol-failure
families contribute exactly zero and do not appear in the fitted artifact.

## Baseline and family order

The production baseline is `transferable-rolling-goals-poisson-v1`. Development-only
challengers do not replace it. Families are evaluated in this order:

1. accepted H2H, when prequalified;
2. availability and lineup;
3. rest and congestion;
4. manager continuity;
5. travel.

`MATCHFORGE_H2H_INCREMENTAL_SIGNAL_RESEARCH_V1` is `DEVELOPMENT_REJECTED`, so H2H is
not eligible for this model.

Each later family is compared with the last accepted incremental baseline. A rejected
family is removed before the next evaluation.

## Time and missingness

All feature builders require a target kickoff and knowledge cutoff. Confirmed lineups,
availability reports, coach records, and completed matches with `known_at` after the
cutoff are ineligible. Same-kickoff targets stay in one chronological batch.

Every optional numeric feature has a value, coverage indicator, and missingness
indicator in the fitted design. Continuous values use means and scales fitted on the
development training partition only. When a whole accepted family is unavailable for a
fixture, its adjustment is exactly neutral; baseline forecast coverage is unchanged.

`UNKNOWN`, `PREDICTED_REPEAT_XI`, and `CONFIRMED` remain distinct. A confirmed lineup
may affect only a confirmed-lineup-horizon forecast. Historical provider availability
must not be inferred from a later snapshot.

## Fitting and evaluation

Coefficients minimize joint home/away Poisson negative log likelihood with L2
regularization. The only regularization values are `0.01`, `0.1`, `1.0`, and `10.0`.
Training, validation, and development holdout use chronological kickoff batches in
`60% / 20% / 20%` order. Validation chooses regularization. The development holdout is
scored once.

Paired intervals use moving blocks of 10 kickoff batches, 2,000 replicates, seed
`20260921`, and a 95% interval. Admission requires all frozen gates in
`docs/evaluation/matchforge-context-feature-evaluation-v1-preregistration.json`.

Manager modelling additionally requires at least 300 qualified targets, three
competition domains, and 70% qualified coach coverage. Travel modelling requires at
least 500 qualified targets, three competition domains, and 80% qualified coordinate
coverage.

## Artifact and forecast activation

The artifact records the production baseline, included and excluded families,
coefficients, training-only scaler values, missingness rule, training cutoff, dataset
and configuration hashes, source commit, and artifact hash. Interaction terms are not
allowed in V1.

Context remains non-predictive until its family is accepted and separately authorized
for the active model. Only then is that family's payload included in
`predictive_input_snapshot_sha256`. A changed active predictive hash may create an
immutable forecast revision. Context-only updates for inactive families do not.
