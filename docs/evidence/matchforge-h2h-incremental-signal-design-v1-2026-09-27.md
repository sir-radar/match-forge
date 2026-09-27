# MatchForge H2H incremental-signal design

## Result

`H2H_RESEARCH_NOT_CURRENTLY_SUPPORTABLE`

The fixed development snapshot contains 1,751 finished matches and exactly 1,270 eligible targets. Although 924 targets have at least one strictly prior meeting, only 169 have at least two and 120 have at least three. All targets with two or more prior meetings are in `bundesliga_2025_26`. No target has five. This is not enough multi-domain evidence to estimate a stable transferable H2H effect.

No model was fitted or evaluated. No data was acquired. V6 remains unauthorized.

## Closed Dixon-Coles V2 route

`TRANSFERABLE_ROLLING_NPXG_FOR_AGAINST_DIXON_COLES_V2` is permanently closed as `DEVELOPMENT_REJECTED`. Its candidate artifact (`92b2a462ef5fecd074622ea1a1dc9d4faabd01e9eba8d14f060b5eb517fc7332`) and preregistration (`5ff4ef212931d5aeeb94b5dd3b3c905d276088a7775f85d54e1ce73e7605f517`) remain immutable negative development evidence.

The candidate materially beat the goals-only reference, but its weighted joint-score delta against V5 was `-0.008201`, with a 95% interval of `[-0.017675, 0.000049]`. The interval crosses zero, and multiple frozen calibration or precision gates failed. The fitted `rho` of `0.0001840405` is effectively zero. The experiment supports npxG-for/against as useful signal, but the Dixon-Coles layer did not earn admission.

## Current H2H data and coverage

All counts use MatchForge team IDs and require `H2H kickoff < target kickoff`. Same-kickoff and future matches are excluded.

| Prior meetings | Targets | Share |
|---:|---:|---:|
| 0 | 346 | 27.2441% |
| 1 | 755 | 59.4488% |
| 2 | 49 | 3.8583% |
| 3 | 120 | 9.4488% |
| 5+ | 0 | 0% |

Cumulative coverage is 924 targets with 1+, 169 with 2+, 120 with 3+, and 0 with 5+. Every counted meeting has usable npxG, so npxG coverage is identical.

| Development scope | Targets | 1+ | 2+ | 3+ |
|---|---:|---:|---:|---:|
| Bundesliga 2024/25 | 215 | 152 | 0 | 0 |
| Bundesliga 2025/26 | 216 | 202 | 169 | 120 |
| La Liga 2024/25 | 280 | 190 | 0 | 0 |
| Premier League 2024/25 | 280 | 190 | 0 | 0 |
| Serie A 2024/25 | 279 | 190 | 0 | 0 |

Latest-prior-meeting age is 4.0 to 358.083333 days, with median 134.125 days. The 10th, 25th, 75th, and 90th percentiles are 94.821875, 122.789062, 161.065104, and 217.0875 days. Counts are 70 at 0–90 days, 661 over 90–180, and 193 over 180–365. Across all 1,213 prior meetings, median age is 146.125 days and maximum age is 624.166667 days.

The latest meeting has reversed home/away orientation for 896 targets and the same orientation for 28. Exactly 169 targets use history from another season scope; no counted history crosses competitions.

## One bounded future feature family

The future baseline is the same transferable Poisson model using rolling goals-for, goals-against, npxG-for, npxG-against, competition effects, and home effect, with `rho = 0` and no H2H input. The candidate changes only by adding one `SECONDARY_MATCHUP_PRIOR` coefficient anti-symmetrically to the home and away log rates.

Use at most five meetings from the prior 730 days, require two usable meetings, and use a fixed 180-day half-life. For prior meeting `j`, orient both clubs to the future target and calculate a strictly out-of-sample baseline residual:

```text
r_j = 0.5 * ((npxG_target_home_j - lambda_target_home_j)
             - (npxG_target_away_j - lambda_target_away_j))
```

Clip `r_j` to `[-1.5, 1.5]`. The baseline rates for meeting `j` must have been forecast using only information strictly before that meeting.

```text
w_j = 2^(-age_days_j / 180)
      * continuity_j
      * era_j
      * competition_j
      * orientation_j

q = min(1, sum(w_j) / 1.5)

secondary_matchup_prior = clip(
    q * sum(w_j * r_j) / sum(w_j),
    -1.5,
    1.5,
)
```

`continuity_j` is 1 for the newest meeting. For older meetings it is `exp(-max(0, gap_to_next_newer_days - 270) / 365)`. `era_j` is 1 for the target season, 0.65 for the immediately prior season, and 0 otherwise. `competition_j` is 1 only in the target competition; other meetings are excluded. `orientation_j` is 1 for the same home/away orientation and 0.9 when reversed. Fewer than two usable meetings produces zero.

Only `secondary_matchup_prior` is predictive. It is a required `float64` in `[-1.5, 1.5]`. Audit-only fields are `h2h_usable_meeting_count` (`uint8`, 0–5), `h2h_effective_weight` (non-negative `float64`), `h2h_relevance` (`float64`, 0–1), nullable non-negative `h2h_latest_age_days`, and `uint8` same/reversed-orientation counts (each 0–5).

## Leakage controls

- Resolve team aliases before constructing unordered pairs.
- Require every prior kickoff to be strictly earlier than the target kickoff.
- Seal same-kickoff batches.
- Derive each residual from a baseline forecast that could not observe that meeting's result.
- Exclude the target outcome and every future match.
- Use only the authorized development snapshot.

## Contingent hypothesis and admission design

The exact future hypothesis is: with every non-H2H model choice frozen, the one bounded residualized H2H prior improves weighted joint-score log loss by at least `0.003`, with a block-bootstrap 95% delta interval wholly below zero, without material calibration or secondary-metric degradation.

The future study would use chronological, leave-domain-out, and leave-team-out validation; per-domain, macro, and weighted results; joint-score and 1X2 log loss; Brier; RPS; total-goal CRPS; calibration; and block-bootstrap intervals. All gates must pass:

- weighted joint-score delta at most `-0.003`, with its 95% interval upper bound below zero;
- weighted 1X2 log-loss delta interval upper bound at most zero;
- negative joint-score point delta in at least three domains, no domain point delta above `0.02`, and each leave-domain-out interval upper bound at most `0.05`;
- Brier and RPS delta interval upper bounds at most `0.01`, and total-goal CRPS at most `0.02`;
- each outcome calibration slope in `[0.8, 1.2]`, absolute intercept at most `0.25`, slope interval width at most `0.4`, intercept interval width at most `0.3`, and candidate absolute calibration error no worse than baseline.

## Data and next owner decision

The current design would have only 169 usable targets, all from one domain. Before implementation, require at least 600 targets with 2+ usable meetings and 300 with 3+, spanning at least three competitions with at least 150 two-meeting targets in each. Relative to current coverage, that means at least 431 additional 2+ targets and 180 additional 3+ targets, including qualifying coverage in at least two competitions beyond Bundesliga.

The suggested next data scope is the immediately preceding full season for Premier League, La Liga, and Serie A, followed by another coverage-only check. Acquisition is not authorized.

The next owner authorization must first authorize this bounded development-history acquisition. If the coverage floor passes, a separate owner decision must authorize implementation, frozen preregistration, fitting, and a development-only comparison. Confirmation use, promotion, and V6 remain outside scope.
