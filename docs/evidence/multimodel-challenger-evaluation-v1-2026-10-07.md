# Multi-model challenger evaluation V1

## Decision

**RETAIN_CHAMPION. Production promotion is not justified.**

No challenger met the governed 712-target, three-domain coverage gate. Classical penaltyblog models and the ensemble covered 318/712 targets (44.66%) and had no Ligue 1 coverage because their development-only artifacts cannot invent unseen-team parameters. The Hierarchical Bayesian fit failed the precommitted R-hat maximum of 1.1 on development and final fitting, so it produced no protected forecasts.

All loss metrics are lower-is-better. Overall challenger rows are descriptive only because they do not share the champion's full target population.

## Overall results

| Model | Targets | Coverage | Joint LL | 1X2 LL | Brier | RPS | CRPS |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current champion | 712 | 100.00% | 2.985201 | 1.022146 | 0.612663 | 0.212147 | 0.924581 |
| Penaltyblog Dixon-Coles | 318 | 44.66% | 3.105558 | 0.994200 | 0.592005 | 0.205719 | 0.934887 |
| Penaltyblog Hierarchical Bayesian | 0 | 0.00% | — | — | — | — | — |
| Penaltyblog Negative Binomial | 318 | 44.66% | 3.117190 | 0.996543 | 0.593842 | 0.206284 | 0.937722 |
| Penaltyblog Weibull-Copula | 318 | 44.66% | 3.117643 | 0.997914 | 0.594596 | 0.206351 | 0.937681 |
| MatchForge ensemble v1 | 318 | 44.66% | 3.052298 | 0.997485 | 0.594146 | 0.205643 | 0.938986 |

## Competition results

| Model | Competition-season | Targets | Joint LL | 1X2 LL | Brier | RPS | CRPS |
|---|---|---:|---:|---:|---:|---:|---:|
| Current champion | `bundesliga_2022_23` | 216 | 3.090509 | 1.027850 | 0.617546 | 0.217664 | 0.978028 |
| Current champion | `bundesliga_2023_24` | 216 | 3.011223 | 1.024593 | 0.613613 | 0.206258 | 0.926989 |
| Current champion | `ligue1_2022_23` | 280 | 2.883888 | 1.015858 | 0.608165 | 0.212435 | 0.881494 |
| Penaltyblog Dixon-Coles | `bundesliga_2022_23` | 170 | 3.105383 | 0.965881 | 0.573608 | 0.200190 | 0.929746 |
| Penaltyblog Dixon-Coles | `bundesliga_2023_24` | 148 | 3.105760 | 1.026728 | 0.613136 | 0.212069 | 0.940791 |
| Penaltyblog Negative Binomial | `bundesliga_2022_23` | 170 | 3.117204 | 0.966475 | 0.574135 | 0.200525 | 0.933058 |
| Penaltyblog Negative Binomial | `bundesliga_2023_24` | 148 | 3.117175 | 1.031082 | 0.616477 | 0.212899 | 0.943079 |
| Penaltyblog Weibull-Copula | `bundesliga_2022_23` | 170 | 3.116340 | 0.968683 | 0.575461 | 0.201178 | 0.933035 |
| Penaltyblog Weibull-Copula | `bundesliga_2023_24` | 148 | 3.119141 | 1.031490 | 0.616575 | 0.212292 | 0.943018 |
| MatchForge ensemble v1 | `bundesliga_2022_23` | 170 | 3.083076 | 1.001298 | 0.596641 | 0.211029 | 0.949702 |
| MatchForge ensemble v1 | `bundesliga_2023_24` | 148 | 3.016944 | 0.993105 | 0.591279 | 0.199457 | 0.926677 |

Champion's best competition by joint log loss was `ligue1_2022_23` (2.883888); worst was `bundesliga_2022_23` (3.090509). Among covered challenger targets, the ensemble was best in both Bundesliga seasons and had the lowest overall joint log loss (3.052298), but this does not overcome missing 394 targets or support a universal comparison.

## Paired deltas versus champion

Delta = challenger loss minus champion loss on identical targets. Negative favors challenger.

| Model | Competition-season | Common targets | Joint LL delta | 95% CI |
|---|---|---:|---:|---:|
| Penaltyblog Dixon-Coles | `bundesliga_2022_23` | 170 | -0.005858 | [-0.053825, 0.047389] |
| Penaltyblog Dixon-Coles | `bundesliga_2023_24` | 148 | 0.080099 | [0.011193, 0.138914] |
| Penaltyblog Hierarchical Bayesian | — | 0 | — | — |
| Penaltyblog Negative Binomial | `bundesliga_2022_23` | 170 | 0.005964 | [-0.044660, 0.062194] |
| Penaltyblog Negative Binomial | `bundesliga_2023_24` | 148 | 0.091514 | [0.021145, 0.151883] |
| Penaltyblog Weibull-Copula | `bundesliga_2022_23` | 170 | 0.005099 | [-0.044965, 0.067641] |
| Penaltyblog Weibull-Copula | `bundesliga_2023_24` | 148 | 0.093480 | [0.021597, 0.168975] |
| MatchForge ensemble v1 | `bundesliga_2022_23` | 170 | -0.028164 | [-0.038974, -0.011600] |
| MatchForge ensemble v1 | `bundesliga_2023_24` | 148 | -0.008717 | [-0.020463, -0.000607] |

The ensemble improved joint log loss on its covered targets in both seasons: -0.028164 [−0.038974, −0.011600] for Bundesliga 2022/23 and -0.008717 [−0.020463, −0.000607] for Bundesliga 2023/24. This is promising partial-domain evidence, not a promotion pass. Dixon-Coles, Negative Binomial, and Weibull-Copula were materially worse in Bundesliga 2023/24; their 95% joint-log-loss intervals were wholly above zero.

## Overall calibration

| Model | Home intercept / slope | Draw intercept / slope | Away intercept / slope |
|---|---:|---:|---:|
| Current champion | 0.100580 / 1.302047 | 0.489894 / 1.327068 | 0.225982 / 1.520650 |
| Penaltyblog Dixon-Coles | 0.194409 / 0.833136 | 0.269181 / 1.226809 | -0.419625 / 0.819025 |
| Penaltyblog Hierarchical Bayesian | — | — | — |
| Penaltyblog Negative Binomial | 0.142713 / 0.825835 | 0.496779 / 1.278526 | -0.462687 / 0.817081 |
| Penaltyblog Weibull-Copula | 0.162720 / 0.871735 | 0.685119 / 1.405874 | -0.460019 / 0.863921 |
| MatchForge ensemble v1 | 0.291455 / 1.464883 | 0.620813 / 1.426883 | 0.268034 / 1.891507 |

Full competition calibration, reliability bins, every paired metric delta/interval, and fitted artifact diagnostics are retained in the machine-readable evidence.

## Development-only selection

- Dixon-Coles half-life: 365 days; 211/216 valid development forecasts.
- Negative Binomial half-life: 730 days; 216/216 valid development forecasts.
- Weibull-Copula half-life: 365 days; 216/216 valid development forecasts.
- Hierarchical Bayesian: fixed 365-day half-life, 4 chains, 3,000 samples, 1,500 burn-in; 0/216 valid development forecasts because R-hat exceeded 1.1.
- Equal-weight ensemble development joint LL: 3.069068.
- Optimized ensemble development joint LL: 3.061406.
- Optimized weights: `pb-negative-binomial-v1`=0.108126, `pb-weibull-copula-v1`=0.079251, `transferable-rolling-goals-poisson-v1`=0.812624.

Dixon-Coles invalid score grids and Hierarchical Bayesian invalid fits were rejected. No clipping, invented coefficients, or diagnostic relaxation was applied.

## Feature ablation

Rating, H2H, and xG/xGA remain descriptive with zero predictive influence in this evaluated model set. Penaltyblog's integrated goal-model APIs consume goals, teams, and time weights; the champion artifact has `beta_xg_for=0.0`. An unsupported contextual model was not invented, so predictive ablation deltas are exactly not applicable rather than post-hoc estimates.

## Governance and integrity

- Development selection and final artifact fitting completed before protected outcomes loaded.
- Evaluation outcomes were not used for fit, refit, tuning, calibration, or ensemble weights.
- Evaluation refits: 0.
- Same-kickoff batches were forecast before outcomes became history.
- Bootstrap: paired moving blocks, 10 kickoff batches, 2,000 replicates, seed 20260924.
- Required promotion coverage: 712/712 across all three domains. Best challenger coverage: 318/712.
- Rust distribution contract tests passed, but publishable-model Rust promotion validation was not run because no challenger reached the mandatory coverage gate.
- One earlier invocation was stopped during development fitting because its supplied source SHA did not match `HEAD`; it did not reach protected-data loading and wrote no result. The completed logical protected evaluation count remains one.

## Evidence identity

- Source commit: `9a25646d00ebc0c20983dbff8d5d205843f1b8be`
- Preregistration SHA-256: `bb0800536f136b0e52df95055f72bec204613f37dd315f6a594f9980328db207`
- Prediction manifest SHA-256: `fadcd93146d62881a8c374d999b1469a83046cde347fcd7db97ba28cb0f532cb`
- Evidence SHA-256: `a5ca0e1eb30d407330ee548e98db2b1817eaec1e347ef87f19bf7c20440e3984`
- Logical authorized executions completed: 1
- Result: `RETAIN_CHAMPION`
- Winning eligible model: `transferable-rolling-goals-poisson-v1`
- Production promotion justified: `false`
