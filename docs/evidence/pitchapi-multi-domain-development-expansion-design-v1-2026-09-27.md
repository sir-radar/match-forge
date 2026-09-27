# PitchAPI multi-domain development expansion design

## Decision and boundary

`PITCHAPI_V5_CALIBRATION_SUCCESSOR_RESEARCH_V1` remains
`DEVELOPMENT_REJECTED`. Its artifact
`cd88bed5e1231dc740886573d7195cc32228b99b9135d2d6f2edab9408768452`
is immutable negative research evidence. No alternate calibrator was tried.

This record completes
`PITCHAPI_MULTI_DOMAIN_DEVELOPMENT_EXPANSION_DESIGN_V1` as design-only work.
No provider call, provider contact, payment, acquisition, snapshot, model fit,
evaluation, confirmation run, or V6 design occurred. The 712 V5 targets remain
`SPENT_FOR_MODEL_SELECTION`; none was reused.

## Existing data inventory

There are **zero** retained targets that are both unused and admissible for this
development route.

| Provider and competition-season | Retained state | Classification | Reason |
| --- | --- | --- | --- |
| PitchAPI Bundesliga 2021/22 | 306 matches; 216 targets; full shot snapshot | Already spent | V3/V5 development and calibration-successor development. Outcomes influenced model decisions. |
| PitchAPI Bundesliga 2022/23 | 306; 216; full shot snapshot | Spent | V5 target population. |
| PitchAPI Bundesliga 2023/24 | 306; 216; full shot snapshot | Spent | V5 target population. |
| PitchAPI Ligue 1 2022/23 | 380; 280; full shot snapshot | Spent | V5 target population. |
| StatsBomb Premier League 2015/16 | 380; 280 protected targets; full events | Protected | Sprint 2 admission and frozen evaluation populations. |
| StatsBomb La Liga 2015/16 | 380; 280 targets; full events | Already spent | Earlier development, diagnostics, and model selection. |
| StatsBomb Serie A 2015/16 | 380; 280 targets; 20 teams; full events and npxG | Protected, confirmation-only | Qualified candidate for independent StatsBomb `EVALUATION_V2`; it cannot be moved into PitchAPI development. |
| StatsBomb Ligue 1 2015/16 | 377 of 380 match-list rows; projected 276 targets | Insufficient coverage | Three matches are missing, event resources are not retained, the scope is undeclared, and kickoff/PIT qualification is absent. |
| StatsBomb Liga F 2023/24 | 240; about 140 structural targets; full events retained | Unsuitable | Women's competition conflicts with the current men's product decision; the group also informed an earlier failed corpus-selection route. |
| StatsBomb WSL 2020/21 | 131; 31 structural targets; metadata only | Unsuitable | Women's scope and too few targets. |
| StatsBomb WSL 2023/24 | 132; 32 structural targets; metadata only | Unsuitable | Women's scope and too few targets. |
| StatsBomb Frauen Bundesliga 2023/24 | 132; 32 structural targets; metadata only | Unsuitable | Women's scope and too few targets. |
| StatsBomb NWSL 2023 | 137; 37 structural targets; metadata only | Unsuitable | Women's scope, playoff/coverage mismatch, and too few targets. |
| StatsBomb Serie A Women 2023/24 | 130; 30 structural targets; metadata only | Unsuitable | Women's scope, incomplete coverage, and too few targets. |
| Football-Data.co.uk Premier League 2025/26 | 380 aggregate rows | Incompatible semantics | Tier B results/aggregate data; no event shots or npxG and no strict historical provider knowledge time. |
| Football-Data.co.uk Premier League 2015/16 | 380 aggregate rows | Protected and incompatible | Overlaps protected StatsBomb EPL and has no event/npxG semantics. |

The remaining StatsBomb catalog entries are match-list metadata, not qualified
event datasets. All are insufficient: Premier League 2003/04 (38); Ligue 1
2021/22 (26) and 2022/23 (32); Bundesliga 2015/16 and 2023/24 (34 each); La
Liga 2004/05–2014/15 and 2017/18–2020/21 (7–38 each); La Liga 1973/74 (1);
Serie A 1986/87 (1); WSL 2018/19 (107) and 2019/20 (87); MLS 2023 (6); NWSL
2018 (36); Argentina 1981 and 1997/98 (1 each); and Indian Super League
2021/22 (115). They have no admissible post-warm-up target population. La Liga
2016/17 is separately retained as a 34-match failed-replication fragment and
is also insufficient.

This inventory uses only retained manifests, prior qualification reports, and
catalog aggregates. It did not open protected target outcomes.

## Minimum useful development evidence

The numerical floor is **1,200 exact eligible targets**, with all of these
additional conditions:

- at least five competition-season groups, four competitions, and two seasons;
- at least 250 home wins, 250 draws, and 250 away wins in the complete
  development population;
- at least 200 eligible targets per group and at least 40 outcomes of each
  class per group, or the group cannot support a domain calibration estimate;
- one qualified Tier A provider and one frozen xG model/version across every
  group;
- full npxG, penalty/own-goal rules, shot situations, kickoff, identity,
  correction, rights, and retention qualification;
- chronological, same-kickoff-safe out-of-sample predictions for every row
  used to estimate or judge calibration;
- promoted or otherwise unseen teams in at least two groups.

The 1,200-target number is a **necessary screening floor, not automatic proof
of enough precision**. Binary calibration-planning research recommends
planning from outcome prevalence, the distribution of forecast logits, and a
target confidence-interval width rather than a fixed rule of thumb. It also
finds that roughly 200 events is a better minimum than 100 for precise external
validation. MatchForge applies that conservatively to each one-versus-rest 1X2
class, adds margin for same-kickoff clustering, and requires multiple domains.
See [Pavlou et al. (2021)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8529102/),
[Riley et al. (2021)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8352630/), and
[Collins et al. (2016)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4738418/).

The current 108-row held-out experiment demonstrates why count alone is not
enough. Raw classwise standard errors were:

| Outcome | Intercept SE | Slope SE | Approximate 95% full width |
| --- | ---: | ---: | ---: |
| Home | 0.2250 | 0.4654 | 0.88 / 1.82 |
| Draw | 2.1092 | 1.7741 | 8.27 / 6.96 |
| Away | 0.3781 | 0.4515 | 1.48 / 1.77 |

Naively scaling those standard errors by `1/sqrt(n)` while holding the forecast
distribution fixed would require about 2,250 targets for the home-slope width,
2,640 for the away-intercept width, and more than 80,000 for the draw-intercept
width. The draw figure is not an acquisition recommendation: it shows that the
current compressed draw predictor is an identification problem that more rows
alone should not be expected to cure. A calibration-only minimum cannot be
defended from target count alone.

The draw failure is driven by both limited draw outcomes and weak spread in
predicted draw probabilities. Increasing rows while keeping nearly constant
draw logits would still leave the slope poorly identified. Before any
calibration fit, the development design therefore needs a preregistered
precision calculation. After the underlying candidate produces chronological
out-of-sample probabilities, but before any calibration fit or outcome-based
model selection, run an
outcome-blind probability-dispersion screen and the frozen simulation. The
package may support later calibration only if its predictions are projected to
give, for home/draw/away separately, 95% full widths no greater than `0.30` for
the intercept and `0.40` for the slope. If 1,200 targets miss that standard,
the corpus grows; the precision rule does not change.

## Smallest proposed development package

The smallest reasonable package is five complete groups from **one** qualified
Tier A event provider. PitchAPI is the continuity preference, but current
catalog, rights, retention, and semantic coverage for these scopes are
unknown. The same package may be sourced from another single qualified Tier A
provider only through a new owner decision.

| Competition | Season | Planned provider | Matches | Projected targets | Teams | Unseen/promoted relevance |
| --- | --- | --- | ---: | ---: | ---: | --- |
| Bundesliga | 2024/25 | PitchAPI, subject to qualification | 306 | 216 | 18 | Includes promoted-team histories after the ten-match warm-up. |
| Bundesliga | 2025/26 | Same provider/version | 306 | 216 | 18 | Second season tests time transfer and newly promoted teams. |
| Premier League | 2024/25 | Same provider/version | 380 | 280 | 20 | New competition and promoted teams. |
| La Liga | 2024/25 | Same provider/version | 380 | 280 | 20 | New competition and promoted teams. |
| Serie A | 2024/25 | Same provider/version | 380 | 280 | 20 | New competition and promoted teams. |
| **Total** |  |  | **1,752** | **1,272** |  |  |

Target projections apply the existing ten-prior-team-match rule: the first 90
matches of an 18-team league and first 100 of a 20-team league are warm-up.
They are not provider coverage claims.

| Group | npxG and shot situations | Outcome distribution | Rights and snapshot | Previous use / decision influence |
| --- | --- | --- | --- | --- |
| Bundesliga 2024/25 | Unknown; require every retained regulation shot, mapped situation, and one frozen xG version | Unknown; require at least 40 home, 40 draw, 40 away eligible targets | Unknown; not acquired | None known; require identity overlap check |
| Bundesliga 2025/26 | Same requirement | Same requirement | Unknown; not acquired | None known; require identity overlap check |
| Premier League 2024/25 | Same requirement | Same requirement | Unknown; not acquired | None known; require identity overlap check |
| La Liga 2024/25 | Same requirement | Same requirement | Unknown; not acquired | None known; require identity overlap check |
| Serie A 2024/25 | Same requirement | Same requirement | Unknown; not acquired | None known; require identity overlap check |

Provider model version, license/retention rights, and exact snapshot coverage
are also `UNKNOWN / NOT ACQUIRED` for every group. Those unknowns are admission
gates, not assumed passes.

Contamination risks are: overlap with V5 or protected StatsBomb match IDs;
choosing scopes after viewing their model performance; mixing xG model
versions; using corrected present-day data without a fixed knowledge-mode
contract; selecting groups after inspecting class balance; and treating league
format counts as actual provider coverage. Freeze the five-group membership
from source metadata, then qualify it before any outcome-based modelling.

## Untouched confirmation role

Confirmation must be acquired and frozen only after a successor hypothesis is
admitted in development. It must contain at least three complete
competition-season groups, two competitions, and 600 exact eligible targets,
with zero match overlap and the same qualified provider/xG semantics as
development. At least one competition and one season must be absent from
development, and at least one group must contain promoted/unseen teams. Its
outcomes, forecasts, and aggregate performance remain sealed until model,
features, hyperparameters, admission criteria, and evaluation code are frozen.

The protected StatsBomb `EVALUATION_V2` groups are not this confirmation set.
Their policy and provider state remain unchanged.

## Research options A–E

| Option | Rationale and data | Main risks and complexity | Calibration and architecture |
| --- | --- | --- | --- |
| A. Retain raw npxG challenger | Required benchmark because V5 improved proper scores. Needs the same prior-only rolling inputs. | Low complexity; known calibration weakness. | Transparent Python fit and coherent score distribution; no correction layer. |
| B. Global calibration | A simple correction may become estimable from multi-domain OOS predictions. | Moderate leakage risk if predictions are not genuinely OOS; compressed draw logits may remain unidentified. | Interpretable, but only reconsider after the precision screen passes. |
| C. Hierarchical calibration | Partial pooling could represent stable competition differences. Requires at least five groups and repeated domains. | Higher parameter and prior sensitivity; serious sequential-shopping risk. | Compatible with Python artifacts, but unjustified until a simple global correction shows stable cross-domain need. |
| D. Improve forecast mathematics | V5's better proper scores plus weak calibration can arise from misspecified goal-rate or low-score mapping. Needs npxG for **and against**, multiple domains, and coherent scores. | Moderate complexity; leakage remains manageable with central PIT inputs. | Directly improves the source of 1X2 probabilities and preserves one joint distribution. Preferred next step. |
| E. Richer event features | Shot situations, shot creation, territory, and possession can explain information omitted by shot-conditioned npxG. Requires stable event semantics and much broader coverage. | Higher missingness, provider drift, feature multiplicity, and overfit risk. xT/VAEP are least interpretable here. | Fits Python ownership, but should follow a bounded pre-shot-threat ablation, not precede the xG foundation. |

The recommended order is `A` as the fixed benchmark, then `D`. Option `B` is
only a later diagnostic if multi-domain OOS precision passes. `C` is deferred.
For `E`, richer npxG splits and the existing bounded pre-shot threat family are
scientifically preferable to endless calibration, but full xT/VAEP is not yet
justified. Those methods require action-sequence semantics that PitchAPI's
retained shot-only snapshot does not provide.

## Exact next hypothesis

Recommend
`TRANSFERABLE_ROLLING_NPXG_FOR_AGAINST_DIXON_COLES_V2`:

> Strictly prior rolling non-penalty xG for and against, combined with
> competition-centered partially pooled scoring baselines and home advantage,
> plus one globally shrunk low-score dependence parameter, will improve joint
> score and 1X2 proper scores and reduce home/draw/away calibration error versus
> both the goals-only reference and the unchanged raw V5 npxG challenger on
> chronological leave-domain-out development predictions.

The first comparison has no post-hoc calibrator. It tests whether draw and 1X2
calibration improve when the goal-rate and low-score mathematics are corrected
at their source. It keeps one coherent joint score distribution and stays in
Python modelling ownership.

## Exact data gaps and required owner authorization

Existing data are insufficient. The gaps are 1,272 new admissible development
targets; four competitions and two seasons; npxG-for and npxG-against; stable
penalty, own-goal, and shot-situation semantics; full fixtures and outcomes;
kickoff/PIT metadata; promoted-team coverage; provider model-version identity;
retention and research-use rights; and an immutable snapshot with backup and
checksums.

A separate owner decision would need to authorize **only**:

1. a metadata-only PitchAPI catalog and rights/retention qualification for the
   five named groups;
2. if that passes, bounded acquisition of complete fixture and shot resources
   for exactly those groups under one frozen provider/xG model version;
3. immutable primary and backup snapshots plus source, schema, coverage,
   situation, identity, correction, kickoff, PIT, overlap, and rights reports;
4. no model fit, outcome-based group substitution, confirmation acquisition,
   StatsBomb protected-scope access, evaluation, V6, promotion, or production
   use.

If PitchAPI cannot supply all five groups under compatible semantics, stop and
return the exact gap. Do not silently mix providers or substitute seasons.

## Owner boundary

The design is complete. Acquisition is required but not authorized. No future
V6 is justified yet. The next decision is whether to authorize the bounded
five-group PitchAPI metadata/rights qualification above.
