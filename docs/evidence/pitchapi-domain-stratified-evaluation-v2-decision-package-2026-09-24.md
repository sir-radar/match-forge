# PitchAPI domain-stratified evaluation V2 decision package

Status: `READY FOR OWNER FREEZE DECISION — EXECUTION NOT AUTHORIZED`

Machine-readable proposal:
`docs/evaluation/pitchapi-domain-stratified-evaluation-v2-policy-proposal.json`

Proposal SHA-256:
`e4dfbf6a5133fba4806de80e6a79ccc878670531bb695e5509776dca082c1da1`

This package implements the design-only authorization recorded by
`ACCEPT_PITCHAPI_V1_FAIL_AND_DESIGN_DOMAIN_STRATIFIED_V2_V1`. It does not run
an evaluation, fit a final challenger, run Rust, call an API, contact a
provider, spend money or modify `PITCHAPI_SNAPSHOT_V1`.

## 1. Exact V2 specification

`PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2` asks whether one frozen MatchForge
challenger generalizes across three independent PitchAPI competition-season
domains while retaining acceptable forecasting performance and calibration.
It does not test whether PitchAPI used one hidden upstream xG model.

The roles remain:

| Role | Domain | Matches | Shots | Exact history-eligible targets |
| --- | --- | ---: | ---: | ---: |
| Development | Bundesliga 2021/22 | 306 | 7,961 | 216, excluded from evaluation |
| Evaluation | Bundesliga 2022/23 | 306 | 7,825 | 216 |
| Evaluation | Bundesliga 2023/24 | 306 | 8,523 | 216 |
| Evaluation | Ligue 1 2022/23 | 380 | 9,350 | 280 |

The target rule is `TEAM_PRIOR_APPEARANCES >= 10`. There is no competition-
history threshold. Evaluation capacity is exactly `216 + 216 + 280 = 712`
before any new fail-closed exclusion. Final admission must reproduce the exact
target manifests and retain at least 500 targets.

All forecasts use strict chronological walk-forward construction. Every
same-kickoff batch is forecast and sealed before any outcome in that batch is
revealed. Evaluation outcomes cannot influence fitting, tuning, transformations,
features, thresholds, calibration or retry decisions.

## 2. Exact differences from failed V1

V1 remains permanently `FAIL — OBSERVATIONAL_COMPATIBILITY_GATE`; V2 does not
amend or rescue it.

| V1 | Proposed V2 |
| --- | --- |
| Asked whether scopes were observationally compatible | Asks whether a frozen model generalizes across heterogeneous domains |
| Calibration intercept/slope and KS differences were admission gates | These are descriptive heterogeneity evidence |
| One failed compatibility gate prevented all targets from admission | Technical and semantic integrity govern source admission |
| Cross-domain source similarity was the primary decision | Domain-specific model performance is the primary evidence |
| No model evaluation could run after the gate failed | A separately authorized V2 could run only after this proposal is frozen |

V2 does not change the V1 threshold, configuration hash, report, snapshot or
failure. It is also separate from StatsBomb `EVALUATION_V2`.

## 3. Scientific rationale

xG distributions and observed goal calibration can legitimately change with
shot location, shot situation, tactics, finishing, penalties, competition and
season. A KS difference establishes distributional difference, not different
hidden upstream mathematics. Likewise, empirical goal-on-xG calibration mixes
the provider signal with realized finishing and sampling variation.

Those diagnostics remain valuable for robustness interpretation. They do not
establish hidden-model identity and therefore are not scientifically suitable
as cross-domain equality admission gates. Schema, semantics, ranges, identity,
lineage and chronology remain hard gates because failure there can make inputs
invalid or incomparable.

## 4. Technical and semantic source admission

Every scope must pass all of the following:

- PitchAPI source family and documented `expected_goals` shot-field semantics;
- valid schema, complete required match-shot resources and recognized shot
  event, situation and first/second-half period semantics;
- finite xG in `[0,1]` and consistent penalty representation;
- unique provider identities and explicit deterministic MatchForge mappings;
- immutable membership in snapshot
  `435bc3760cd3790e9f79cfc48801da0289fa73dbd30b02e63dc84468fd5a74ea`;
- verified raw, normalized, manifest, corpus and firewall hashes;
- zero development/evaluation and protected-data overlap;
- strict-prior history and same-kickoff firewall `PASS`.

Empirical distribution equality, equal calibration coefficients and pairwise KS
equivalence are explicitly not required.

## 5. Development-only xG treatment

Two alternatives were compared on Bundesliga 2021/22 non-penalty shots only:

1. raw xG;
2. `logit(xG') = a + b*logit(xG)`.

The comparison used four expanding chronological folds. Each fold trained on
all earlier blocks and validated on the next 20% of matches. The paired
uncertainty calculation resampled whole validation matches 2,000 times with
seed `20260924`. Recalibration could be selected only if transformed-minus-raw
log loss had point estimate and 95% upper bound below zero and Brier score had
point estimate and 95% upper bound at most zero. Requiring agreement from two
strictly proper scores avoids selecting a transform that improves one score by
degrading another.

| Development result | Delta | 95% interval |
| --- | ---: | ---: |
| Log loss | -0.006867 | [-0.013788, -0.000426] |
| Brier score | +0.001783 | [+0.000765, +0.002857] |

The Brier guardrail fails, so V2 freezes **raw PitchAPI xG with no transform or
normalization**. The full-development audit fit was `a=-0.6006589715`,
`b=0.6442830324`; it is not selected and must not be applied. Penalties remain
excluded from `MATCHFORGE_NPXG_FOR_LAST10_V1` under its existing feature rule.
No evaluation-domain outcome was used for this selection.

Reproduce the comparison with
`uv run python scripts/analyze_pitchapi_v2_development_xg.py`. The canonical
JSON output, including its trailing newline, has SHA-256
`dd19de6ae0a54a849d2dfb3c496b6c2934b63b27b2b57842674c6b749aa9e798`.

## 6. Domain-specific metrics

For each of the three evaluation domains, calculate on identical targets for
the challenger and compatible reference:

- joint score-matrix log loss, the confirmatory metric;
- 1X2 log loss, multiclass Brier and ordered RPS;
- total-goal CRPS;
- calibration intercept, calibration slope and reliability diagram;
- prediction-interval or prediction-set coverage and width;
- challenger-minus-reference deltas and paired 95% intervals.

Binary-market AUC, Brier and log loss, exact-score top-k accuracy, expected-
total-goal MAE and sharpness conditional on calibration are descriptive where
defined. AUC is not calculated for a constant outcome or single-class slice.
All markets must derive from the same coherent joint score distribution.

## 7. Aggregate methodology and thresholds

The primary aggregate is the arithmetic mean of the three domain-level paired
joint-score log-loss deltas. The secondary aggregate weights domains by fixed
target counts `216:216:280`. Calibration coefficients remain domain-specific
and are not averaged. Raw source distributions are never pooled.

Within each domain, use a paired moving-block bootstrap over chronological
kickoff batches: block length 10, 2,000 replicates, percentile 95% interval,
seed `20260924`. Domain resampling is independent. Aggregate replicate `i`
uses replicate `i` from each domain, equally for macro and with fixed target
weights for the weighted result.

All deltas are `challenger loss - reference loss`; lower is better.

| Gate | Proposed limit |
| --- | ---: |
| Macro joint-score log-loss point delta | `<= -0.010` nats/match |
| Macro joint-score log-loss 95% upper bound | `< 0` |
| Every domain joint-score log-loss 95% upper bound | `<= +0.050` |
| Macro 1X2 log-loss 95% upper bound | `<= +0.020` |
| Macro 1X2 Brier 95% upper bound | `<= +0.010` |
| Macro 1X2 RPS 95% upper bound | `<= +0.010` |
| Macro total-goal CRPS 95% upper bound | `<= +0.020` |
| Every domain intercept absolute-deviation worsening | `<= 0.050` |
| Every domain slope absolute-deviation worsening | `<= 0.100` |

These are not fitted to PitchAPI model results. They reuse the independently
approved, pre-outcome Phase 3A practical margins. The existing `n>=100`
competition-season `+0.050` joint-log-loss segment rule becomes V2's explicit
catastrophic-domain-degradation guardrail. All three domains exceed 100 targets.
There is one confirmatory primary and one candidate, so no success-claim
multiplicity adjustment is needed. Domain gates are conjunctive safety checks:
one failure rejects the candidate and cannot be averaged away.

## 8. Heterogeneity reporting

`DOMAIN_HETEROGENEITY_ANALYSIS` reports, by domain and pairwise where relevant:

- xG moments and quantiles;
- goal-on-logit-xG intercept and slope;
- shot-situation counts and rates;
- penalty count, rate and xG distribution;
- overall and situation-conditioned KS statistics;
- domain metric deltas, intervals and direction;
- macro versus target-weighted result and maximum-minus-minimum domain range.

These results are descriptive unless they expose an actual schema or semantic
incompatibility. They cannot alone admit or reject a domain.

## 9. Fail-closed conditions and result mapping

Stop with `DEFER_INSUFFICIENT_DATA` before outcomes are opened if fewer than
500 exact targets remain. Stop with `TERMINAL_ROUTE_FAIL` for leakage,
protected overlap, unauthorized access, snapshot/resource/policy hash mismatch,
chronological or same-kickoff failure, invalid probabilities, mutation,
post-outcome rule change or non-deterministic replay.

Use `REJECT` if any predictive or calibration guardrail fails, including a
domain joint-log-loss 95% upper bound above `+0.050`. Use `RETAIN_CHAMPION` when
integrity and guardrails pass but the macro primary improvement does not. Use
`PROMOTE_CANDIDATE` only when the macro primary and every guardrail pass.
Promotion remains a later owner decision; the disposition does not enable use.

A missing, failed or inconclusive mandatory Rust result prevents a complete
V2 disposition. Exact Rust parity, convergence, seed and resource thresholds
remain an execution prerequisite because the repository has no accepted engine
or frozen numerical policy. They must be approved before V2 execution; this
design authorization does not invent them or run the deferred scaffold.

## 10. Exact projected targets

The snapshot contains 712 history-eligible evaluation targets: Bundesliga
2022/23 `216`, Bundesliga 2023/24 `216`, and Ligue 1 2022/23 `280`. This exceeds
the minimum by 212. Admission must reproduce all IDs from the sealed manifests;
712 is not a promise that no later integrity exclusion will apply.

## 11. Cross-provider canonical-overlap review

Current-inventory status:
`PASS_BY_GOVERNED_SCOPE_WITH_FINAL_ALIAS_RECONCILIATION_REQUIRED`.

- PitchAPI development/evaluation exact-ID intersection is zero.
- Protected Sprint 2 is EPL 2015/16; PitchAPI scopes are Bundesliga/Ligue 1
  2021/22–2023/24, so protected overlap is zero by governed competition-season.
- Current qualified StatsBomb sources are also outside these PitchAPI scopes.
- A future licensed StatsBomb Bundesliga 2023/24 or Ligue 1 2022/23 snapshot
  would contain the same fixture population and must be declared overlapping.

The existing PitchAPI MatchForge UUIDs were initially allocated as UUIDv5 of
provider type and provider ID. UUID-set intersection therefore cannot prove
cross-provider equality. Final corpus admission must resolve every candidate
fixture using stable competition and team aliases plus kickoff, home and away
identity against every then-frozen protected/development/evaluation manifest.
No fuzzy-name-only merge is allowed. Missing or ambiguous aliases fail closed.
This design closes the method question; final reconciliation necessarily waits
for any future StatsBomb manifests that do not yet exist.

## 12. Disclosure classification

V2 is a
`POST_SOURCE_DIAGNOSTIC_PRE_MODEL_RESULT_PREREGISTRATION`, not a source-blind
preregistration. Its design follows inspection of V1 xG distributions,
calibration behaviour, shot situations, penalties and KS results. MatchForge
V2 evaluation was not executed; challenger performance and challenger-versus-
baseline results were not inspected or used. Every future report must carry
this disclosure.

## 13. Optional untouched confirmation plan

`PITCHAPI_CONFIRMATION_EVALUATION_V1` remains optional and unauthorized. The
preferred candidate is Ligue 1 2021/22 because retained catalog evidence names
it, it is not in `PITCHAPI_SNAPSHOT_V1`, and its outcomes were not used in this
design. Ligue 1 2023/24 and Bundesliga 2024/25 are secondary catalog leads.

Any confirmation requires a new immutable snapshot, exact qualification,
firewall and target manifests, budget and owner authorization. It cannot reuse
V2 fit/tuning decisions after confirmation outcomes are opened. It does not
block useful V2 work.

## 14. Exact next owner decisions

### Freeze/preregister V2

The next decision must state:

> Approve and freeze
> `PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2` exactly as specified in
> `docs/evaluation/pitchapi-domain-stratified-evaluation-v2-policy-proposal.json`
> at SHA-256
> `e4dfbf6a5133fba4806de80e6a79ccc878670531bb695e5509776dca082c1da1`.
> Freeze raw PitchAPI xG with no transformation,
> the exact development/evaluation roles, 10-team-appearance history rule,
> 500-target minimum, metrics, aggregation, bootstrap, thresholds,
> heterogeneity analysis, overlap rule, disclosure and fail-closed behavior.
> This decision authorizes preregistration only. It does not authorize final
> challenger fitting, evaluation outcomes access, Rust execution, API calls,
> provider contact, spend, promotion or production use.

### Execute V2 later

Execution requires a distinct later decision stating:

> Authorize one authoritative execution of the frozen
> `PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2` policy identified by exact policy,
> corpus, target-firewall, source snapshot, raw-xG treatment, reference model,
> challenger configuration, code commit, dependency lock and cross-provider
> overlap hashes. Confirm at least 500 exact targets, final alias-based overlap
> `PASS`, zero forbidden access, an accepted Rust engine and frozen numerical
> validation policy, exact compute/storage budget and accountable owner.
> Authorize final challenger fitting and evaluation/Rust execution only within
> those identities and budgets. Do not authorize API calls, provider contact,
> snapshot mutation, threshold changes, reruns after metric exposure,
> promotion or production use.

Until the first decision is recorded, V2 remains a proposal. Even after the
first decision, execution remains blocked pending the second decision and its
listed prerequisites.

## Immutable-boundary check

The proposal does not change StatsBomb `EVALUATION_V2`. At preparation start,
the protected file hashes were:

- `docs/evaluation/evaluation-v2-policy.md`:
  `90812c0119e84a5bef94e8726ba9f4a984c33f8a6bb655603c68738994a345b3`;
- StatsBomb corpus owner decision:
  `164b459089f54ba2023f92457579e400f78f183b88db50cc8620cf4a70a2e6b1`;
- Phase 3A xG freeze proposal:
  `4e7f880fa20b038e226473f860608e61180505f6c741660b6243d726cddb0b24`.

V1's policy configuration remains
`4b90fdccf678480ab53e0d5c637b76d8535ae114ad5c8b835c9675d4ae984318`.
