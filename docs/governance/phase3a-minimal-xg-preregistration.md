# Phase 3A minimal xG hypothesis — draft pre-registration

```text
Experiment ID:       PHASE3A_MINIMAL_XG_FOR_V1_DRAFT
Lifecycle status:    DRAFT
Run status:          BLOCKED
Frozen:              false
Authorized to score: false
```

This draft is bounded by owner decision
`RETAIN_SPRINT2_FAIL_CLOSE_SHARED_PACE_AND_AUTHORIZE_PHASE3_RESEARCH_V1`.
That decision permits one minimal, leakage-safe xG goal-model research
hypothesis. It does not supply the complete mathematical, data, evaluation, or
resource specification required to freeze or run the experiment.

## Draft hypothesis

Against a compatible reproduced goals-only reference, adding one prior-only
xG-for signal per team from qualified Tier-A shot data may improve
chronological held-out goal-distribution and 1X2 proper scores without a
blocking calibration, segment, reproducibility, or operational regression.

The challenger may differ from the reference only through that xG-for signal
and the minimum parameters required to integrate it. This statement does not
authorize a search across multiple transformations or model formulations.

## Fixed scope

| Item | Draft restriction |
| --- | --- |
| Family | xG-for only |
| Reference | compatible goals-only reference on the same governed targets |
| Source | qualified Tier-A provider shot data with exact dataset and source lineage |
| Historical eligibility | prior football time and approved knowledge time only |
| Same-kickoff handling | freeze every forecast in the batch before revealing outcomes |
| Missingness | explicit; no silent zero, mean, or cross-provider substitution |
| Output | one coherent joint goal distribution and derived products |
| Calibration | separate; no use of target or future outcomes |
| Forbidden additions | xGA, shot volume, chance-quality splits, opponent/game-state adjustment, xT, VAEP, player/lineup inputs, ensembles, simulation, bookmaker inputs |
| Protected data | no access to the frozen Sprint 2 280 targets or admission population |

## Qualified source available for design

The exact StatsBomb La Liga 2015/16 dataset recorded in
[Phase 1C qualification](../evidence/phase1c-statsbomb-laliga-tier-a-xg-qualification-2026-09-21.md)
passes xG semantic coverage with warnings. It provides 9,168 shot rows with
complete, finite provider xG. This qualifies a source for feature-contract
design; it does not by itself define the experiment corpus or authorize a run.

## Unset — blocking freeze and implementation

The following values require an explicit owner or research-owner decision.
They must not be selected after observing evaluation outcomes.

| Field | State |
| --- | --- |
| Accountable research owner | `UNSET — BLOCKING` |
| Exact provider/source scope beyond the qualified La Liga source | `UNSET — BLOCKING` |
| Penalty inclusion/exclusion | `UNSET — BLOCKING` |
| Match-level xG aggregation and normalization | `UNSET — BLOCKING` |
| Rolling window, cross-season behavior, and decay | `UNSET — BLOCKING` |
| Minimum eligible history and missingness fallback | `UNSET — BLOCKING` |
| Exact mathematical integration into the goals-only reference | `UNSET — BLOCKING` |
| Additional parameter count, bounds, regularization, and initialization | `UNSET — BLOCKING` |
| Fit objective, optimizer, convergence, and numerical tolerances | `UNSET — BLOCKING` |
| Development corpus and target-plan IDs/hashes | `UNSET — BLOCKING` |
| Evaluation V2 policy/corpus/firewall IDs and hashes | `UNSET — BLOCKING` |
| Primary metrics, practical margins, and regression limits | `UNSET — BLOCKING` |
| Paired uncertainty, multiplicity, stopping, and failure rules | `UNSET — BLOCKING` |
| Compute/time budget | `UNSET — BLOCKING` |

## Stop rules

- Do not implement or fit the challenger while any mathematical, feature, or
  development-corpus field above remains unset.
- Do not access or score an authoritative Evaluation V2 target without the
  separate owner decision required after policy and corpus freeze.
- Do not broaden a failed or inconclusive xG-for result into xGA or another
  feature family.
- Do not change this draft to `FROZEN` merely because code or data becomes
  available.
