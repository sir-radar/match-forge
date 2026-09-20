# DCv3 low-score structure diagnostic protocol — 2026-09-09

## Map

```text
Frozen DCv3 Low-Score Structure Diagnostic
```

This protocol is frozen before this map generates cell-level results. It is a
read-only analysis of the retained corrected La Liga diagnostic artifact. It
does not fit, retune, or alter DCv3 or any challenger.

## Bound input

```text
Input: docs/evidence/dcv3-independent-laliga-diagnostic-corrected-2026-09-09.json
Required SHA-256: 120ca2e0e135942d7d0b0316d8035562e9d57426225fe3d49dedf4ada445ee5e
Dataset version: 670662d6-6ed7-5fa1-ba3c-1cfd561e524f
Source snapshot: 01a08471-f763-7787-80ca-4293316b7e44
Targets: 280
Kickoff batches: 243
Target SHA-256: b758e795d41f0cc84145626d20d791eccbcfbd9fb94d2767039bdcdf50f3eb18
Frozen model: sprint2-dixon-coles-v3
```

Each forecast must retain the canonical match ID, kickoff timestamp, home and
away team IDs, frozen lambdas, fitted rho, frozen joint probability state, and
observed score. The script verifies the artifact hash, contract, target and
batch counts, unique forecast identities, and that its computed four-cell DC
probabilities equal the frozen joint state.

## Probability decomposition

For every forecast and each cell in `(0-0, 0-1, 1-0, 1-1)`, the analysis
computes:

```text
independent Poisson probability = Pois(home; lambda_home) * Pois(away; lambda_away)
frozen DC probability = independent probability * tau
```

The exact `tau` implementation is the frozen production implementation. No
probabilities are re-normalized and no parameter is optimized.

## Frozen bootstrap and multiplicity procedure

```text
Method: circular chronological moving-block bootstrap
Sampling unit: retained kickoff batches reconstructed from identical UTC kickoff strings
Block length: 10 kickoff batches
Replicates: 2,000
Seed: 20260909
Primary family: frozen-DC calibration errors for 0-0, 0-1, 1-0, and 1-1 together
Statistic: maximum standardized centered bootstrap error
Interval: simultaneous 95%, empirical order-statistic floor-index quantile
```

Every replicate samples circular consecutive kickoff-batch blocks until it
contains exactly 243 batches. All matches from selected batches are retained.
This preserves within-batch dependence and forecast/refit grouping. Let
`e_j` be the observed-minus-predicted frequency error for cell `j`, and
`e*_j,b` its bootstrap replicate. The bootstrap standard error is the sample
standard deviation of `e*_j,b`. The family critical value is the empirical
95th percentile of:

```text
max_j abs((e*_j,b - e_j) / se_j)
```

The simultaneous interval is `e_j +/- critical_value * se_j`. Independent
Poisson values are a deterministic decomposition only; their marginal 95%
moving-block-bootstrap intervals are reported descriptively and are not used
for the primary family conclusion.

## Prespecified supporting views

Forecast-only 0-0 strata are three equal-count groups after sorting frozen DC
0-0 probability, then canonical match ID: 93, 93, and 94 targets. Their
uncertainty uses the same 2,000-replicate moving-block bootstrap and reports
marginal percentile 95% intervals.

Chronological stability reuses the earlier diagnostic's four equal-count
kickoff-batch blocks. Team concentration uses each match's frozen-DC 0-0
residual split equally between its home and away teams; reported shares use
absolute team net contributions, and effective concentration is the inverse
Herfindahl index of those shares. These views are descriptive and do not
select team parameters.

## Decision rule

`0-0` survives the primary low-score family only when its simultaneous interval
excludes zero. Scalar-rho direction is compatible only when a single signed
rho change moves all four frozen cell probabilities toward their observed
frequencies; it is incompatible when neither signed change does so. It is
inconclusive when the four-cell direction cannot be established from the
simultaneous family.

The map selects scalar-rho misspecification only when the frozen correction
materially worsens the 0-0 absolute calibration error, the scalar direction is
compatible, and 0-0 survives simultaneous inference. It selects broader
dependence only when a robust four-cell pattern is scalar-direction
incompatible. It selects low-score mechanism inconclusive when the retained
signal survives but neither mean versus correction nor scalar versus broader
dependence can be identified under these rules.

No result authorizes fitting, tuning, a change in rho bounds, a challenger, or
access to the protected EPL populations.
