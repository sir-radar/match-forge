# Transferable Rolling npxG For/Against Dixon-Coles V2 Research

## Disposition

`DEVELOPMENT_REJECTED`

The candidate is not admitted for confirmation. No confirmation data was selected or acquired,
no V6 protocol was created or run, no model was promoted, and no post-hoc calibrator was fitted.

## Bound inputs

- Snapshot: `9acd90ce-b847-5ab4-8e2b-b98d5602da70`
- Snapshot SHA-256: `5d179ba9933ee2284d3646a1298f0305c355a5cf178e5e580fe974b28e97b1e5`
- Corpus SHA-256: `2ace8fb86f8881dae1baeb5c7cdb277e1174e124eb264def17f658b9550c2193`
- Firewall SHA-256: `8b67bb05d52768b8163ce205db2fbc127f22ff879206b1f9fd11ff46b9c87704`
- Eligible development targets: 1,270
- Protected intersections: V5 `0`; protected StatsBomb `0`; prior spent PitchAPI `0`
- Preregistration SHA-256: `5ff4ef212931d5aeeb94b5dd3b3c905d276088a7775f85d54e1ce73e7605f517`
- Implementation source commit: `951c17f0d3ef570609b11a76d7a565898e32017f`

## Frozen mathematics

For competition `c`, `b_c = b_global + delta_c` and `h_c = h_global + eta_c`.
Competition deviations have separate sum-to-zero constraints.

```text
log(lambda_home) = b_c + h_c
                 + beta_gf * GF_home
                 + beta_ga * GA_away
                 + beta_xf * NPXGF_home
                 + beta_xa * NPXGA_away

log(lambda_away) = b_c
                 + beta_gf * GF_away
                 + beta_ga * GA_home
                 + beta_xf * NPXGF_away
                 + beta_xa * NPXGA_home
```

Each feature is the equally weighted mean over the team's last 10 valid appearances, transformed
as `log((rolling_mean + 0.05) / (strictly_prior_competition_mean + 0.05))`. npxG excludes
provider-labelled penalties and own goals. Team state is paired with the opponent's against state;
there are no fitted team-ID parameters.

The joint score probability is
`tau(x,y) * Poisson(x;lambda_home) * Poisson(y;lambda_away)`, where:

```text
tau(0,0) = 1 - lambda_home * lambda_away * rho
tau(0,1) = 1 + lambda_home * rho
tau(1,0) = 1 + lambda_away * rho
tau(1,1) = 1 - rho
tau(x,y) = 1 otherwise
```

The optimizer, bounds, initialization, three-candidate regularization budget, convergence rules,
tail handling, validation design, bootstrap, and admission thresholds are frozen in the
preregistration.

## Development folds

Five leave-domain-out folds were split into four chronological kickoff-batch blocks. Each scored
block excluded its entire competition-season and used only other-domain rows strictly before the
block start. Early blocks with fewer than 100 eligible strictly-prior other-domain rows failed
closed and were not scored. This produced 1,013 leave-domain-out targets:

| Domain | Qualified | Scored |
| --- | ---: | ---: |
| Bundesliga 2024/25 | 215 | 163 |
| Bundesliga 2025/26 | 216 | 216 |
| Premier League 2024/25 | 280 | 205 |
| La Liga 2024/25 | 280 | 215 |
| Serie A 2024/25 | 279 | 214 |

Leave-team-out assigned each target once to the lexicographically smaller participating team ID,
excluded that team's outcomes and all rows at or after the fold cutoff, and scored 242 targets
across 76 team folds. Its joint-score log loss was `2.9664437654` for the candidate,
`2.9815821154` for the reference, and `2.9623598724` for V5.

## Proper scores

Columns are goals-only reference, raw V5 npxG, then V2 candidate.

| Domain | Joint log loss | 1X2 log loss | Brier | RPS | Total-goal CRPS |
| --- | --- | --- | --- | --- | --- |
| Bundesliga 2024/25 | 3.165844 / 3.122340 / 3.102365 | 1.077442 / 1.059575 / 1.051474 | 0.651323 / 0.638828 / 0.631959 | 0.222124 / 0.216809 / 0.213373 | 1.014866 / 0.989951 / 0.982215 |
| Bundesliga 2025/26 | 3.120007 / 3.086584 / 3.081195 | 1.016144 / 1.008483 / 1.012947 | 0.607298 / 0.602117 / 0.604503 | 0.207232 / 0.205187 / 0.206187 | 0.978274 / 0.949041 / 0.934471 |
| Premier League 2024/25 | 2.990236 / 2.980326 / 2.966338 | 1.003925 / 0.992619 / 0.978488 | 0.600001 / 0.592279 / 0.582938 | 0.213720 / 0.209377 / 0.204893 | 0.877250 / 0.877745 / 0.871559 |
| La Liga 2024/25 | 2.833840 / 2.819850 / 2.819834 | 1.018329 / 0.999098 / 0.995854 | 0.608998 / 0.594777 / 0.592455 | 0.209701 / 0.202616 / 0.201391 | 0.902886 / 0.905499 / 0.906055 |
| Serie A 2024/25 | 2.749627 / 2.732675 / 2.727922 | 1.027360 / 1.013731 / 1.002040 | 0.616881 / 0.606801 / 0.599590 | 0.203532 / 0.199135 / 0.195858 | 0.814397 / 0.808106 / 0.810256 |
| Macro-domain | 2.971911 / 2.948355 / 2.939531 | 1.028640 / 1.014701 / 1.008160 | 0.616900 / 0.606960 / 0.602289 | 0.211262 / 0.206625 / 0.204340 | 0.917535 / 0.906069 / 0.900911 |
| Target-weighted | 2.962140 / 2.939457 / 2.931256 | 1.026368 / 1.012610 / 1.006241 | 0.615291 / 0.605465 / 0.600962 | 0.210684 / 0.206081 / 0.203882 | 0.913098 / 0.902181 / 0.897150 |

Weighted candidate-minus-reference joint-score log loss was `-0.030884`
with 95% interval `[-0.049192, -0.017604]`. Candidate-minus-V5 was `-0.008201`
with 95% interval `[-0.017675, 0.000049]`. The latter fails the frozen strict
upper-bound-below-zero rule.

## Calibration

Candidate values are intercept / slope; full intervals and ECE values remain in the machine-readable
evidence.

| Domain | Home | Draw | Away |
| --- | --- | --- | --- |
| Bundesliga 2024/25 | -0.144 / 1.542 | 0.674 / 1.431 | 0.041 / 0.821 |
| Bundesliga 2025/26 | 0.162 / 1.184 | 0.816 / 1.560 | -0.192 / 1.114 |
| Premier League 2024/25 | 0.077 / 1.582 | -1.269 / -0.000 | 0.523 / 1.499 |
| La Liga 2024/25 | 0.053 / 1.172 | 0.202 / 1.044 | -0.066 / 1.139 |
| Serie A 2024/25 | 0.023 / 1.449 | 1.867 / 2.347 | 0.073 / 1.473 |

The frozen per-domain acceptance ranges were absolute intercept at most `0.25`, slope from `0.8`
through `1.2`, intercept interval width at most `0.3`, and slope interval width at most `0.4`.
Multiple outcomes fail, especially draw calibration. No post-hoc calibration rescue was attempted.

## Immutable outputs and reproduction

- Candidate artifact SHA-256: `92b2a462ef5fecd074622ea1a1dc9d4faabd01e9eba8d14f060b5eb517fc7332`
- Fold manifest SHA-256: `a5d0cfe70cfe6e1f3890b4b1944cedc17e1677deb483d542c64f81f4b43c80c9`
- OOS predictions SHA-256: `644b7e2fb9f3802fbfdad3adc12de763147119c3f259a0fc06ad249168270f6c`
- Development evidence SHA-256: `d9a43ffef56ea14b0f8c25016d19e2a2bf75949da09d1e135bf6cf6fcaa3e3f7`
- Completion receipt SHA-256: `3a42e404b4176bd92b5187a4c8bc9c923255d8aa499bebb50488fd50b4153e2d`
- Reproduction: `PASS_BYTE_IDENTICAL_TWO_RUNS`
- Artifact reload: `PASS_EXACT_PREDICTION_EQUALITY`

## Scientific limitations

- PitchAPI does not expose the upstream xG model version.
- Provider correction history is unavailable.
- Strict chronology prevents scoring 257 early leave-domain-out targets because fewer than 100
  other-domain eligible rows existed before their block cutoff.
- Leave-team-out evidence covers 242 targets; early team folds without 100 strictly-prior eligible
  non-team rows fail closed.
- All evidence is development-only and cannot support a confirmation or promotion claim.

## Owner boundary

Confirmation acquisition, confirmation evaluation, V6, and promotion remain unauthorized.
The next owner decision required is:

`ACCEPT_TRANSFERABLE_ROLLING_NPXG_FOR_AGAINST_DIXON_COLES_V2_DEVELOPMENT_REJECTION_AND_CLOSE_ROUTE_V1`

Alternatively, any further model research requires a new explicit hypothesis and authorization.
