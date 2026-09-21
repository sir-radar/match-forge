# Expected Performance Snapshot V1

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Source-derived proposed field contract.** Require separate owner approval, point-in-time eligibility and implementation/schema review before production use.

---

### 6.2 `ExpectedPerformanceSnapshotV1`

For each team immediately before a fixture, store:

```text
xg_for
xg_against
non_penalty_xg_for
non_penalty_xg_against
xg_difference
xg_per_shot
xg_against_per_shot
shots_for
shots_against
goals_for_minus_xg
goals_against_minus_xga
open_play_xg_for_and_against
set_piece_xg_for_and_against
minutes_leading_drawing_trailing
minutes_11v11_and_at_numerical_advantage_or_disadvantage
raw_and_candidate_game_state_adjusted_xg_xga
game_state_adjustment_version
rolling_window_definition
decay_parameter
effective_sample_size
opponent_adjustment_version
home_away_split
provider_and_semantic_version
knowledge_cutoff
```

Every value must include lineage and missingness state. Metrics from different xG providers are not interchangeable without an approved bridge and validation.
