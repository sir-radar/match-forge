# H2H Context V1

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Source-derived proposed field contract.** Require separate owner approval, point-in-time eligibility and implementation/schema review before production use. Residualized H2H is research-only until its own evaluation/promotion decision; the derby tag never enters this contract.

---

### 6.3 `H2HContextV1`

Required fields:

```text
unordered_team_pair
venue_orientation
eligible_meetings
effective_sample_size
time_decay_version
competition_mix
strength_adjustment_version
goal_residual_mean_and_variance
outcome_residual_mean_and_variance
xg_residual_mean_and_variance
cards_or_fouls_residuals_if_qualified
result_entropy
score_and_total_goal_entropy
goal_correlation_or_covariance
manager_continuity
squad_continuity
lineup_or_style_similarity_coverage
model_vs_h2h_distribution_discrepancy
last_meeting_age
coverage_flags
knowledge_cutoff
```

Do not make these primary inputs:

```text
raw_h2h_win_percentage
unadjusted_average_score
all-time meeting counts
friendly results mixed with league results
meetings played by materially different club identities
```

## Residualized secondary matchup prior

`MATCHFORGE_SECONDARY_MATCHUP_PRIOR_V1` is the reusable, development-research feature
defined by `football.forecasting.h2h_residual.H2HResidualV1`. It does not replace the
forecast snapshot. It consumes point-in-time eligible meetings and returns:

```text
secondary_matchup_prior
h2h_usable_meeting_count
h2h_effective_weight
h2h_relevance
h2h_latest_age_days
h2h_same_orientation_count
h2h_reversed_orientation_count
status
```

Only `secondary_matchup_prior` is predictive. Fewer than two usable meetings produces
zero with `INSUFFICIENT_H2H`; normal forecasting continues. `ContextualGoalAdjustmentV1`
applies the scalar anti-symmetrically to baseline log goal rates. This contract does not
authorize production use or promotion.
