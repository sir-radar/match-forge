# Phase 3A xG-for and Evaluation V2 freeze proposal

## Status

```text
Proposal ID:                 PHASE3A_XG_FOR_EVALUATION_V2_FREEZE_PROPOSAL_V1
Proposal status:             AWAITING_OWNER_DECISION
Decision 1:                 APPROVED WITHOUT AMENDMENTS
Decision 2:                 APPROVED WITHOUT AMENDMENTS
Decisions 3-5:              AWAITING_OWNER_DECISION
Phase 3A implementation:    NOT AUTHORIZED
Evaluation V2 execution:    NOT AUTHORIZED
Pre-registration frozen:    false
```

This document proposes exact values for the five Issue 6 freeze decisions. It
does not approve them. The repository owner must approve, reject, or amend each
decision. After approval, the approved values must be copied into the Phase 3A
pre-registration, assigned final IDs and hashes, reviewed, and frozen before
implementation tickets are released.

The proposal preserves the recorded 20 September 2026 authorization: one
minimal xG-for-only hypothesis and Evaluation V2 design. It does not authorize
xGA, opponent adjustment, shot-volume features, calibration changes, Rust
implementation, authoritative evaluation, promotion, or production use.

## Current evidence

The qualified StatsBomb La Liga 2015/16 source contains 380 matches, 9,168
shots, and complete finite `shot.statsbomb_xg` in `[0, 1]`. It is disjoint from
the protected Sprint 2 EPL admission and 280-target populations. Its point-in-
time prerequisites pass under the retained fixed-snapshot knowledge mode.

The source is suitable for feature-contract implementation after freeze. It is
not, by itself, an eligible Evaluation V2 corpus. Current repository evidence
contains only one qualified xG competition-season group.

External research supports using xG as a team-performance signal, a dynamic
goals-only reference, and proper scoring rules for probabilistic comparison.
Those sources support the direction, not the numeric freeze values. The values
below are conservative repository decisions chosen before evaluation outcomes:

- Dixon and Coles, *Modelling Association Football Scores and Inefficiencies
  in the Football Betting Market* (1997):
  https://doi.org/10.1111/1467-9876.00065
- Mead et al., *Expected goals in football: Improving model performance and
  demonstrating value* (2023):
  https://doi.org/10.1371/journal.pone.0282295
- Gneiting and Raftery, *Strictly Proper Scoring Rules, Prediction, and
  Estimation* (2007): https://doi.org/10.1198/016214506000001437
- StatsBomb Open Data competition catalog and event source:
  https://github.com/hudl/open-data

## Decision 1 — feature mathematics

```text
Decision status: APPROVED WITHOUT AMENDMENTS
Decision ID:     APPROVE_PHASE3A_MINIMAL_XG_FOR_V1_FEATURE_MATHEMATICS_V1
Recorded at:     2026-09-21T09:47:07Z
```

The repository owner approved this decision exactly as proposed. The approval
freezes the feature mathematics but does not release implementation. The full
pre-registration remains draft until Decisions 2–5 are resolved and the owner
separately approves and freezes the completed document.

### Proposed freeze

```text
Feature ID:                 MATCHFORGE_NPXG_FOR_LAST10_V1
Provider field:             shot.statsbomb_xg
Included shots:             periods 1 and 2; every non-penalty Shot
Excluded shots:             provider shot type Penalty; periods other than 1/2
Match aggregation:          sum retained xG by MatchForge team and match
Normalization:              none; one regulation-match total
History order:              kickoff batch, then MatchForge match ID
History window:             previous 10 eligible team matches
Cross-season behavior:      reset; no carryover
Minimum team history:       10 eligible matches
Missingness:                target ineligible; no zero, mean, or provider fallback
Same-kickoff handling:      all target features frozen before any batch outcome
Competition reference:      mean team-match non-penalty xG from prior eligible
                            matches in the same competition-season
Signal:                     s = log(team_last10_mean / competition_prior_mean)
Invalid signal behavior:    fail closed if either mean is non-finite or <= 0
```

Use one shared coefficient in the existing compatible goals-only reference:

```text
lambda_home_challenger = lambda_home_reference * exp(beta_xg_for * s_home)
lambda_away_challenger = lambda_away_reference * exp(beta_xg_for * s_away)

beta_xg_for domain:         [0, 1]
beta_xg_for initialization: 0.25
additional parameters:      exactly 1
```

Fit the reference parameters and `beta_xg_for` under the reference model's
existing likelihood, optimizer, iteration limit, tolerances, time weighting,
identifiability constraints, score-tail rule, and low-score correction. The
reference is the same model with `beta_xg_for = 0`. A boundary result at zero is
a valid no-effect result, not optimizer failure. Non-convergence, invalid
probabilities, or a failed reload-equivalence check fails closed.

No xGA, shot count, xG per shot, home/away split, opponent adjustment,
game-state adjustment, penalty signal, extra decay, alternative window,
regularization search, or calibrator change is permitted.

### Alternatives rejected

- Include penalties: mixes rare awarded-penalty opportunity with repeatable
  chance creation and gives 97 high-weight shots disproportionate influence.
- Multiple windows or learned decay: creates a tuning search not authorized by
  the one-hypothesis decision.
- Cross-season carryover: cannot be checked using the single currently
  qualified season and creates a separate prior-strength decision.
- Directly replace goal rates with xG averages: discards the approved
  goals-only reference rather than testing one incremental signal.
- Separate home and away coefficients: doubles the new parameter count without
  evidence that distinct effects are identifiable.

### Effects on existing work

Existing goals-only models remain unchanged and available as references. The
challenger creates a new artifact and new forecasts; it never mutates a fitted
baseline, raw probability, or published forecast. Python retains model and
feature ownership. Rust remains the required simulation route for any later
simulation-capable production candidate, under separate authorization.

### Approval required

Owner must approve the complete block above as one indivisible mathematical
and feature contract, or return exact amendments. Approval does not authorize
implementation until the approved pre-registration is frozen.

## Decision 2 — evaluation corpus

```text
Decision status: APPROVED WITHOUT AMENDMENTS
Decision ID:     APPROVE_PHASE3A_EVALUATION_V2_CORPUS_POLICY_V1
Recorded at:     2026-09-21T10:18:56Z
```

The repository owner approved this decision exactly as proposed. The approval
freezes the development source and independent-corpus eligibility policy and
authorizes bounded source qualification. It does not freeze authoritative
corpus membership, IDs, or hashes and does not authorize Evaluation V2.

### Proposed freeze

Development source:

```text
Role:                        DEVELOPMENT_ONLY
Provider scope:              StatsBomb La Liga 2015/16 (11/27)
Dataset version:             670662d6-6ed7-5fa1-ba3c-1cfd561e524f
Source snapshot:             01a08471-f763-7787-80ca-4293316b7e44
Source Git SHA:              4b73468fc5b0f1950f9f66fada70ad3a4f9327cb
Dataset manifest SHA-256:    cd32d1c44620116cedefc09860efeccb91da19db4e6006ace8b8b6df1dd8e4e0
Evaluation V2 membership:    EXCLUDED
```

Evaluation V2 corpus rule:

```text
Minimum groups:              3 competition-season groups
Minimum competitions:       2
Minimum seasons:            2
Group type:                  complete domestic league season
Minimum matches per group:  120
Minimum scored targets:     500 after all eligibility rules
Minimum team history:       10 prior eligible matches
Protected exclusions:       all Sprint 2 EPL 2015/16 source, admission, and
                            frozen 280-target identities
Development exclusion:      StatsBomb La Liga 2015/16 dataset above
Source requirement:         immutable exact snapshot and manifest per group
xG requirement:             100% finite provider xG on retained Shot rows
PIT requirement:            lifecycle, kickoff, source, and knowledge checks pass
Knowledge mode:             retrospective-fixed-snapshot-v1 only
Same-kickoff rule:           freeze whole batch before revealing outcomes
Target outcomes:            inaccessible until all model forecasts are sealed
```

Every group needs a qualification report, zero protected intersection, exact
source and dataset hashes, and a single frozen target manifest. A group with
quarantine findings, incomplete match coverage, ambiguous identity, or a
different knowledge mode is ineligible.

No exact authoritative corpus can be frozen now. Repository evidence contains
one qualified group, and that group is reserved for development. Catalog
presence is not qualification. The authoritative corpus decision must remain
blocked until the exact groups and hashes satisfy the rule above.

### Candidate acquisition scopes, not frozen members

The pinned StatsBomb catalog contains possible independent scopes, including
Liga F 2023/24 (`182/281`), Frauen Bundesliga 2023/24 (`135/281`), and NWSL
2023 (`49/107`). They are not proposed as frozen members. They require full
qualification, product-scope review, and enough combined eligible targets.
Prior Liga F evidence does not qualify that source for this route.

### Trade-offs

Requiring independent groups prevents reusing development evidence and tests
future-season/cross-competition stability. It delays Evaluation V2 because the
current inventory is insufficient. Reducing the requirement to the one La Liga
season would make execution possible sooner but would contradict the current
multi-season, multi-competition design and produce weak generalization evidence.

### Approval required

Owner must approve:

1. the exact development source and its permanent Evaluation V2 exclusion;
2. the corpus eligibility rule;
3. qualification of additional sources as the next authorized data task; and
4. that authoritative Evaluation V2 authorization cannot be requested until
   exact qualifying group IDs and hashes are available.

This decision alone cannot freeze the Evaluation V2 corpus.

## Decision 3 — acceptance thresholds

### Proposed freeze

All loss deltas use:

```text
delta = challenger loss - reference loss
```

Lower is better. Evaluation uses raw, unmodified distributions from one
candidate and one compatible reference on identical targets.

```text
Confirmatory primary:       joint score-matrix log loss
Required point delta:       <= -0.010 nats per match
Required 95% CI upper:      < 0

Guardrail, 1X2 log loss:    95% CI upper delta <= +0.020
Guardrail, 1X2 Brier:       95% CI upper delta <= +0.010
Guardrail, 1X2 RPS:         95% CI upper delta <= +0.010
Guardrail, total-goal CRPS: 95% CI upper delta <= +0.020

Calibration intercept:     absolute deviation from 0 may worsen by <= 0.050
Calibration slope:         absolute deviation from 1 may worsen by <= 0.100

Bootstrap:                  paired moving-block bootstrap
Unit:                       kickoff batch
Block length:               10 chronological kickoff batches
Replicates:                 2,000
Interval:                   percentile 95%
Seed:                       20260921
Multiplicity:               none; one candidate and one confirmatory primary
```

Blocking segments are competition-season, observed result, reference favorite
probability band, reference expected-total-goals band, history-depth band, and
data-coverage band. A segment is blocking only at `n >= 100`. For such a
segment, the joint score-matrix log-loss 95% CI upper delta must be `<= +0.050`.
Smaller segments and broader roadmap segments are descriptive only. Their
absence cannot be used to fail or pass this bounded Phase 3A experiment.

Decision rules:

```text
PROMOTE_CANDIDATE:
  primary point and CI requirements pass; all guardrails, calibration limits,
  blocking segments, integrity checks, and resource limits pass

RETAIN_CHAMPION:
  integrity passes, but primary improvement requirement is not met and no
  terminal failure occurs

REJECT:
  any predictive guardrail, calibration limit, or blocking segment fails

DEFER_INSUFFICIENT_DATA:
  corpus or reportable target count is below the frozen requirement before
  outcomes are inspected

TERMINAL_ROUTE_FAIL:
  leakage, protected-target access, artifact mutation, hash mismatch,
  non-deterministic replay, invalid probabilities, unauthorized input, or
  post-outcome policy change occurs
```

No result may change these thresholds. A favourable secondary metric or small
segment cannot override the primary rule.

### Trade-offs

One confirmatory metric avoids a hidden multiple-testing route. Score-matrix
log loss tests the coherent joint distribution the challenger changes. The
proper-score guardrails retain the existing product view. The practical
improvement is intentionally larger than zero; the interval requirement also
rejects an improvement that is not stable under paired resampling.

### Approval required

Owner must approve all metric directions, numeric margins, bootstrap settings,
segment rules, and result mapping before any authoritative target is opened.

## Decision 4 — experiment budget

### Proposed freeze

```text
Candidate families:         1 (xG-for only)
Reference models:           1 compatible goals-only reference
Feature variants:           1
Window/decay variants:      1 fixed last-10 window; no decay
Hyperparameter search:      prohibited
Optimizer starts:           1 fixed start
Optimizer maximum:          existing reference limit, at most 1,000 iterations

Development full replays:   at most 2
Development CPU budget:     16 CPU-hours total
Development wall time:      8 hours total
Development memory:         16 GiB peak
Development storage:        20 GiB temporary

Authoritative logical runs: 1
Evaluation CPU budget:      64 CPU-hours total
Evaluation wall time:       24 hours total
Evaluation memory:          16 GiB peak
Evaluation storage:         40 GiB temporary
Bootstrap replicates:       2,000, included in evaluation budget
```

An exact technical retry is allowed only when no evaluation outcome or metric
was exposed, inputs and hashes are unchanged, and the accountable owner records
the retry reason. It consumes the same one logical run. Any retry after metrics
are exposed requires a new owner decision and a new experiment ID.

Budget exhaustion returns `INCONCLUSIVE` or `DEFER_INSUFFICIENT_DATA`; it does
not authorize fewer checks, extra compute, another model, or relaxed thresholds.

### Trade-offs

This budget supports deterministic fits and established 2,000-replicate paired
uncertainty while preventing window, coefficient, or candidate search. It may
be conservative until exact corpus size and benchmark timing are known. If a
non-outcome dry benchmark shows it cannot complete, amend the budget by owner
decision before the authoritative run, never after inspecting results.

### Approval required

Owner must approve each search and resource limit, retry rule, and fail-closed
budget behavior.

## Decision 5 — accountable owner

### Proposed freeze

```text
Accountable research owner: repository owner, GitHub identity sir-radar
Execution operator:         may be delegated and must be recorded per run
Freeze approval:            accountable owner only
Evaluation run approval:    separate accountable-owner event after all hashes
Result disposition:         accountable owner after evidence review
Production authorization:   separate owner event; never implied
```

The accountable owner must confirm the identity above or provide the exact
human name and stable repository identity to record. An agent, model, CI job,
or execution operator cannot fill this role or approve its own work.

Required owner duties:

- approve or amend all five freeze decisions;
- verify final pre-registration IDs and hashes;
- authorize the authoritative run separately;
- decide result disposition without threshold changes;
- record any conflict, retry, exception, or stop decision.

### Approval required

Owner must explicitly accept accountability and the recorded identity. Silence,
merge, implementation activity, or prior research authorization is not approval.

## Phase 1C `PASS_WITH_WARNINGS` disposition

| Finding | Implementation | Evaluation V2 | Required control |
| --- | --- | --- | --- |
| `PHASE3A_FEATURE_CONTRACT_UNSET` | **BLOCKS** | **BLOCKS** | Approve Decision 1 and freeze pre-registration. |
| `RETAINED_VALIDATOR_WARNINGS_NOT_CLEARED` | Does not block this xG-only feature | Does not block if frozen exclusions hold | Do not use affected spatial, event-time, position-stint, or unknown-type fields. |
| `RETROSPECTIVE_SNAPSHOT_NO_PUBLICATION_TIMESTAMPS` | Does not block deterministic implementation | **BLOCKS** any historical-publication claim; conditionally allowed only under the fixed-snapshot mode | Freeze `retrospective-fixed-snapshot-v1`; do not claim live historical availability. |
| `SINGLE_COMPETITION_SEASON_INSUFFICIENT_FOR_EVALUATION_V2` | Does not block implementation against the development contract | **BLOCKS** corpus freeze and run | Qualify independent groups and meet Decision 2. |

The 648 retained validator findings are also classified:

- 9 out-of-bounds locations: nonblocking because the feature never reads
  location; affected rows remain excluded from any spatial feature.
- 126 impossible event timestamps: nonblocking because aggregation is at match
  level and uses kickoff order; event-time features remain forbidden.
- 66 nonmonotonic position stints: nonblocking because the feature does not use
  lineups or positions.
- 447 unknown event types: nonblocking because retained Shot rows have complete
  canonical event type, team, player, and xG; unknown types stay unmapped.

Any later feature that consumes an affected field must reopen the relevant
qualification. These findings do not grant a blanket warning waiver.

## Preserved invariants

- Existing completed evidence and terminal results remain unchanged.
- Protected EPL identities remain excluded; no protected files or outcomes may
  be opened by development, qualification, implementation, or evaluation work.
- Inputs are prior-only; target and same-kickoff outcomes stay sealed until all
  forecasts in the batch are immutable.
- Every challenger forecast is a new immutable artifact. It cannot overwrite a
  reference or published forecast, raw probability, or prior revision.
- Python owns feature and model work. The mandatory Rust simulation requirement
  for any later simulation-capable production route remains unchanged and needs
  separate authorization.
- Goals-only baselines remain available and are the mandatory comparison.
- This proposal changes no production forecasting behavior.

## Required approval sequence

1. Owner approves, rejects, or amends Decisions 1–5 individually.
2. If approved, create final policy, feature, corpus-rule, budget, and owner IDs.
3. Update the Phase 3A pre-registration with approved values; review and hash it.
4. Freeze the pre-registration by explicit owner event.
5. Release implementation and non-authoritative verification tickets.
6. Qualify the independent Evaluation V2 corpus and freeze exact IDs/hashes.
7. Request a separate owner decision to execute Evaluation V2.

Current stop point is step 1. No later step is authorized.
