> **Reference archive ONLY.** Exact content of the user-supplied PLAN; superseded for proposed organization by root `PLAN.md` and specialized supporting specifications. Not proof of repository status or authorization.

# MatchForge Implementation Plan

> Revision: 21 September 2026 — mandatory Rust simulation validation, preserving existing work  
> Purpose: update the attached plan in place to require Rust simulation validation for simulation-backed production forecasts and model promotion, without confusing Monte Carlo convergence with predictive calibration.  
> Status: PROPOSED roadmap change, not an authorization or implementation result. The repository's tracked `docs/project-status.json`, accepted architecture, evidence, and owner decisions override conflicting roadmap assertions. Nothing here changes frozen experiments, corpora, thresholds, decisions, failures, existing artifacts, or application code. Apply through an additive, evidence-backed reconciliation before implementation.

## 1. Mission

MatchForge is a provider-neutral football forecasting and simulation platform that produces reproducible, calibrated probability distributions for football matches.

The system must:

- estimate changing team attack and defence strength;
- use goals, xG, xGA, and other qualified pre-match information rather than depending on xG alone;
- preserve uncertainty instead of reducing every fixture to one confident score;
- identify known rivalries and expose them as frontend metadata without changing the forecast;
- identify fixtures with elevated forecast uncertainty or unusual historical behaviour and expose that assessment as frontend metadata without changing the forecast;
- use H2H only as a bounded, opponent-specific contextual signal;
- distinguish predicted lineups from confirmed lineups;
- produce coherent result, score, goals, BTTS, clean-sheet, and approved corner distributions;
- require the Rust Monte Carlo engine and its reproducible validation evidence for every newly published production fixture forecast by default and every simulation-capable candidate proposed for promotion, once the separately authorized engine has passed its acceptance gates; allow only explicitly approved and visibly labelled analytic-only fallback, with no retroactive effect on historical artifacts; retain analytic-only research and historical artifacts without retroactive simulation requirements;
- evaluate every material change with chronological, leakage-safe backtesting;
- preserve data, feature, model, calibration, simulation, and decision provenance;
- expose only capabilities supported by passed gates.

The objective is not maximum complexity or maximum accuracy on one test set. The objective is reliable, calibrated, explainable performance that generalizes across time, competitions, and fixture types.

## 2. Decisions introduced by this revision

| Proposal | Decision | Implementation rule |
| --- | --- | --- |
| Derby identification | Accept as display-only metadata | Use a versioned, reviewed rivalry registry. The derby tag must never enter features, parameters, calibration, simulation, or probability post-processing. |
| Historically abnormal fixtures | Accept as display-only metadata | Build a frontend tag from out-of-sample residuals, forecast uncertainty, model disagreement, drift, data quality, and known pre-match context. The tag cannot change the forecast. |
| xG plus xGA and other indicators | Accept | Build opponent-adjusted attacking and defensive expected-performance features. |
| H2H integration | Accept as a challenger | Use residualized, time-decayed, sample-size-shrunk pair history. Do not use raw win percentage as a dominant feature. |
| Matchup intelligence | Accept as a research layer | Combine qualified H2H residuals, tactical/style, manager, lineup, formation, and set-piece interactions without letting any one signal override the base model. |
| Travel, rest, and fixture load | Accept after data qualification | Derive objective load features from venues, kickoff times, minutes, extra time, and international duty; do not invent a subjective fatigue score. |
| Game-state-adjusted performance | Accept as a bounded challenger | Compare raw and state-stratified or reweighted xG/xGA features; do not assume adjustment improves forecasts. |
| Lineup impact and continuity | Accept after lineup qualification | Convert lineup scenarios into uncertain attack, defence, goalkeeper, and set-piece strength deltas. |
| Forecast horizons and revisions | Accept | Store every forecast immutably and evaluate information gained from later, point-in-time updates. |
| Squad-transition modelling | Accept after identity and lineup qualification | Measure retained minutes, role replacement, newcomer integration, and roster churn without using transfer fees or market value as ability shortcuts. |
| Goalkeeper shot-stopping | Accept after post-shot data qualification | Test post-shot xG/xGOT residuals with strong shrinkage and keep them separate from team defensive xGA. |
| Pre-shot possession and territory | Accept as a bounded challenger | Test box entries, deep completions, high turnovers, field tilt, and possession-to-shot conversion before adopting complex possession-value models. |
| Initial deployment shape | Accept modular monolith plus workers | Keep domain boundaries explicit in code and data contracts; split deployables only when scaling, fault isolation, or ownership evidence justifies it. |
| Training-serving implementation | One feature implementation | Historical replay and production forecasting must call the same versioned feature code to prevent training-serving skew. |
| Engineering readiness | Required before authoritative runs | CI, migrations, observability, SLOs, security checks, reproducible builds, rollback, restore, and cost budgets are phase gates rather than late hardening work. |
| Automatic recalibration after every surprise | Reject | Recalibrate only through governed rolling windows after drift and sample-size gates pass. |
| Assume every derby is unpredictable | Reject | Derby and unpredictability are separate display tags; neither modifies the forecast. |
| Let a frontend flag alter the forecast | Reject | Tag generation occurs after the immutable forecast and cannot feed back into any forecasting component. |
| Closing odds as model inputs | Keep excluded | Use point-in-time, legally usable odds only as an external benchmark unless separately authorized. |
| Post-match red cards, penalties, or errors as pre-match inputs | Reject | Store them as post-match shock explanations and future research labels only. |
| Mandatory Rust simulation validation | Adopt as a proposed product and promotion requirement, not an already authorized implementation | Once the separately authorized engine is operational, every newly published production fixture forecast needs a passing linked `SimulationValidationArtifactV1`, except an explicitly approved and visibly labelled analytic-only fallback; every simulation-capable promotion candidate must pass the same gate. Analytic-only research and previously published artifacts remain valid. |
| Simulation as a substitute for calibration | Reject | Monte Carlo samples test distribution implementation and numerical convergence; real held-out match outcomes, proper scores, and reliability measure predictive calibration. No automatic probability adjustment from simulated frequencies. |
| Complex simulation before forecast inputs work | Reject | Implement the minimal seeded Rust sampler only after statistical parameters and coherent calibrated distributions are defined; add event-rich simulation only on separate authorization and evidence. |

## 3. Current execution state carried forward

The last evidenced state in the supplied plan remains unchanged until newer repository evidence proves otherwise:

- Phase 1B: `PASS`.
- Phase 2B: `PASS`.
- Sprint 2 baseline: immutable `FAIL` with decision `RETAIN_FAIL_AND_STOP`.
- `DCV3_SHARED_MATCH_PACE_MIXTURE_V1`: implementation complete, deterministic feasibility passed, but the frozen training-only route ended in `TERMINAL_ROUTE_FAIL` at the `60/10` fold because it selected the lower `kappa = 0` boundary.
- The frozen 280 Sprint 2 targets were not accessed by that challenger and must remain outside all new routes.
- No model was promoted.
- Owner decision `RETAIN_SPRINT2_FAIL_CLOSE_SHARED_PACE_AND_AUTHORIZE_PHASE3_RESEARCH_V1` (20 September 2026) already authorizes **research only** for one bounded, minimal leakage-safe Phase 3A xG goal-model hypothesis using approved qualified Tier-A data; overall Phase 3 remains `BLOCKED`. Do not request this authorization again or infer broader permission.
- Evaluation V2 policy/corpus design and pre-registration are already authorized; the authoritative run requires a distinct owner decision after the independent corpus, thresholds, references, and policy are frozen.
- Rust simulation implementation, new simulation evaluation, and simulation-backed production enablement are **NOT** covered by that owner decision. This revision proposes a separate authorization; it does not grant it. Existing Sprint 2 results and the 280-target firewall remain unchanged.

The original Sprint 2 result must never be changed, retried under relaxed rules, or reinterpreted as a pass.

## 4. Governing principles

1. Use only information demonstrably available at the forecast knowledge cutoff.
2. Batch fixtures with the same kickoff time so one result cannot affect another simultaneous forecast.
3. Keep raw observations immutable and record publication, observation, ingestion, and correction times.
4. Quarantine unresolved identities, incompatible semantics, and contradictory records.
5. Separate data qualification, research authorization, evaluation authorization, and model promotion.
6. Pre-register hypotheses, feature families, tuning limits, target sets, and failure rules.
7. Compare every new feature family with an ablation that removes only that family.
8. Prefer partial pooling and shrinkage to unstable small-sample averages.
9. Evaluate probabilities with proper scoring rules and calibration, not accuracy alone.
10. Report results by competition, season, favourite strength, fixture type, and data-quality tier.
11. Keep learning models, parameter generation, distribution-coherent calibration, Rust sampling, numerical validation, and API delivery separate; never calibrate against the simulator's own synthetic outcomes.
12. A valid research result may be “no improvement; retain the simpler model.”
13. Never use a post-match explanation to improve the already-issued pre-match forecast.
14. Never allow a warning label to hide poor probability calibration.
15. Frontend fixture tags are downstream metadata: changing, adding, or removing a tag must leave every forecast probability and simulator input unchanged.
16. Every transformation, feature, contract, model, and operational run has one named owner and one source of truth.
17. Prefer a modular monolith and independently scalable workers until measured load or fault isolation justifies additional services.
18. Historical replay and production forecasting must use the same versioned feature implementations.

## 5. Target architecture

```text
providers
  -> immutable raw observations
  -> provider-specific normalization
  -> identity resolution and quarantine
  -> point-in-time match/event/lineup/odds views
  -> leakage-safe feature snapshots
  -> matchup, squad, and load context
  -> statistical candidate models
  -> validated match parameters / coherent base distribution
  -> out-of-sample-fitted calibration (coherent distribution-level policy)
  -> sealed immutable forecast candidate, not yet public
  -> REQUIRED authorized Rust sampling and parity / convergence validation
  -> immutable linked SimulationValidationArtifactV1
  -> publish unchanged forecast + validated simulation evidence atomically
  -> optional display-tag and diagnostic sidecar
  -> API response composition and monitoring
```

### Boundary rules

- The feature layer calculates only pre-match eligible values.
- Statistical models estimate team strengths, goal intensities, and outcome distributions.
- The parameter generator converts model state and match context into simulator inputs.
- Rust samples only validated parameter/distribution inputs; it does not learn hidden team strength, tune calibration, or alter forecast probabilities in response to sampling noise.
- The finalized forecast candidate is sealed before simulation. For a simulation-backed production product, publication is gated on a passing linked simulation-validation artifact; a failure retains the candidate internally for diagnosis but publishes neither an unvalidated simulated product nor a silently altered forecast. Already-published analytic artifacts remain immutable and retrievable. An explicitly authorized analytic-only fallback must be labeled and must never masquerade as simulation-validated.
- Once publication passes, the immutable forecast is completed before optional derby or unpredictability enrichment is attached.
- The display-tag and diagnostic layer describes fixture categories, confidence, and evidence quality. It cannot be joined into model features, parameter generation, simulation, calibration, or probability post-processing.
- Removing the display-tag sidecar must produce exactly the same forecast artifact.
- The calibration layer is fitted only on training/calibration periods and is versioned separately.

### Initial deployment shape

Start with one modular application and separately runnable worker processes rather than a network of microservices. Maintain these code boundaries from the first release:

```text
domain          team identity, fixture time, eligibility, probability types
ingestion       provider adapters, raw writes, corrections, quarantine
features        point-in-time transformations shared by replay and production
forecasting     model loading, parameter generation, calibration
simulation      Rust deterministic sampling and validation; Python owns analytic modelling and calibration
diagnostics     post-forecast risk assessment and display tags
delivery        API schemas, persistence, authentication, rate limits
operations      jobs, observability, audit, deployment and recovery
```

Rules:

- domain modules must not import provider, transport, database, or framework code;
- provider-specific logic ends at normalization adapters;
- batch replay and production forecasting call the same feature library with explicit cutoff and version arguments;
- long-running ingestion, replay, training, and simulation use durable workers with idempotent job keys;
- a new deployable service requires measured scaling pressure, a fault-isolation need, or a clear ownership boundary;
- cross-module calls use typed interfaces and versioned contracts, even while modules share one deployment.

### Single-source-of-truth ownership

| Concern | Authoritative owner | Forbidden duplication |
| --- | --- | --- |
| Provider semantics | Provider adapter and qualification report | Reinterpreting raw fields inside models or API handlers |
| Team and fixture identity | Identity resolver | Local name matching in feature or UI code |
| Feature definition | Versioned feature library and contract | Separate training and serving transformations |
| Dataset membership | Frozen corpus manifest | Ad hoc query filters inside experiments |
| Model state | Model registry artifact | Untracked files or embedded parameters in services |
| Calibration | Versioned calibrator artifact | Endpoint-specific probability adjustment |
| Simulation inputs | Versioned match parameter / calibrated distribution contract owned by forecasting | Simulator-side strength estimation or recalibration |
| Simulation validation | `SimulationValidationArtifactV1` produced by approved Rust engine | API or frontend inventing run counts, parity, convergence, or approval |
| Display tags | Post-forecast sidecar | Tag logic inside forecast generation or calibration |
| Public response | Versioned API schema | Frontend reconstruction of model semantics |

If two sections mention the same concern, this table determines which artifact owns the executable rule; other sections define gates, tests, or sequencing only.

## 6. New and revised data contracts

### 6.1 `RivalryDefinitionV1`

Required fields:

```text
rivalry_id
unordered_team_pair
valid_from
valid_to
rivalry_type
geographic_scope
competition_scope
source_references
review_status
reviewed_by
reviewed_at
notes
```

Allowed `rivalry_type` values initially:

```text
SAME_CITY
REGIONAL
HISTORIC
CULTURAL_OR_POLITICAL
INSTITUTIONAL
```

Rules:

- geographic proximity may nominate a candidate but cannot automatically declare a derby;
- a pair may have more than one type;
- all entries need temporal validity because club identity, location, and rivalry relevance can change;
- friendly matches are excluded unless a research contract explicitly includes them;
- neutral venues and shared stadiums are stored separately from rivalry type;
- unreviewed candidates cannot become production features.

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

### 6.4 `ForecastRiskAssessmentV1`

Required components:

```text
predictive_entropy
model_disagreement
out_of_distribution_score
data_quality_risk
lineup_uncertainty_if_available
team_state_change_risk
pair_history_volatility
rivalry_display_context
calibration_segment_risk
drift_status
reason_codes
risk_band
assessment_version
knowledge_cutoff
forecast_effect
```

Initial risk bands:

```text
LOW
NORMAL
ELEVATED
HIGH
INSUFFICIENT_DATA
```

`forecast_effect` is always `false`. The assessment is calculated from an already-issued forecast plus eligible contextual evidence and cannot be read by any forecasting component. The system must publish the components and reason codes, not only one opaque score.

### 6.5 `FixtureDisplayTagsV1`

This sidecar is the only production route for derby and unpredictability labels.

```text
fixture_id
forecast_id
tags
reason_codes
evidence_snapshot_ids
effective_sample_size
tag_confidence_or_evidence_status
computed_at
knowledge_cutoff
tag_policy_version
forecast_effect
```

Initial tags:

```text
DERBY
UNPREDICTABLE
HISTORICALLY_VOLATILE
HIGH_FORECAST_UNCERTAINTY
HIGH_MODEL_DISAGREEMENT
OUT_OF_DISTRIBUTION
DATA_INCOMPLETE
INSUFFICIENT_EVIDENCE
```

Rules:

- `forecast_effect` is always `false`;
- the sidecar is attached only after the forecast artifact is immutable;
- `DERBY` comes only from the reviewed rivalry registry;
- `DERBY` never implies `UNPREDICTABLE`;
- `UNPREDICTABLE` may be emitted only by a frozen, validated diagnostic policy and must include the component reason codes that caused it; otherwise expose only the component tags;
- `HISTORICALLY_VOLATILE` requires prior out-of-sample residuals, shrinkage, and a minimum effective sample size;
- `HIGH_FORECAST_UNCERTAINTY` describes the forecast distribution already produced and does not widen or flatten it;
- frontend presentation may use badges or warnings but must render the original probabilities unchanged;
- tags are excluded from training matrices, calibrator inputs, match parameters, simulator inputs, and forecast-revision triggers.

### 6.6 `PostMatchShockLabelV1`

This contract is available only after the match and is never joined into its own pre-match snapshot.

Possible labels, when provider semantics are qualified:

```text
early_red_card
multiple_red_cards
penalty_event
own_goal
goalkeeper_error
extreme_finishing_overperformance
extreme_goalkeeping_overperformance
injury_forced_substitution
match_abandonment
data_correction
```

Use it to explain forecast errors, build stratified evaluation, and study whether any pre-match indicators exist. Do not use the label itself to predict the same match.

### 6.7 `FeatureAvailabilityV1`

Each feature must declare:

```text
event_time
observation_time
provider_publication_time
ingestion_time
correction_time
knowledge_cutoff
eligibility_status
missingness_reason
source_lineage
```

### 6.8 `MatchupIntelligenceV1`

This contract is a wrapper for opponent-specific evidence. It prevents H2H from becoming a standalone source of truth.

```text
fixture_id
base_model_snapshot_id
h2h_context_id
style_interaction_features_if_qualified
manager_matchup_features_if_qualified
lineup_and_formation_interactions_if_qualified
set_piece_matchup_features_if_qualified
component_coverage
component_uncertainty
adjustment_mode
reason_codes
knowledge_cutoff
version
```

`adjustment_mode` must be one of `DISPLAY_ONLY`, `MEAN_CANDIDATE`, `DISPERSION_CANDIDATE`, `CORRELATION_CANDIDATE`, or `PROMOTED`. Production may use only a separately promoted mode.

Derby registry membership is deliberately absent. Rivalry metadata belongs only to `FixtureDisplayTagsV1`; H2H and other matchup candidates must prove value independently of the derby tag.

### 6.9 `TravelAndFixtureLoadV1`

```text
origin_venue_id
destination_venue_id
distance_km
travel_direction
timezone_delta
international_or_border_crossing
neutral_venue
rest_days
matches_last_3_7_14_30_days
minutes_by_projected_core_xi
recent_extra_time_minutes
recent_international_duty
days_to_next_match
next_match_competition
travel_load_features
recovery_disadvantage_features
fixture_congestion_features
effective_coverage
knowledge_cutoff
version
```

The first implementation must expose objective components. A learned composite is allowed only after an ablation shows stable incremental value.

### 6.10 `LineupImpactV1`

```text
lineup_mode
lineup_scenarios
player_start_probabilities
attack_strength_delta
defence_strength_delta
goalkeeper_strength_delta
set_piece_strength_delta
xi_continuity
defensive_midfield_attacking_unit_continuity
minutes_together
formation_continuity
replacement_uncertainty
residual_scenario_mass
knowledge_cutoff
version
```

Predicted and confirmed lineups are different forecast contracts. Strength deltas must preserve player and scenario uncertainty instead of substituting one guessed XI.

### 6.11 `ForecastRevisionV1`

```text
forecast_id
fixture_id
issued_at
knowledge_cutoff
forecast_horizon
supersedes_forecast_id
model_feature_and_calibration_ids
probability_distributions
revision_reason_codes
new_information_ids
distribution_change_metrics
version
```

Supported research horizons may include `7d`, `3d`, `24h`, `6h`, `1h`, `15m`, and `CONFIRMED_LINEUP`, but only where historical availability can be reconstructed. A revision creates a new artifact and never overwrites an earlier forecast.

### 6.12 `SquadTransitionV1`

```text
retained_minutes_share
retained_starting_minutes_share
departed_core_minutes
newcomer_projected_minutes
newcomer_matches_and_minutes_with_team
role_replacement_deltas
goalkeeper_change
manager_and_squad_change_interaction
promoted_or_relegated_transition
effective_sample_size
identity_and_lineup_coverage
knowledge_cutoff
version
```

This contract should detect rapid changes that a slow-moving team rating may miss. It must use actual roles, appearances, minutes, and availability known at cutoff—not transfer fees, rumours, or subjective reputation.

### 6.13 `GoalkeeperShotStoppingV1`

```text
goalkeeper_id
post_shot_xg_or_xgot_faced
goals_conceded_excluding_own_goals
goals_prevented_residual
cross_and_set_piece_claim_context_if_qualified
rolling_windows
opponent_and_shot_mix_adjustment
shrinkage_and_uncertainty
projected_start_probability
provider_semantic_version
knowledge_cutoff
version
```

Ordinary xGA measures the chances allowed before the shot outcome; it does not cleanly isolate goalkeeper shot-stopping. Use post-shot information only where its trajectory and on-target semantics are qualified. Reject raw save percentage as a standalone ability signal.

### 6.14 `PreShotThreatProfileV1`

```text
box_entries
deep_completions
final_third_entries
high_turnovers
field_tilt
possession_to_shot_rate
possession_to_box_entry_rate
transition_and_settled_attack_splits
for_and_against_values
game_state_adjustment_version
provider_semantic_version
effective_sample_size
knowledge_cutoff
version
```

This bounded family tests whether a team consistently creates or suppresses dangerous possessions before a shot occurs. It precedes xT/VAEP adoption and must not treat possession volume as chance quality.

## 7. Data programme

### 7.1 Required coverage before advanced modelling

Qualify at least three competition-season groups with enough history to test both within-league and cross-league generalization. The exact corpus belongs in the frozen Evaluation V2 policy.

For each competition-season, measure:

- fixtures and final scores;
- kickoff-time completeness and timezone correctness;
- team identity resolution;
- event and shot coverage;
- xG/xGA availability or ability to compute xG from qualified events;
- post-shot xG/xGOT, shot-target, trajectory, and goalkeeper identity coverage;
- possession-sequence, box-entry, turnover, and territory-event coverage;
- lineup, availability, registration, transfer, and historical player-minute coverage;
- manager, stadium, travel, rest, and promotion status coverage;
- odds observation-time coverage for benchmarking only;
- corrections, conflicts, and quarantined records.

Do not represent incomplete rich-event coverage as complete competition coverage. StatsBomb Open Data contains selected competitions and 360 data only for selected matches.

### 7.2 Data tiers

```text
TIER_A: qualified event/shot data with enough semantics to build xG
TIER_A_PLUS: Tier A plus qualified event sequences and post-shot/goalkeeper semantics
TIER_B: qualified fixtures, results, and aggregate match statistics
TIER_C: contextual data such as lineups, availability, managers, venues, weather, or referees
TIER_M: market benchmark data with exact observation times
```

Forecasts must declare the tier used. A model trained on Tier A cannot silently fall back to differently defined aggregate fields.

### 7.3 Feasible context sources

Prioritize context that is stable, obtainable, and time-stamped:

- rest days and fixture congestion;
- home, away, and neutral venue;
- travel distance where venue coordinates are reliable;
- promoted/relegated team status;
- manager change date;
- competition stage and two-leg state;
- predicted or confirmed lineup when qualified;
- rivalry registry membership.

Defer weather, referee style, injuries, suspensions, and tactical formations until historical availability time and coverage can be proved.

## 8. Feature programme

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

## 10. Probability and calibration requirements

Every forecast must provide coherent probabilities for approved products.

Minimum outputs:

```text
home/draw/away
home and away goal distributions
exact-score matrix with explicit tail
total-goal distribution
over/under approved lines
BTTS
clean sheets
goal range probabilities
expected goals for each team
prediction intervals or credible intervals
forecast-risk components and band
```

Calibration policy:

- fit calibration only on predictions generated without seeing their outcomes;
- compare uncalibrated, sigmoid/temperature-style, and isotonic candidates where sample size permits;
- assess overall and segment calibration;
- reject calibrators that improve one metric while materially degrading proper scores or sharpness;
- version calibrators by model, competition scope, target, and time period;
- ensure the final joint distribution is coherent before Rust sampling: if a proposed 1X2-only calibrator breaks coherence with exact scores, totals, or BTTS, reject it or use a separately evaluated distribution-coherent reconciliation; do not let Rust silently reconcile inconsistent market probabilities;
- never fit or refit calibration to repeated draws generated from the model itself; synthetic replicates share the same model assumptions and are not independent football outcomes;
- never recalibrate from a single match;
- trigger review, not automatic promotion, when drift thresholds are crossed.

## 11. Mandatory Rust simulation and validation policy

**Product decision:** Rust Monte Carlo is the **default mandatory gate for all newly published production fixture forecasts** and an independent gate for promoting every simulation-capable candidate, **after** separate implementation authorization and engine acceptance. It is not a retroactive requirement for completed baselines, immutable historic evidence, or the already authorized minimal Phase 3A xG research. It is not permission to expand the currently deferred Rust scaffold. Detailed executable criteria live in `docs/simulation/mandatory-validation.md`; the immutable sidecar schema lives in `docs/contracts/simulation-validation-v1.md`.

### 11.1 What simulation proves — and what it cannot

- **Numerical/structural validation:** Rust's seeded samples approximate the same finalized probability distribution as the analytic model within a pre-registered Monte Carlo tolerance. Check 1X2, score, total goals, approved over/under lines, BTTS, clean sheets, corners if independently qualified, moments, dependence, and explicit tail mass.
- **Predictive calibration:** use forecasts issued without future outcomes and compare them with *real* later results across many distinct matches. Report proper scores, reliability, uncertainty, segments, and chronological stability. Simulation frequencies alone cannot improve or establish real-world calibration.
- **Posterior/predictive checking:** on a separately authorized development or untouched evaluation protocol, compare simulated aggregate statistics with observed match statistics to identify potential misfit. Any proposed fix starts a new registered training-only hypothesis; never tune on frozen evaluation observations or automatically alter the published forecast.
- Simulation is a validation and scenario product. If simulation-derived probabilities are ever proposed as the forecast's authoritative output, define a new model contract and separately prove scoring, coherence, calibration, and promotion; never silently replace analytic probabilities with Monte Carlo frequencies.

### 11.2 Mandatory production and promotion gates

1. Python generates eligible point-in-time inputs and approved model parameters; calibration parameters are fitted only on earlier out-of-sample real forecasts and final distributions are coherent before sampling.
2. Seal the forecast candidate and its canonical probability hash. Rust receives only approved versioned parameters/distributions and an independent seed schedule: no tags, post-match information, raw training labels, or model fitting.
3. The Rust engine produces reproducible runs and a `SimulationValidationArtifactV1` linked to the candidate hash and engine build. Required results include run count, seed policy, convergence, event coverage, parity and tail checks, numerical precision, and failure reasons.
4. A **new production fixture forecast** may be published as simulation-validated only if all mandatory numerical checks pass; after activation this is the default required production route, not an optional decoration. Publish the identical sealed forecast and its validation evidence, using an atomic/recoverable publication boundary; never mutate probabilities to make parity pass.
5. If simulation fails, times out, or is unavailable, retain the sealed candidate for debugging and return an explicit `SIMULATION_UNAVAILABLE`/unavailable state for the simulation-required product. Existing published forecasts remain retrievable. An analytic-only response is allowed only under a separately approved policy, prominently marked `ANALYTIC_ONLY`, and never advertised as validated simulation output.
6. Every simulation-capable model proposed for promotion requires a passing reference-fixture suite and representative batch parity/convergence/cost evidence. Promotion still additionally requires real-outcome evaluation and an explicit owner decision. A passing simulation test is never a predictive promotion decision.
7. Optional post-forecast enrichment remains independent: tag generation may fail without invalidating a successfully published forecast or its simulation evidence. Tags cannot enter the simulator.

### 11.3 Initial scope and counts

Implement a **minimal** Rust sampler against the existing approved score distribution first. Defer time-varying hazards, red cards, substitutions, event-by-event corners, multi-scenario lineups, and H2H counterfactuals until their separate contracts and data sources pass qualification.

| Use | Initial engineering count (not an accuracy guarantee) |
| --- | ---: |
| Development / smoke checks | 1,000 |
| Routine production candidate | 10,000 |
| Detailed inspection / difficult convergence | 100,000 |
| Long-run capacity benchmark | Up to 1,000,000, only if justified |

Counts are configurable **starting points**, not fixed pass conditions. Run additional independent seeded batches until event-specific pre-registered confidence half-widths and parity thresholds pass or a compute/time budget is reached; otherwise mark `INCONCLUSIVE`, not `PASS`. Rare outcomes may require much larger samples or an approved analytic calculation. Record effective draws, independence/variance assumptions, numerical tolerances, seeds, hardware/build, elapsed time, and cost. Prefer analytic exact probabilities when available; never degrade them merely to add Monte Carlo noise.

### 11.4 Supported future scenario scope (authorization required)

After minimal engine acceptance, separately qualify any of: goal timing and current score; lineup scenarios; posterior parameter uncertainty; match-state-dependent goal rates; dependence between team scores; qualified red-card or substitution hazards; and independently validated corners processes. If sampling uncertain parameters, include the scenario weights and uncertainty source; do not mistake multiple seeds for new uncertainty about team strength.

### 11.5 Validation requirements

- deterministic seed schedule, repeatability across identical build/platform where promised, and well-defined cross-platform tolerance otherwise;
- parity against analytic distributions wherever analytic references exist;
- convergence across independently seeded batches with confidence intervals and explicit failure/inconclusive handling;
- normalized 1X2/exact score/market relationships, monotone lines, finite values, realistic support, and preserved score-tail mass;
- distribution-level and segment-level comparison with real outcomes under the separately frozen evaluation contract;
- bounded latency, throughput, memory, costs, cancellation, idempotent retries, and reproducible immutable artifacts;
- no feature training, calibration, promotion, or probability changes in Rust or triggered automatically by a simulation discrepancy.

The engine is the mandatory default validation dependency for **all new production fixture publication** after separate approval, except a separately approved and explicitly labelled analytic-only fallback; it is not a reason to reopen Sprint 2, access its frozen 280 targets, or stop authorized analytic-only research.

### H2H counterfactual simulation suite

When H2H parameter candidates reach simulation research, run matched variants for the same fixture snapshot using common random numbers and the same seed schedule:

```text
S0: approved base parameters, no H2H adjustment
S1: H2H-informed mean adjustment only
S2: H2H-informed dispersion adjustment only
S3: H2H-informed mean plus dispersion
S4: H2H-informed score correlation, only if separately qualified
```

Compare full distributions, not one historical result or one simulation run. Record changes in 1X2, expected goals, total goals, BTTS, exact-score distribution, and tails. Estimate every adjustment on training data, freeze it before the evaluation window, and evaluate each variant on untouched matches. A same-seed counterfactual isolates the effect of the H2H parameter change; it does not by itself prove predictive value.

## 12. Evaluation V2

### 12.1 Pre-registration

Freeze before an authoritative run:

```text
corpus and exclusions
competition-season groups
knowledge cutoff rules
same-kickoff batching
warm-up and minimum history
data tier requirements
forecast horizons and revision rules
reference models
candidate feature families
forbidden display-tag columns
hyperparameter budget
calibration windows
primary and secondary metrics
segment definitions
bootstrap method
promotion thresholds
latency and complexity budgets
failure and stopping rules
```

The original frozen 280 Sprint 2 targets are permanently excluded.

### 12.2 Temporal evaluation design

Use rolling-origin or expanding-window evaluation:

```text
train -> optional tuning -> calibration -> untouched evaluation
```

Requirements:

- no random match split for authoritative evidence;
- same-kickoff fixtures predicted as one batch;
- hyperparameters selected without evaluation outcomes;
- all feature snapshots materialized at the historical knowledge cutoff;
- one immutable prediction artifact per model and fixture;
- separate within-competition, future-season, and cross-competition results;
- evaluate each supported forecast horizon separately and retain every superseded forecast;
- attribute forecast revisions to point-in-time information changes without using the later outcome.

### 12.3 Metrics

Primary metrics:

- multiclass log loss for 1X2;
- multiclass Brier score;
- ranked probability score for ordered away/draw/home outcomes;
- CRPS or an approved discrete equivalent for goal distributions;
- log score for the score matrix with a defined tail policy;
- calibration intercept/slope and reliability diagrams;
- interval or prediction-set coverage and width.

Secondary metrics:

- accuracy and top-k exact-score hit rate;
- MAE for expected goals or total goals;
- discrimination/AUC for binary markets;
- sharpness conditional on calibration;
- latency, memory, artifact size, and failure rate.

Never select a model primarily by exact-score accuracy or simulated betting profit.

### 12.4 Mandatory segments

Report every candidate for:

```text
competition
season
home/draw/away
favourite-probability band
expected-total-goals band
derby versus non-derby
H2H effective-sample band
risk band
newly promoted teams
manager-change window
predicted versus confirmed lineup
forecast horizon and revision count
travel-load and rest band
lineup-continuity and lineup-impact band
retained-minutes and squad-transition band
goalkeeper post-shot coverage band
pre-shot threat coverage band
game-state-adjustment coverage
style-interaction coverage
data tier and coverage band
```

Small segments need confidence intervals and may be descriptive only.

### 12.5 Statistical comparison

- paired bootstrap at match or matchday block level;
- confidence intervals for score differences;
- pre-defined practical-equivalence margins;
- multiple-comparison control or a strictly bounded candidate family;
- stability checks across folds and competitions;
- no promotion based on one favourable segment.

### 12.6 Feature-family experiment order

Run one bounded family at a time:

1. Baseline reproduction and infrastructure validation.
2. xG-for challenger.
3. xG-for plus xGA challenger.
4. opponent-adjusted expected-performance challenger.
5. raw versus game-state-adjusted expected-performance challenger.
6. travel, rest, and fixture-load challenger.
7. dynamic state-space challenger.
8. residualized H2H challenger.
9. H2H counterfactual mean, dispersion, and correlation simulation candidates.
10. derby and volatility tag validity analysis, display-only.
11. lineup impact and continuity challenger.
12. team-plus-player strength and squad-transition challenger.
13. goalkeeper post-shot shot-stopping challenger where coverage permits.
14. pre-shot possession and territory challenger where coverage permits.
15. style and tactical interaction challenger where coverage permits.
16. forecast-diagnostic tag validation, display-only.
17. forecast-horizon and revision information-value analysis.
18. ensemble challenger.
19. independently authorized Rust simulation validation and comparison: parity/convergence first; then full-distribution real-outcome evaluation if simulation-derived forecasting is separately proposed.

Each failed family remains failed. Do not silently combine several failed ideas into a new unregistered candidate.

Display-tag analyses can validate whether a badge has honest descriptive meaning, but they cannot promote the tag into a predictive feature under this plan.

## 13. Promotion gates

A candidate is eligible for promotion consideration only if all applicable gates pass:

### Integrity

- point-in-time feature audit passes;
- dataset manifest and checksums reproduce;
- no target leakage or same-kickoff leakage;
- complete lineage and immutable artifacts;
- missingness and fallback behaviour match the frozen policy;
- derby and unpredictability tags are absent from feature manifests, calibrator inputs, parameter generation, simulator inputs, and probability post-processing;
- forecast-with-tags and forecast-without-tags probability artifacts are identical.

### Predictive performance

- no material regression on primary proper scores;
- improvement exceeds the pre-registered practical threshold or provides a separately approved operational benefit;
- confidence interval satisfies the frozen decision rule;
- gains are not concentrated in one competition or fold;
- calibration is maintained or improved.

### Segment safety

- derby and high-uncertainty segments are explicitly reviewed as evaluation slices only;
- incomplete-data fallbacks do not produce unjustified confidence;
- newly promoted and low-history teams remain calibrated enough for the approved use;
- non-H2H fixtures are not degraded by the H2H candidate.

### Operations

- latency and resource budgets pass;
- model, calibrator, and feature versions are deployable and reversible;
- contract compatibility and database migration dry runs pass;
- training-serving parity and deterministic replay pass;
- dashboards, actionable alerts, runbooks, and on-call ownership exist;
- backup restoration meets the approved RPO and RTO;
- build provenance, dependency policy, and security scans pass;
- cost per forecast, simulation, and scheduled rebuild remains within budget;
- shadow run and rollback evidence exists;
- Rust simulation reference-fixture parity, independent-batch convergence, tail checks, validation-artifact integrity, and cost gates pass for any simulation-capable candidate (once separately authorized);
- owner records a separate promotion decision.

Passing research, numerical simulation validation, or evaluation does not automatically promote a model. A real-outcome evaluation is still required before predictive promotion.

## 14. Implementation phases

### Engineering foundation across all phases

Engineering is not deferred to Phase 9. Before the first authoritative evaluation, deliver:

- architecture decision records for module boundaries, storage, job execution, and deployment shape;
- a reproducible local environment with seeded development data and one-command test execution;
- versioned database migrations and backward-compatible contract evolution rules;
- CI gates for formatting, linting, type checking, unit, integration, contract, leakage, and deterministic-replay tests;
- an artifact registry for datasets, features, models, calibrators, simulation builds, and API schemas;
- structured logs, metrics, traces, correlation IDs, dashboards, and initial SLOs;
- dependency locking, secret scanning, software-bill-of-materials generation, signed build provenance, and container scanning;
- infrastructure-as-code, staging parity, progressive deployment, rollback, backup, and restore exercises;
- cost budgets for ingestion, storage, training, replay, simulation, and forecast serving.

Every later phase adds its own tests, telemetry, runbook changes, migration impact, and rollback evidence to this foundation.

### Phase 0: reconcile status and authorize the new route

Deliverables:

- update tracked project status to reflect the closed shared-match-pace route;
- preserve the Sprint 2 failure and frozen 280-target firewall;
- reconcile, rather than recreate, the **existing** 20 September owner decision authorizing only bounded Phase 3A minimal xG research and Evaluation V2 policy/corpus design;
- propose a **new and separate** owner decision specifically for minimal Rust simulator implementation and its validation scope; do not infer authorization from this roadmap or from the previous research decision;
- define which phases are research-only and which can affect production;
- approve the initial architecture, ownership table, engineering SLO categories, and cost-accounting method.

Exit gate: status, evidence, and decision events agree.

### Phase 1: qualify the Evaluation V2 data foundation

Deliverables:

- competition-season coverage matrix;
- `TIER_A`/`TIER_A_PLUS`/`TIER_B`/`TIER_C`/`TIER_M` qualification reports;
- point-in-time dataset builder;
- same-kickoff batching;
- provider-semantic tests;
- rivalry registry schema and review workflow;
- immutable feature snapshot format;
- idempotent ingestion/backfill jobs, schema migration policy, and raw-to-snapshot lineage;
- training-serving feature-parity harness and fixed-model scoring test.

Exit gate: at least the minimum frozen corpus can be reproduced with no unresolved critical data issue.

### Phase 2: freeze Evaluation V2

Deliverables:

- versioned policy and corpus manifest;
- target firewall;
- reference implementations;
- metrics and bootstrap implementation;
- calibration and segment-report templates;
- dry run using non-authoritative targets.

Exit gate: explicit owner authorization for the authoritative run.

### Phase 3: xG/xGA expected-performance research

**Authorization boundary:** the 20 September decision permits only one minimal leakage-safe xG goal-model research hypothesis. The broader deliverables below are a proposed portfolio, **not** already authorized; each expanded family requires an explicit decision. Rust simulation is not a prerequisite for that existing minimal analytic research.

Deliverables:

- qualified shot-level xG model or approved provider xG adapter;
- `ExpectedPerformanceSnapshotV1`;
- opponent adjustment;
- multi-window and uncertainty features;
- ablations A-F;
- raw versus game-state-stratified and adjusted ablation;
- `PreShotThreatProfileV1` bounded shot-generation/suppression ablation after the core xG/xGA result;
- chronological evaluation report.

Exit gate: retain or reject the feature family based on frozen thresholds.

### Phase 4: H2H and rivalry research

Deliverables:

- `H2HContextV1`;
- `RivalryDefinitionV1` registry;
- residual replay from historical out-of-sample predictions;
- decay, shrinkage, and pair-random-effect candidates;
- entropy, goal covariance, continuity, and model-versus-H2H discrepancy features;
- `MatchupIntelligenceV1` wrapper with component coverage and uncertainty;
- counterfactual mean, dispersion, and correlation simulation design;
- matched-control derby analysis for display-tag validation only;
- placebo pair analysis;
- ablation report.

Exit gate: H2H candidates are accepted or rejected independently; derby status remains display-only regardless of the descriptive result.

### Phase 5: forecast diagnostics and frontend tags

Deliverables:

- `ForecastRiskAssessmentV1`;
- `FixtureDisplayTagsV1` generated after the immutable forecast;
- OOD, entropy, disagreement, data-risk, and drift components;
- `PostMatchShockLabelV1`;
- risk-band calibration analysis;
- API reason codes;
- frontend badge and warning policy that preserves the complete original forecast.

Exit gate: tags show stable, honest descriptive meaning or the aggregate unpredictability tag is removed in favour of component tags. Forecast parity with tags disabled must pass.

### Phase 6: dynamic team strength and match context

Deliverables:

- state-space or Bayesian dynamic challenger;
- competition and promoted-team priors;
- attack/defence change handling;
- manager/transfer-window change analysis where data supports it;
- comparison with time-decayed Dixon-Coles;
- `TravelAndFixtureLoadV1` with neutral-venue and timezone handling;
- separate rest, travel, congestion, and combined-load ablations;
- competition-strength, promoted-team, and objective priority-context candidates.

Exit gate: predictive and operational gates pass or the simpler reference remains champion.

### Phase 7: lineup and player context

Deliverables:

- availability and selection as separate probabilities;
- top-K lineup scenarios and residual mass;
- predicted versus confirmed forecast artifacts;
- `LineupImpactV1` attack, defence, goalkeeper, and set-piece deltas;
- XI, positional-unit, minutes-together, and formation-continuity features;
- `SquadTransitionV1` and team-plus-player rating ablations;
- `GoalkeeperShotStoppingV1` post-shot ablation where qualified;
- multidimensional player effects with uncertainty;
- strict fallback when lineup data is absent.

Exit gate: lineup-aware forecasts improve the relevant pre-lineup and confirmed-lineup contracts separately.

### Phase 8: mandatory Rust simulation validation and probability products

**Change in sequencing:** do not defer the *minimal Rust parity/validation engine* until after every advanced model family. Once separately authorized, implement its reference distribution contract and acceptance harness alongside foundational probability work, while leaving more complex scenario extensions in Phase 8. This is a new gate for future simulation-backed delivery, not a retroactive dependency of historical or the narrowly authorized Phase 3A research.

Deliverables:

- reconcile existing `rust/simulation-core` and Python/Go interfaces; preserve the repository's existing language ownership and avoid rebuilding working analytical components;
- approved parameter and coherent calibrated distribution contract;
- minimal deterministic Rust score sampler with independent seed schedule and bounded work;
- immutable `SimulationValidationArtifactV1` with input hash, engine version, run counts, convergence, parity, tail tests, and reason codes;
- reference-fixture analytic parity and multi-batch convergence suite;
- strict `PASS` / `FAIL` / `INCONCLUSIVE` gating plus explicit outage handling and idempotent publication;
- later, separately authorized score dependence, scenario uncertainty, and H2H same-seed counterfactual extensions;
- real-outcome chronological comparison only under the authorized evaluation policy; do not label numerical parity as calibration.

Exit gate: Rust engine and artifact validation pass; after separately authorized activation all new production fixture publication defaults to a required PASS, with only an explicitly approved labelled analytic-only fallback. Any predictive improvement claim additionally needs real-outcome evidence and separate promotion authorization.

### Phase 9: production API and monitoring

Deliverables:

- immutable prediction endpoints;
- `ForecastRevisionV1` and explicit supported forecast horizons;
- revision information-value reports and non-overwriting forecast history;
- model/feature/calibration/risk provenance;
- drift and calibration dashboards;
- shadow deployment;
- rollback and recovery proof;
- alerting by competition, model, target, and risk segment.

Exit gate: SLOs, security, monitoring, and rollback tests pass.

## 15. API contract additions

Illustrative **future** response fragment; fields below do not represent an implemented or already authorized public API, and optional/unpromoted capabilities must be omitted or explicitly marked unavailable:

```json
{
  "schema_version": "v1",
  "request_id": "...",
  "fixture_id": "...",
  "forecast_id": "...",
  "issued_at": "...",
  "knowledge_cutoff": "...",
  "forecast_horizon": "24h",
  "supersedes_forecast_id": null,
  "revision_reason_codes": [],
  "probabilities": {
    "home": 0.44,
    "draw": 0.29,
    "away": 0.27
  },
  "expected_goals": {
    "home": 1.42,
    "away": 1.12
  },
  "context": {
    "h2h_effect_used": false,
    "h2h_effective_sample_size": 2.1,
    "h2h_simulation_variant": null,
    "matchup_intelligence_mode": "DISPLAY_ONLY",
    "lineup_mode": "PREDICTED",
    "lineup_attack_delta": -0.04,
    "lineup_defence_delta": 0.01,
    "travel_load_band": "NORMAL",
    "fixture_congestion_band": "ELEVATED",
    "game_state_adjustment_used": false
  },
  "display_tags": {
    "items": [
      {
        "code": "DERBY",
        "reason_codes": ["SAME_CITY"]
      },
      {
        "code": "UNPREDICTABLE",
        "reason_codes": ["HIGH_MODEL_DISAGREEMENT", "HISTORICALLY_VOLATILE"]
      }
    ],
    "forecast_effect": false,
    "tag_policy_version": "..."
  },
  "forecast_diagnostics": {
    "band": "ELEVATED",
    "reason_codes": ["MODEL_DISAGREEMENT"],
    "predictive_entropy": 0.97,
    "data_quality": "PASS",
    "forecast_effect": false
  },
  "simulation": {
    "mode": "RUST_VALIDATED",
    "validation_artifact_id": "...",
    "validation_status": "PASS",
    "simulation_count": 10000,
    "simulation_engine_version": "..."
  },
  "provenance": {
    "model_id": "...",
    "dataset_snapshot_id": "...",
    "feature_set_id": "...",
    "calibration_id": "...",
    "code_revision": "...",
    "simulation_engine_version": "...",
    "rivalry_registry_version": "...",
    "matchup_intelligence_version": "...",
    "travel_load_version": "...",
    "lineup_impact_version": "...",
    "display_tag_policy_version": "...",
    "risk_model_id": "..."
  }
}
```

Rules:

- `schema_version` follows the published compatibility and deprecation policy;
- `request_id` correlates API logs, traces, worker activity, and support incidents;
- derby and unpredictability categories appear only under `display_tags`;
- every display-tag payload must include `forecast_effect: false`;
- `h2h_effect_used` must show whether the promoted model actually used the signal;
- insufficient H2H history must return low effective sample size, not a fabricated neutral history;
- diagnostic and tag reasons are additive and auditable;
- forecast horizon, issue time, and superseded forecast must be explicit;
- revisions create a new immutable response artifact and carry reason codes for the newly available information;
- no tag may be copied into forecast `context`, a feature snapshot, simulator parameters, calibration inputs, or probability post-processing;
- a simulation-backed response is available only after a linked Rust validation artifact passes; the shown simulation fields are an **illustrative future contract**, not current API capability or authorization;
- `simulation.mode = RUST_VALIDATED` requires `validation_status = PASS`, a valid artifact ID, engine build, and eligible sample count; never fabricate the block when simulation has not run;
- simulation failure/timeout returns an explicit unavailable result for required products. An approved analytic-only fallback uses `ANALYTIC_ONLY` and must not represent itself as validated simulation output;
- simulated frequencies cannot silently overwrite the sealed forecast distribution, and adding simulation evidence cannot alter its canonical probability hash;
- the same `forecast_id` must return identical probabilities whether tag enrichment succeeds, fails, or is disabled;
- no endpoint may present a point estimate without its surrounding distribution and provenance where the product contract requires them.

## 16. Model, data, and forecast monitoring

This section owns statistical and data-quality monitoring. Section 18.4 owns service-health telemetry and SLOs.

Monitor:

- input missingness and schema drift;
- feature distribution shift;
- score residuals and probability integral transform diagnostics;
- Brier, log loss, RPS, CRPS, calibration slope/intercept, and coverage;
- performance by competition and mandatory segments;
- display-tag prevalence, evidence sufficiency, and diagnostic monotonicity;
- rivalry and non-rivalry calibration as reporting segments only;
- tag-enrichment parity: probabilities and simulator inputs remain identical with enrichment enabled or disabled;
- H2H contribution and effective sample size;
- H2H counterfactual variant performance and distribution shift;
- forecast performance by horizon and revision stage;
- information value and calibration change from each revision reason;
- travel-load, rest, and congestion segments;
- lineup impact, uncertainty, and continuity segments;
- squad-transition, player-rating, and retained-minutes segments;
- goalkeeper post-shot residual coverage and shrinkage behaviour;
- pre-shot threat and territory feature coverage;
- raw versus game-state-adjusted feature behaviour;
- provider corrections and dependency impact;
- model disagreement;
- simulation validation PASS/FAIL/INCONCLUSIVE rates, seed reproducibility, reference parity errors, Monte Carlo intervals, tail stability, batch convergence, timeouts, and compute costs;
- independently, real-outcome calibration and proper scoring of simulation-derived forecasts only when such a variant has a distinct approved contract and evaluation policy.

Retraining policy:

```text
trusted completed-match publication
  -> dependency and correction checks
  -> eligible future training data
  -> scheduled candidate rebuild
  -> leakage-safe evaluation
  -> calibration review
  -> governed promotion decision
```

Drift detection opens a review or challenger route. It must not silently replace the champion, change feature weights, or recalibrate production forecasts.

## 17. Testing requirements

### Software structure and contracts

- architecture tests enforce module dependency direction;
- domain and probability types have deterministic unit and property tests;
- provider adapters pass fixture-based contract tests against versioned samples;
- database migrations are tested both forward and through the supported rollback or roll-forward recovery path;
- API schemas are checked for backward compatibility within the supported version;
- job handlers are idempotent under duplicate delivery and safe under partial retry;
- outbox or equivalent state-transition tests prevent committed data from losing required follow-up work;
- batch replay and production scoring return identical features and scores for the same cutoff, versions, and model.

### Delivery, performance, and resilience

- CI reproduces locked dependencies and verifies build provenance;
- integration tests use real supported database and queue versions rather than mocks alone;
- end-to-end tests cover ingest, correction, feature snapshot, forecast, tag enrichment, and API retrieval;
- load tests cover forecast latency, batch throughput, queue depth, and bounded simulation requests;
- staging tests prove required-product publication blocks on failed or inconclusive Rust validation; historic analytic-only artifacts remain readable;
- simulator outage, timeout, cancellation, duplicate delivery, seed repeatability, precision-budget exhaustion, and artifact/hash mismatch fail explicitly without probability mutation;
- provider timeouts, malformed payloads, rate limits, and partial outages exercise documented fallbacks;
- staging deployment, rollback, backup restore, and disaster-recovery exercises meet the approved SLO, RPO, and RTO;
- authorization, input-fuzzing, secret-scanning, dependency, container, and license-policy checks pass.

### Data and time

- property tests for cutoff eligibility;
- same-kickoff leakage tests;
- daylight-saving and timezone tests;
- provider correction replay;
- identity ambiguity and quarantine tests;
- feature missingness/fallback tests;
- travel distance, direction, and timezone calculations;
- neutral-venue and relocated-fixture handling;
- no future fixture, international-duty, or next-match information enters before publication;
- forecast revisions are immutable and have non-decreasing knowledge cutoffs.

### Derby, display tags, and H2H

- unordered pair identity tests;
- historical validity tests;
- neutral/shared venue tests;
- friendly/competition filtering;
- decay and effective-sample calculations;
- shrinkage tends to zero for sparse pairs;
- no current-match outcome enters its H2H snapshot;
- placebo-pair pipeline tests;
- entropy, covariance, and distribution-divergence calculations;
- same-seed counterfactual variants differ only through registered H2H parameter changes;
- current or future meetings cannot enter a pair's continuity or style-similarity features;
- derby registry fields cannot enter a model feature manifest;
- unpredictability tags cannot enter training, calibration, parameter, or simulator schemas;
- mutating or removing tags leaves forecast and simulation artifacts unchanged;
- tag enrichment failure returns the original forecast without probability changes;
- every tag carries `forecast_effect: false` and reproducible reason codes.

### xG/xGA

- shot coordinate and direction normalization;
- penalties and shootouts handled separately;
- own goals excluded from shot xG unless the contract says otherwise;
- provider semantic version tests;
- xG-for for one team equals xGA attributed to the opponent under the approved match contract;
- rolling windows contain only eligible prior matches;
- game-state slices reproduce from qualified event timelines;
- adjusted values retain raw counterparts and adjustment version;
- historical score state or dismissal data cannot enter its own pre-match snapshot.

### Travel, lineup, and revision context

- projected-core-XI minute totals use only lineup probabilities available at cutoff;
- lineup continuity and minutes-together exclude future appearances;
- predicted and confirmed lineup contracts cannot be mixed silently;
- lineup scenario probabilities plus residual mass are coherent;
- travel/load fallbacks are explicit when venue or player-minute data is missing;
- every revised forecast points to an existing predecessor and preserves the predecessor unchanged;
- forecast-horizon bucketing is deterministic and timezone-safe.

### Squad transition, goalkeeper, and pre-shot threat

- retained-minute and newcomer features use identities and appearances known at cutoff;
- transfer rumours, fees, and future registrations cannot enter snapshots;
- projected player and goalkeeper contributions are weighted by start probability;
- player and goalkeeper effects shrink toward their approved population priors when samples are sparse;
- pre-shot and post-shot xG semantics cannot be mixed;
- own goals, penalties, blocked shots, off-target shots, and shootouts follow explicit post-shot rules;
- box-entry, field-tilt, turnover, and possession-sequence calculations reproduce from versioned events;
- possession and territory windows contain only eligible previous matches.

### Probabilities and mandatory Rust simulation validation

- probabilities are finite, non-negative, and sum to one; score-matrix tail is explicit;
- final calibrated joint distribution is internally coherent before sampling; do not accept a 1X2-only adjustment that contradicts score-derived markets;
- deterministic Rust seed reproducibility, independent batch schedules, and analytic parity within pre-registered Monte Carlo confidence tolerances;
- convergence, uncertainty half-width, rare-event and tail checks have PASS, FAIL, and INCONCLUSIVE tests;
- validation-artifact hashes bind exactly to the sealed forecast candidate, Rust build, parameter/distribution version, and seed schedule;
- required-product publication rejects failed, missing, or inconclusive validation; existing published artifacts remain unchanged;
- monotonic market-line relationships where mathematically required;
- calibration artifact cannot train on its evaluation outcomes or Rust-generated synthetic outcomes;
- no Rust simulation runs on the frozen 280 Sprint 2 targets for the new route.

### Display-tag and diagnostic layer

- risk components are pre-match eligible;
- post-match shock labels cannot join the same match's pre-match snapshot;
- thresholds are frozen and versioned;
- reason codes reproduce;
- `INSUFFICIENT_DATA` is not converted to normal confidence;
- `FixtureDisplayTagsV1` is created only after the referenced forecast is immutable;
- no frontend tag can trigger forecast revision or recalibration.

## 18. Engineering and operational controls

Section 18 owns platform implementation requirements. Section 17 owns the tests that prove them, and Section 13 owns the gates that block promotion.

### 18.1 Persistence and data lifecycle

- keep provider payloads immutable in raw storage and operational state in a transactional database;
- make derived caches disposable and reproducible from authoritative artifacts;
- use versioned migrations with an expand-migrate-contract sequence for incompatible schema changes;
- checksum datasets, feature snapshots, models, calibrators, and simulation builds;
- define retention, archival, correction, deletion, and provider-license policies by data class;
- record lineage from API forecast back to source observations, transformations, code revision, and artifact versions.

### 18.2 Jobs, retries, and replay

- assume at-least-once job delivery and make handlers idempotent using stable operation keys;
- use durable queues, bounded retries, exponential backoff, dead-letter handling, and operator-visible replay;
- persist checkpoints so ingestion, backfills, evaluation, and simulation batches resume safely;
- separate transient provider failure from invalid or quarantined data;
- schedule in UTC and make same-kickoff batch boundaries explicit;
- prevent concurrent jobs from publishing conflicting current versions.

### 18.3 API and access boundaries

- publish a versioned machine-readable API schema and explicit compatibility policy;
- validate match, lineup, scenario, pagination, and bounded-simulation inputs;
- apply authentication, authorization, tenant or role boundaries where applicable, rate limits, request size limits, and timeouts;
- attach request and forecast correlation IDs to responses and telemetry;
- support idempotency keys for state-changing administrative operations;
- never expose raw or licensed provider data unless the provider contract permits it.

### 18.4 Observability and service levels

- correlate structured logs, metrics, and traces across API, workers, storage, model loading, and provider calls;
- define measurable SLOs for API availability and latency, forecast freshness, scheduled-job success, correction lag, feature coverage, and recovery;
- track saturation, queue age, error budgets, provider failures, cache effectiveness, and artifact-load failures;
- make alerts actionable with an owner, severity, runbook, and clear recovery condition;
- ensure display-tag enrichment failure cannot consume the forecast-availability error budget.

### 18.5 Security and software supply chain

- manage secrets outside source code and rotate provider and infrastructure credentials;
- enforce least privilege, encryption in transit and at rest, and immutable audit events for datasets, experiments, administrative changes, and promotion;
- lock dependencies and scan source, secrets, dependencies, licenses, containers, and infrastructure definitions;
- generate a software bill of materials and verifiable build provenance for release artifacts;
- verify artifact signatures or checksums before deployment and model loading;
- document vulnerability triage, patch timelines, and incident response ownership.

### 18.6 Delivery, recovery, and cost

- define infrastructure as code and keep development, staging, and production configuration differences explicit;
- use automated migrations, smoke tests, shadow or canary validation, and reversible deployment steps;
- prove rollback for application, schema, model, calibrator, and feature releases;
- define RPO and RTO, automate backups, and test restoration on a schedule;
- set budgets and alerts for provider calls, storage growth, training, replay, simulation, and per-forecast serving cost;
- scale workers independently before introducing additional network services.

## 19. Feasibility matrix

| Feature | Feasible now? | Data dependency | Promotion condition |
| --- | --- | --- | --- |
| Minimal Rust sampler / mandatory simulation validation | Proposed; implementation not yet authorized by 20 September decision | Qualified parameters, coherent calibrated distribution, existing Rust scaffold, explicit new owner authorization | Reference parity, convergence, numerical integrity, independent-seed reproducibility, failure handling, cost and published validation artifact PASS |
| New production fixture forecast (simulation default) | Blocked until simulator and independent product enablement are approved | Approved model plus accepted Rust engine and artifact contract | A linked PASS for each new forecast by default; exceptional analytic-only fallback must be explicitly approved and labelled; real-outcome model evidence and promotion/enablement decision; no retroactive requirement on prior artifacts |
| Analytic-only reference research | Existing authorized subset remains allowed | Existing qualified data/model contracts | No Rust dependency for historical work or bounded 20 September Phase 3A xG research |
| Curated derby registry | Yes | Team identity plus reviewed rivalry sources | Registry QA; display metadata only |
| Derby display flag | Yes | Registry | API and forecast-parity tests pass |
| Unpredictability display tags | Yes after diagnostic validation | Issued forecast, model disagreement, residual history, OOD and data-quality evidence | Honest reason codes, sufficient evidence and forecast-parity tests |
| Derby model coefficient | No under this plan | Not applicable | Requires an explicit future policy change; never inferred from the display tag |
| xG and xGA rolling form | Yes after Tier A qualification | Shot events or compatible provider xG | Beats goals-only/xG-only ablations |
| Opponent-adjusted xG/xGA | Yes | Multi-team historical coverage | Generalizes across folds |
| Game-state-adjusted xG/xGA | Research now after event qualification | Event timeline, score state, and dismissal semantics | Beats or complements raw values without leakage |
| Residualized H2H | Yes, research only | Historical out-of-sample predictions | Adds signal after shrinkage |
| H2H counterfactual simulation | After H2H and simulator foundations | Qualified pair context and parameter generator | Held-out mean/dispersion variant improves full-distribution scores |
| Raw H2H win rate | Technically possible, not recommended | Results | Do not promote as designed |
| Entropy and model disagreement | Yes | Approved predictive models | Risk bands validate out of sample |
| OOD detection | Yes | Frozen training feature distribution | Correlates with measurable forecast degradation |
| Post-match shock labels | Yes where events exist | Qualified event data | Explanation/research only initially |
| Manager-change context | Feasible after qualification | Accurate historical dates | Ablation passes |
| Rest/congestion | Yes | Reliable kickoff times | Ablation passes |
| Travel/load context | Feasible | Venue coordinates, neutral flags, player minutes, duty and fixture history | Component and combined ablations pass |
| Predicted lineups | Later | Deep historical lineup/availability coverage | Separate lineup forecast gates pass |
| Lineup strength impact and continuity | Later | Player effects, lineup scenarios, historical units/minutes together | Adds value beyond lineup names and preserves uncertainty |
| Squad-transition context | Feasible after lineup/identity qualification | Retained minutes, departures, arrivals, roles and availability | Adds value beyond team rating and lineup strength |
| Team plus player ratings | Research after lineup qualification | Historical player minutes and leakage-safe player ratings | Combined candidate beats team-only and player-only references |
| Goalkeeper post-shot residual | Later | Qualified post-shot xG/xGOT and goalkeeper identity | Adds value beyond xGA with stable shrinkage |
| Pre-shot threat and territory | Research after Tier A qualification | Versioned event sequences | Adds value beyond xG/xGA without unstable provider semantics |
| Forecast horizons and revisions | Yes once snapshots exist | Reconstructable point-in-time inputs | Horizon-specific calibration and revision value validate |
| Objective competition-priority proxies | Research only | Table/knockout state, future schedule as known at cutoff, rotation history | Adds value without subjective motivation labels |
| Kickoff/circadian effects | Deferred research | Local time, travel and timezone history | Stable effect after controlling for schedule and travel |
| Weather/referee features | Deferred | Point-in-time historical coverage | Only after qualification and ablation |
| xT/VAEP | Later | Normalized event actions | xG foundation stable and separately authorized |
| Tracking/GNN features | Not near-term | Licensed tracking data and large corpus | Independent future research route |
| Live automatic recalibration | No | Would require mature online-learning governance | Explicit future research only |

## 20. Immediate implementation backlog

This backlog references the phase and contract sections instead of restating their complete deliverables.

### 20.1 Engineering foundation

Execute before an authoritative evaluation run:

1. Reconcile current committed `docs/project-status.json` and the existing 20 September owner decision without overwriting either; preserve the Sprint 2 failure and frozen-target firewall. Draft a **distinct, not-yet-approved** minimal Rust simulation authorization proposal.
2. Write architecture decisions for the modular deployment, module dependencies, storage, durable jobs, artifact registry, API versioning, and deployment strategy.
3. Establish the reproducible local environment, locked dependencies, seeded fixtures, and one-command validation suite.
4. Implement the raw-data, identity, correction, quarantine, migration, and point-in-time snapshot foundations.
5. Add idempotent ingestion and backfill jobs with checkpoints, retry policy, dead-letter handling, and replay controls.
6. Add CI gates, artifact checksums, build provenance, security and license scans, migration dry runs, and deterministic fixed-model scoring.
7. Instrument logs, metrics, traces, dashboards, and initial SLOs; prove backup restoration and rollback in staging.
8. Establish cost attribution and budgets for provider calls, storage, training, evaluation, simulation, and forecast serving.

### 20.2 Research and product sequence

Proceed only as each preceding gate resolves:

1. Freeze Evaluation V2 policy, corpus rules, references, metrics, and target firewall.
2. Qualify competition-season coverage and implement `FeatureAvailabilityV1` plus same-kickoff tests.
3. Reproduce reference models on a non-frozen development corpus and prove training-serving parity.
4. Run only the existing authorized single minimal Phase 3A xG hypothesis; request new owner decisions for the broader xG/xGA, opponent-adjustment, or game-state experiments.
5. Run travel/load, H2H, lineup, squad-transition, goalkeeper, and pre-shot candidates one family at a time in the Section 12.6 order.
6. Build `FixtureDisplayTagsV1` as a non-blocking post-forecast sidecar and prove forecast parity under every tag state.
7. Implement `ForecastRevisionV1` and evaluate supported horizons without overwriting earlier forecasts.
8. Freeze and request authorization for the authoritative Evaluation V2 run; do not use Sprint 2's protected 280 targets.
9. Once separately authorized, build/qualify the minimal Rust parity and convergence harness before any new simulation-backed production enablement; advanced scenarios remain independently gated.
10. After separately approved activation, require `SimulationValidationArtifactV1` PASS for every new production fixture forecast by default (except an explicitly approved and labelled analytic-only fallback), and independent real-outcome evidence before any predictive promotion. Do not delay the already-authorized analytic Phase 3A research waiting for Rust.

## 21. Distinct definitions of done: forecast, simulation, enrichment, release

**Immutable analytic forecast candidate** is complete when fixture and team identities resolve; cutoff and pre-match feature eligibility pass; missingness and provenance are retained; approved model/calibrator and data tier are identified; coherent distributions, expected goals, intervals, and canonical hash reproduce; and the candidate is sealed. This internal or analytic-only artifact is not evidence that Rust validation ran.

**Simulation validation** is complete separately when an explicitly authorized Rust build reproduces approved inputs using recorded seeds; an immutable `SimulationValidationArtifactV1` links the exact forecast hash; analytic parity, convergence, tails, resource and numerical checks pass; and no forecast probability or calibrator was altered by simulation. Missing/failed/inconclusive validation cannot be represented as PASS.

**New production fixture forecast** is simulation-validated and releasable by default only after both preceding artifacts pass and an owner-approved capability is enabled; publication must be atomic/recoverable and must preserve unchanged forecast bytes. Failed validation prevents new simulation-backed publication, but does not erase the sealed candidate or invalidate any earlier published forecast. Analytic-only fallback requires its own approved, clearly labeled product policy.

**Enrichment** is separately complete when post-forecast tags and diagnostics reproduce with `forecast_effect=false` and preserve forecast and simulation hashes. Enrichment is never mandatory for forecast completion or simulator validation; failure must not block an otherwise valid forecast.

**Predictive calibration** is proven only by chronological comparisons with real held-out match outcomes under an authorized policy, not by the number of simulated games or simulation parity alone.

## 22. Definitions of done

### 22.1 Predictive feature

A proposed feature is complete only when:

- its semantics and source are documented;
- availability time is proved;
- missingness is explicit;
- implementation tests pass;
- the hypothesis and ablation are pre-registered;
- evaluation uses chronological unseen data;
- proper scores, calibration, and segments are reported;
- paired uncertainty is reported;
- complexity and latency are measured;
- the accept/reject decision is recorded;
- failure evidence is retained.

### 22.2 Engineering change

An engineering change is complete only when:

- its owning module, contract impact, and architecture decision are clear;
- database and artifact migrations are backward compatible or have a rehearsed recovery path;
- unit, integration, contract, end-to-end, and relevant property tests pass;
- idempotency, retry, concurrency, and failure behaviour are tested where applicable;
- logs, metrics, traces, dashboards, and alerts cover the new failure modes;
- security, privacy, provider-license, dependency, and cost impacts are reviewed;
- performance stays inside the approved latency, throughput, memory, and storage budgets;
- deployment, rollback, data recovery, and runbook steps are verified in staging;
- documentation and ownership are updated before release.

## 23. Research and engineering basis

These sources inform the roadmap but do not override repository governance or provider terms:

- Hudl/StatsBomb Open Data: <https://github.com/hudl/open-data>. The repository provides selected competitions, match events and lineups, with 360 data only for selected matches; rich coverage must therefore be measured, not assumed.
- Mead, O'Hare, and McMenemy (2023), “Expected goals in football: Improving model performance and demonstrating value”: <https://doi.org/10.1371/journal.pone.0282295>. Supports richer shot context, team-quality/context features, and direct validation of xG's predictive value.
- Ridall, Titman, and Pettitt, “Bayesian state-space models for the modelling and prediction of the results of English Premier League football”: <https://doi.org/10.1093/jrsssc/qlae075>. Supports dynamic attacking and defensive states rather than static team strength.
- Macrì-Demartino, Egidi, and Torelli (2026), “Bayesian weighted discrete-time dynamic models for association football prediction”: <https://doi.org/10.1093/jrsssc/qlag032>. Supports adaptive historical borrowing when team strength changes.
- Settembre et al. (2024), “Factors associated with match outcomes in elite European football — insights from machine learning models”: <https://doi.org/10.3233/JSA-240745>. In a large European-match analysis, travel distance, Elo difference, match location, and recent performance were prominent model contributors, while rest, rotation, and manager tenure also contributed. These are associations and feature-importance results, not causal proof; the paper's lineup-stability result was not a clear universal effect, so every context family still requires MatchForge-specific ablation.
- Arntzen and Hvattum (2021), “Predicting match outcomes in association football using team ratings and player ratings”: <https://doi.org/10.1177/1471082X20929881>. Their experiments found the combined team-rating and starting-lineup player-rating covariates outperformed using either rating family alone, supporting a bounded team-plus-player challenger rather than replacing team strength.
- Hudl StatsBomb, “A New Way to Measure Keepers' Shot Stopping: Post-Shot Expected Goals”: <https://www.hudl.com/blog/a-new-way-to-measure-keepers-shot-stopping-post-shot-expected-goals>. Provides the modelling rationale for separating pre-shot xG/xGA from post-shot goalkeeper evaluation. This is a provider methodology reference, so MatchForge still needs semantic qualification, shrinkage, and independent held-out evaluation.
- Pipping-Gamón, Feng, and Sabin (2025/2026), “Beyond Expected Goals: A Probabilistic Framework for Shot Occurrences in Soccer”: <https://arxiv.org/abs/2512.00203>. Motivates research into possession-level shot-generation information that ordinary shot-conditioned xG omits. It is a preprint, so this plan adds only simpler pre-shot threat ablations and does not treat its reported improvement as established production evidence.
- socceraction documentation: <https://socceraction.readthedocs.io/>. Demonstrates provider loaders, normalized action representations, xT, VAEP, and Atomic-VAEP as feasible later research paths.
- Gneiting and Raftery (2007), “Strictly Proper Scoring Rules, Prediction, and Estimation”: <https://doi.org/10.1198/016214506000001437>. Supports evaluating probabilistic forecasts with proper scoring rules.
- Scikit-learn probability calibration guidance: <https://scikit-learn.org/stable/modules/calibration.html>. Useful implementation reference for out-of-sample calibration and reliability analysis.
- Google, “Rules of Machine Learning”: <https://developers.google.com/machine-learning/guides/rules-of-ml>. Supports establishing a trustworthy end-to-end pipeline, testing infrastructure independently from the learner, monitoring silent failures and freshness, assigning feature ownership, and removing unused features before adding model complexity.
- NIST SP 800-218, Secure Software Development Framework: <https://csrc.nist.gov/pubs/sp/800/218/final>. Provides the secure-development basis for preparation, protected software, vulnerability response, and verifiable release practices.
- SLSA specification: <https://slsa.dev/spec/v1.2/>. Informs build provenance and software-supply-chain integrity requirements without requiring a particular CI vendor.
- OpenTelemetry documentation: <https://opentelemetry.io/docs/what-is-opentelemetry/>. Supports vendor-neutral correlation of logs, metrics, and traces across the forecast API and worker pipeline.
- The derby literature is limited and context-dependent. Use rivalry only for a reviewed frontend tag and evaluation slice; matched-control analysis must not feed a derby coefficient back into the forecast.
- Game-state-adjusted xG/xGA is retained as a research hypothesis rather than a claimed established improvement. MatchForge must compare raw, stratified, and adjusted variants under the same chronological contract.

## 24. Explicit exclusions

This plan does not authorize:

- changing the frozen Sprint 2 corpus, result, or thresholds;
- accessing the frozen 280 targets for a new route;
- automatic model promotion;
- automatic production recalibration after an upset;
- raw bookmaker odds as baseline model features;
- unreviewed web claims as derby truth;
- derby, rivalry, unpredictability, volatility, risk-band, or other frontend display tags as model features, calibrator inputs, simulator parameters, forecast-revision triggers, or probability adjustments;
- widening, flattening, suppressing, or recalibrating a forecast because a display tag is present;
- post-match information in a pre-match forecast;
- opaque “AI confidence” scores;
- LLM-written probability adjustments;
- microservices, Kubernetes, a streaming feature store, or service mesh as prerequisites for the first production release without measured need;
- reliance on exactly-once message delivery instead of idempotent processing and reconciliation;
- separate feature implementations for training, historical replay, and production serving;
- data resale or provider-term violations;
- simulator expansion as a substitute for failed forecasting evidence;
- interpreting this roadmap as authorization to implement Rust simulation, rerun frozen evaluation, or promote/deploy a model;
- presenting simulation frequencies as inherently more calibrated than the final model distribution;
- replacing calibrated analytic forecast probabilities with Monte Carlo frequencies by default;
- requiring retrospective Rust runs or changes to immutable existing Sprint 2 evidence. Foreign ownership of Python model mathematics and calibration by the Rust engine is prohibited.

## 25. Recommended repository document split

Keep this roadmap readable by moving detailed contracts into versioned documents:

```text
PLAN.md
docs/status/current-state.md
docs/governance/decision-events/
docs/architecture/module-boundaries.md
docs/architecture/decisions/
docs/engineering/local-development.md
docs/engineering/ci-cd-and-release.md
docs/engineering/schema-evolution.md
docs/engineering/jobs-and-replay.md
docs/engineering/artifact-registry.md
docs/api/openapi.yaml
docs/api/compatibility-policy.md
docs/operations/slos-and-alerts.md
docs/operations/runbooks/
docs/operations/disaster-recovery.md
docs/operations/cost-budgets.md
infra/
docs/evaluation/evaluation-v2-policy.md
docs/evaluation/promotion-gates.md
docs/contracts/rivalry-definition-v1.md
docs/contracts/h2h-context-v1.md
docs/contracts/expected-performance-snapshot-v1.md
docs/contracts/forecast-risk-assessment-v1.md
docs/contracts/fixture-display-tags-v1.md
docs/contracts/post-match-shock-label-v1.md
docs/contracts/matchup-intelligence-v1.md
docs/contracts/travel-and-fixture-load-v1.md
docs/contracts/lineup-impact-v1.md
docs/contracts/forecast-revision-v1.md
docs/contracts/squad-transition-v1.md
docs/contracts/goalkeeper-shot-stopping-v1.md
docs/contracts/pre-shot-threat-profile-v1.md
docs/data/coverage-matrix.md
docs/models/xg-xga-research.md
docs/models/game-state-adjustment-research.md
docs/models/h2h-and-rivalry-research.md
docs/models/context-and-load-research.md
docs/models/lineup-impact-research.md
docs/models/squad-transition-and-player-strength-research.md
docs/models/goalkeeper-shot-stopping-research.md
docs/models/pre-shot-threat-research.md
docs/models/calibration-policy.md
docs/simulation/validation.md                 # existing / future repository mapping, reconcile first
docs/simulation/mandatory-validation.md         # proposed mandatory Rust gate
docs/contracts/simulation-validation-v1.md    # immutable validation sidecar
docs/governance/simulation-authorization-proposal.md # proposed, not an owner decision
```

This `PLAN.md` defines sequence and boundaries. The versioned contracts define exact schemas and tests. Immutable evidence records what actually happened.
