# Feature Research

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Gated portfolio, not blanket authorization:** only the narrowly scoped minimal Phase 3A xG hypothesis is recorded as authorized. Every additional experiment requires a registered proposal and appropriate owner decision. Diagnostic/tag methods are descriptive only.

---

### 8.1 Reference features

Maintain simple reference models using only:

- home advantage;
- dynamic team attack and defence strength;
- time decay;
- competition and season structure;
- coherent score distribution.

All richer candidates must beat or complement these references under the same target set.

### 8.2 xG, xGA, and expected-performance suite

The **proposed broader Phase 3 expected-performance programme** must not be described as “xG alone.” The ablations below are **not** collectively authorized by the 20 September decision, which permits only one bounded minimal xG goal-model hypothesis. After separately approved expansion, test a balanced attacking and defensive family:

#### Primary rolling features

- exponentially weighted xG for and xGA;
- non-penalty xG for and non-penalty xGA;
- xG difference;
- xG and xGA per 90;
- shot volume for and against;
- xG per shot for and against;
- open-play and set-piece xG for and against where semantics are reliable;
- home/away splits with shrinkage toward the team total;
- effective sample size and uncertainty for every aggregate.

#### Derived features

- opponent-adjusted attacking xG strength;
- opponent-adjusted defensive xGA strength;
- expected goal difference strength;
- goals minus xG with shrinkage, representing uncertain finishing deviation;
- goals conceded minus xGA with shrinkage, representing uncertain defensive/goalkeeping deviation;
- trend features comparing short and medium windows;
- schedule-strength-adjusted form;
- season-to-date and cross-season priors with controlled decay.

#### Multi-window design

Use a small pre-registered set such as:

```text
short: previous 5 eligible matches
medium: previous 10 eligible matches
long: previous 20 eligible matches or previous-season carryover
```

The final windows and decay values must be selected on training data only. Do not search dozens of windows against the evaluation set.

#### Required ablations

```text
A: goals-only reference
B: xG-for only
C: xG-for + xGA
D: xG/xGA + shot volume and chance quality
E: opponent-adjusted xG/xGA
F: E + shrunk finishing/goalkeeping residuals
```

This sequence identifies where any gain actually comes from.

### 8.3 Game-state-adjusted expected performance

Raw xG and shot totals may partly describe how a match unfolded rather than only the pre-match strength of a team. A team protecting a lead, chasing a deficit, or playing with a numerical advantage can generate a different event profile.

Test this as a bounded research family:

1. raw rolling xG/xGA reference;
2. features stratified by leading, drawing, and trailing states;
3. 11v11-only features where event semantics are reliable;
4. training-derived reweighting toward a documented reference state;
5. raw plus adjusted features with regularization.

Rules:

- adjustment weights and reference states are fitted on training data only;
- red cards and score states from a completed historical match may inform later fixtures, never that match's own pre-match forecast;
- retain both raw and adjusted values with lineage;
- use effective sample size and missingness flags because some state slices will be sparse;
- reject the adjustment if it does not improve unseen proper scores, calibration, or stability.

### 8.4 H2H as a residualized contextual feature

Raw H2H tends to reproduce team-strength differences already present in the base model. MatchForge should instead calculate whether a pairing repeatedly behaves differently from what the historical pre-match model expected.

For meeting `m`:

```text
goal_residual_m = observed_goal_difference_m - expected_goal_difference_m
result_residual_m = one_hot_observed_result_m - predicted_result_probabilities_m
xg_residual_m = observed_xg_difference_m - expected_xg_difference_m
```

Aggregate only leakage-safe, historically issued or replayed out-of-sample predictions. Apply:

- exponential time decay;
- venue orientation;
- competition-type controls;
- opponent/team-strength controls;
- minimum effective sample size;
- empirical-Bayes or hierarchical shrinkage toward zero;
- uncertainty intervals.

A conceptual shrinkage form is:

```text
shrunk_pair_effect = n_eff / (n_eff + k) * weighted_pair_residual
```

`k` is fitted on training data. A pair with few meetings should contribute almost nothing.

Required H2H experiments:

1. no H2H;
2. raw recent H2H, research-only sanity check;
3. residualized H2H;
4. residualized H2H with decay and shrinkage;
5. model with pair random effects;
6. venue-specific versus venue-neutral H2H;
7. H2H mean-adjustment candidate;
8. H2H dispersion-only candidate;
9. H2H mean-plus-dispersion candidate;
10. score-correlation candidate where the sample and model family support it.

For each historical fixture, retain a point-in-time discrepancy record between the base forecast and eligible matchup evidence:

```text
delta_home_draw_away
delta_expected_home_and_away_goals
delta_expected_total_goals
delta_btts
score_distribution_divergence
effective_sample_size
uncertainty
```

The discrepancy is research evidence, not an automatic correction. Test whether it predicts future residuals on matches that were not used to estimate it.

Promote H2H only if it improves proper scores or calibration across multiple folds without damaging non-H2H fixtures.

### 8.5 Derby and rivalry display metadata

Derby status is frontend metadata, not a predictive feature. Build the sidecar from:

```text
is_rivalry
rivalry_type
same_city
regional_distance_band
neutral_or_shared_stadium
rivalry_recency
registry_version
review_status
forecast_effect_false
```

Offline descriptive analysis may estimate:

- whether the approved model is differently calibrated on derby fixtures;
- whether derby fixtures have different residual or score dispersion;
- whether draw, goals, cards, or fouls differ after matching on strength, competition, season, and venue.

These analyses diagnose model limitations and tag usefulness. They do not authorize a derby coefficient, a probability correction, a calibrator branch, or a simulator adjustment.

Required evaluation:

- compare derby fixtures with strength-, season-, venue-, and competition-matched non-derbies;
- report confidence intervals because derby samples are small;
- report global and competition-specific descriptive results;
- include a placebo pairing test to detect spurious pair effects;
- keep the registry as a `FixtureDisplayTagsV1` input only;
- verify that attaching, changing, or removing the derby tag leaves the immutable forecast byte-for-byte unchanged.

### 8.6 Fixture abnormality and forecast-risk layer

“Abnormal” must be split into three concepts.

#### A. Pre-match uncertainty

Known before kickoff:

- high predictive entropy;
- substantial disagreement between approved models;
- input outside the training distribution;
- low xG/event coverage;
- low team history or newly promoted team;
- high predicted-lineup entropy;
- recent manager change or large player turnover when qualified;
- unstable pair residuals;
- rivalry context with evidenced segment miscalibration, as a display-tag reason only;
- unresolved data conflict.

#### B. Historical surprise

Calculated from prior out-of-sample forecasts:

```text
outcome_surprise = -log(probability_assigned_to_observed_result)
score_surprise = -log(probability_assigned_to_observed_score_or_tail)
goal_residual = observed_total_goals - expected_total_goals
```

Track rolling mean, variance, tail frequency, and effective sample size for teams and pairs. Use shrinkage so a few remarkable matches do not create a permanent label.

#### C. Post-match shock explanation

Red cards, penalties, own goals, goalkeeper errors, and similar events explain why a result may be surprising. They are not pre-match evidence unless a separate, qualified pre-match feature predicts their risk.

#### Display-tag implementation

1. Standardize each component using training-period distributions.
2. Fit or define diagnostic weights using training/calibration data only.
3. Freeze band thresholds before evaluation.
4. Measure whether higher bands actually have worse calibration, wider residuals, or lower coverage.
5. If monotonicity fails, do not expose a single unpredictability tag; expose only verified component tags.
6. Set `forecast_effect = false` and attach tags only after the forecast is immutable.
7. Never flatten, widen, recalibrate, suppress, or otherwise change forecast probabilities because of a tag.

#### Appropriate product behaviour

- display a warning and reasons;
- display the intervals and full distributions already produced by the approved model without modification;
- retain every forecast product even when the frontend chooses to visually de-emphasize an exact score;
- separate `LOW_CONFIDENCE` from `DATA_INCOMPLETE`.

### 8.7 Context, load, and lineup-impact features

Prioritize objective, point-in-time context that changes the state of a team at kickoff:

- travel distance, direction, timezone change, and neutral venue;
- rest days, recent match count, recent extra time, and projected-core-XI minutes;
- international duty and days to the next fixture;
- manager transition stage, using documented match or day bands rather than one permanent flag;
- predicted and confirmed lineup strength deltas;
- XI, positional-unit, and formation continuity;
- competition strength, promoted/relegated state, and early-season prior uncertainty;
- observable competition-priority proxies such as table state, aggregate score, remaining fixtures, and historical rotation behaviour.

Do not encode a subjective `motivation` or `fatigue` number. Each family needs coverage analysis, a missing-data policy, and a separate ablation. Interactions such as short rest plus long travel plus high core-XI minutes may be tested only after the component features are qualified.

### 8.8 Additional feasible features

These should be tested after the expected-performance foundation:

#### A. Squad transition and player-strength bridge

- retained team and starting-XI minutes from the previous season and recent matches;
- departed core-player minutes and role-specific replacement deltas;
- newcomer projected minutes, integration time, and uncertainty;
- manager-change plus roster-churn interaction;
- promoted/relegated team transition priors;
- player plus-minus or another leakage-safe, shrunk player rating combined with team strength.

Required ablation: team rating only versus team plus projected-lineup player strength versus team plus lineup strength and squad-transition context.

#### B. Goalkeeper and finishing separation

- post-shot xG/xGOT faced and goals prevented, where qualified;
- projected goalkeeper start probability;
- pre-shot xGA retained as team-defence evidence;
- shooter finishing residuals with hierarchical shrinkage;
- separate open-play, set-piece, and penalty semantics.

Required ablation: xGA only versus xGA plus goalkeeper post-shot residual versus xGA plus goalkeeper and shrunk finishing effects. Sparse goalkeeper or shooter history must shrink strongly toward the population mean.

#### C. Pre-shot possession and territory

- box and final-third entries for and against;
- deep completions and touches in the box;
- high turnovers and transition frequency;
- field tilt and possession-to-shot conversion;
- settled-attack versus transition splits;
- game-state-adjusted versions where qualified.

These features test shot generation and suppression that ordinary xG cannot see because xG is conditioned on a shot occurring. They remain simpler challengers before xT, VAEP, or tracking-based models.

Dynamic strength, travel/load, manager transition, competition state, set pieces, style interactions, and lineup scenarios are already owned by Sections 8.1, 8.7, and 9; they are not repeated as a second feature family here.

### 8.9 Information hierarchy

Use this hierarchy to organize feature ownership and ablations, not to impose hand-written weights:

| Level | Information family | Examples |
| --- | --- | --- |
| 1 | Structural | Dynamic team and competition strength, home advantage, long-term performance |
| 2 | Current performance | Recent xG/xGA, shots, form, game-state-adjusted performance |
| 3 | Matchup | H2H residual, tactical/style and set-piece interactions |
| 4 | Squad | Availability, predicted/confirmed lineup, player impact, continuity |
| 5 | Match context | Travel, rest, congestion, venue, weather, referee, kickoff time |
| 6 | Information updates | Late injury, confirmed lineup, tactical confirmation, other pre-kickoff changes |

A later level does not override an earlier one. Each level contributes only through a leakage-safe candidate that proves incremental out-of-sample value. The resulting `MatchupIntelligenceV1` layer must publish component coverage and uncertainty.

`FixtureDisplayTagsV1` sits outside this hierarchy. Derby and unpredictability tags are never candidate model features.

### 8.10 Deferred feature families

Do not make these dependencies of the near-term roadmap:

- xT, VAEP, or Atomic-VAEP before xG/xGA evidence;
- social-media sentiment or narrative features;
- unverified injury scraping;
- player market value as a shortcut for player ability;
- tracking-data pressure features without licensed, consistent coverage;
- graph neural networks or embeddings before simpler challengers;
- referee or weather effects without reliable historical publication times;
- LLM-generated probability corrections.

---

## 9. Modelling ladder

Evaluate models in increasing complexity.

### Level 0: references

- historical base rates;
- Elo result model;
- independent Poisson;
- Dixon-Coles with time decay.

### Level 1: dynamic attack and defence

- dynamic Poisson or Dixon-Coles attack/defence state;
- hierarchical competition and promoted-team priors;
- state-space or weighted Bayesian candidate;
- home advantage allowed to vary by competition and time.

### Level 2: expected-performance parameters

- goal intensity informed by opponent-adjusted xG and xGA;
- raw versus game-state-stratified or adjusted expected-performance candidates;
- separate attack and defence contributions;
- uncertainty from limited observations carried forward;
- Negative Binomial or other over-dispersion only if diagnostics justify it.

### Level 3: contextual challengers

- `MatchupIntelligenceV1`, including residualized H2H and qualified style interactions;
- `TravelAndFixtureLoadV1`, manager transition, and competition state;
- `LineupImpactV1` predicted and confirmed scenarios;
- `SquadTransitionV1` and team-plus-player strength;
- `GoalkeeperShotStoppingV1` where qualified post-shot data exists;
- `PreShotThreatProfileV1` where qualified event sequences exist;
- explicit forecast horizon and immutable revision context.

Derby and unpredictability tags are not part of any modelling level.

### Level 4: direct machine-learning challengers

- constrained LightGBM or CatBoost models;
- direct 1X2 and totals prediction;
- monotonic or regularized treatment where domain constraints are justified;
- probability calibration fitted out of fold.

### Level 5: ensembles

- combine only independently useful and calibrated models;
- learn weights on a distinct calibration window;
- compare with uniform averaging;
- reject stacking if it adds instability, latency, or minimal gain.

No level is automatically promoted because it is newer or more complex.
