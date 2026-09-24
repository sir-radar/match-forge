# PitchAPI retrospective evaluation V1 — pre-acquisition owner review

Status: `FINAL PROPOSAL — ACQUISITION NOT AUTHORIZED`

This review finalizes the proposal for owner approval. It makes no API request,
does not consume the ten attempts left from earlier authority, and does not
authorize acquisition, spend, model fitting, Rust simulation, or evaluation.
StatsBomb `EVALUATION_V2` remains independent and unchanged.

## Decision summary

| Requirement | Status | Recommended decision | Approval consequence | Rejection consequence |
| --- | --- | --- | --- | --- |
| Team history `>= 10`; no competition-history target floor | `RESOLVED — APPROVED` | Retain | Complete last-10 features without importing a Sprint 2 training constraint | Requires a new owner amendment and new target projections |
| One development group; at least three evaluation groups, two competitions, two seasons, and 500 exact targets | `RESOLVED — APPROVED` | Retain | Preserves the frozen architecture | Stops or redesigns this protocol |
| Exact four-group assignment | `OPEN — READY` | Bundesliga 2021/22 development; Bundesliga 2022/23, Bundesliga 2023/24, Ligue 1 2022/23 evaluation | Freezes roles before new data are seen | Acquisition remains blocked |
| Observational xG compatibility policy | `OPEN — READY` | Approve the methods and thresholds below | Freezes admission rules before new data and performance are seen | Acquisition remains blocked |
| `PITCHAPI_SNAPSHOT_V1` and immutable retention | `OPEN — READY` | Approve | Allows reproducible retained acquisition | Acquisition remains blocked |
| Preferred acquisition budget | `OPEN — READY` | 1,302 base, 27 retries, 1,329 hard attempts | Authorizes only listed paths and attempts | No acquisition |
| Storage budget | `OPEN — READY` | 500 MiB expected; 6 GiB hard | Allows fail-closed storage planning | No acquisition |
| Controlled acquisition | `OPEN — READY` | Approve only after accepting every row above | Allows acquisition and verification only | Protocol remains offline |
| Evaluation execution | `NOT REQUESTED` | Keep separate | None | No current consequence; execution remains prohibited |

## Frozen architecture and exact proposed roles

The proposed roles satisfy one development group, three evaluation groups,
two evaluation competitions, three evaluation seasons, disjoint match IDs, and
PitchAPI-only source isolation.

| Role | Scope | Nominal | Warm-up excluded | Projected targets | Expected extra exclusions before acquisition | Expected final contribution |
| --- | --- | ---: | ---: | ---: | --- | --- |
| Development | Bundesliga 2021/22 | 306 | 90 | 216 | Unknown; all gates below apply | Development only; contributes zero to the 500-target gate |
| Evaluation | Bundesliga 2022/23 | 306 | 90 | 216 | Unknown; unaudited scope | Up to 216 if admitted |
| Evaluation | Bundesliga 2023/24 | 306 | 90 | 216 | Mapping and firewall remain unproved; earlier technical audit passed | Up to 216 if reacquired and admitted |
| Evaluation | Ligue 1 2022/23 | 380 | 100 | 280 | Mapping and firewall remain unproved; earlier technical audit passed | Up to 280 if reacquired and admitted |

The deterministic round-robin projection excludes the first ten appearances
for every team: ten 18-team Bundesliga rounds contain 90 matches, and ten
20-team Ligue 1 rounds contain 100. Evaluation capacity is therefore
`(306 - 90) + (306 - 90) + (380 - 100) = 712`. This is 212 above 500; up to
29.8% of projected targets can be lost before the global minimum fails.

Bundesliga 2021/22 is appropriate for development because it is a complete,
chronologically earlier, match-disjoint season where mappings, implementation,
and diagnostics can be fixed without using evaluation outcomes. It never
counts toward evaluation metrics. Bundesliga 2022/23 tests the next season;
Bundesliga 2023/24 tests a second later season and repeats previously observed
technical completeness under retained acquisition; Ligue 1 2022/23 supplies
competition independence. The shared Bundesliga competition is a limitation,
not leakage, provided the role firewall passes.

Targets may still be removed by same-kickoff batching, governed availability,
postponement or rescheduling, abandoned/cancelled or ambiguous lifecycle,
canonical mapping failure, malformed or incomplete resources, xG compatibility
failure, protected-scope intersection, or corpus/firewall failure. A protected
or firewall intersection is a protocol failure, not an ordinary exclusion. The
exact admitted evaluation count must remain at least 500.

No materially smaller plan is evidenced. The preferred route already uses
three 306-match Bundesliga scopes and the one 380-match Ligue 1 scope needed
for two-competition evaluation. Replacing any scope with a smaller unevidenced
season would require discovery, exact capacity proof, and a new review.

### Alternatives

| Route | Groups | Base + retry = ceiling | Projected evaluation targets | Scientific difference | Expected storage |
| --- | --- | ---: | ---: | --- | --- |
| Preferred/minimum evidenced | Bundesliga 2021/22 development; Bundesliga 2022/23, Bundesliga 2023/24, Ligue 1 2022/23 evaluation | `1,302 + 27 = 1,329` | 712 | Meets all frozen requirements at lowest evidenced scope count | <=500 MiB with verified backup |
| Stronger role separation | Ligue 1 2021/22 development; same three evaluation groups | `1,376 + 28 = 1,404` | 712 | Development overlaps only one evaluation competition; costs 74 more base calls | <=550 MiB with backup |
| Higher confidence | Preferred route plus Ligue 1 2021/22 backup/additional evaluation | `1,683 + 34 = 1,717` | 712 primary; up to 992 with backup | Adds replacement capacity and a second Ligue 1 season; no third competition | <=650 MiB with backup; 8 GiB hard stop |

The stronger-role-separation route is scientifically useful but not strong
enough to silently replace the owner's preferred layout. The broader route is
worth considering only if replacement resilience justifies 381 more base
requests; it is not required for the frozen architecture.

## Observational xG compatibility gate

The configuration and its hash must be frozen before acquisition. Every scope
must pass; `UNPROVED` is not admission. A warning requires a named finding and
sensitivity review. A failure excludes the scope and stops before evaluation.
The machine-readable proposal is
`docs/evaluation/pitchapi-retrospective-evaluation-v1-policy-proposal.json`
with SHA-256
`4b90fdccf678480ab53e0d5c637b76d8535ae114ad5c8b835c9675d4ae984318`.

| Test | Definition and sample | PASS | WARN | FAIL / action |
| --- | --- | --- | --- | --- |
| Schema and semantics | Ordered names, types, null rules, units, enum mappings, adapter version; every resource | Exact equality; zero unknown required period/situation values | None | Any mismatch; quarantine resource and stop protocol |
| Finite/range | Count of non-finite xG or xG outside `[0,1]`; every shot | Zero | None | Any value; exclude scope |
| Missingness | `missing_xG / shots`; every shot | `0` | None | `>0`; exclude scope |
| Penalty sample/range | Penalty count and min/max per scope | At least 20; all xG in `[0.65,0.90]` | None | Fewer than 20 is `UNPROVED`; outside range is `FAIL` |
| Penalty spread | `Q3(xG)-Q1(xG)` per scope; at least 20 | `<=0.04` | `(0.04,0.05]` | `>0.05`; exclude scope |
| Penalty cross-scope shift | Absolute difference in penalty medians per pair; at least 20 each | `<=0.04` | `(0.04,0.05]` | `>0.05`; exclude incompatible scope/pair |
| Calibration sample | Non-penalty shots with binary outcomes per scope | At least 1,000 | None | Fewer is `UNPROVED` |
| Calibration fit | `logit(P(goal)) = a + b*logit(xG)` with diagnostic-only clip `[1e-6,1-1e-6]` | Converged, finite | None | Non-converged/non-finite is `UNPROVED` |
| Calibration intercept | Absolute fitted `a`; sample above | `<=0.20` | `(0.20,0.25]` | `>0.25`; exclude scope |
| Calibration slope | Fitted `b`; sample above | `[0.85,1.15]` | `[0.80,0.85)` or `(1.15,1.20]` | Outside `[0.80,1.20]`; exclude scope |
| Overall distribution | Pairwise two-sample KS `D=sup_x|F_i(x)-F_j(x)|`; every scope pair | `D<=0.08` | `0.08<D<=0.10` | `D>0.10`; exclude incompatible scope/pair |
| Situation distribution | Same KS test within every shared normalized situation | At least 100 shots in each side and `D<=0.08` | `0.08<D<=0.10` | `D>0.10`; below 100 is `UNPROVED` |

The schema, period, situation, range, and missingness rules prevent silent
meaning changes. Penalty tests detect treatment changes. Calibration intercept
and slope detect level and scale changes. Overall and situation-conditioned KS
effect sizes detect season/competition shifts without confusing a changing
shot mix with a changed xG scale.

All overall pairs and eligible situation/pair comparisons use one
Holm-Bonferroni family at `alpha=0.05`. Adjusted significance is descriptive:
adjusted `p<0.05` with `D<=0.08` is a warning, not failure, because effect size
controls admission. Retain counts, moments, p10/p50/p90, goal rates, fitted
coefficients, KS values, raw and adjusted p-values, and exclusions.

Sensitivity reruns use calibration clips `1e-5` and `1e-4`, calibration with
and without penalties, overall KS without penalties, situation sample floors
75/100/150, each hard effect threshold at 80% and 120% where mathematically
valid, and leave-one-scope-out summaries. A primary pass that fails the 80%
threshold becomes `WARN_SENSITIVITY` and requires owner review. Primary failure
cannot be overridden by sensitivity analysis.

The maximum allowed conclusion is: “The admitted frozen PitchAPI scopes are
observationally compatible under the preregistered
PITCHAPI_RETROSPECTIVE_EVALUATION_V1 criteria.” This does not identify or prove
an identical hidden upstream model.

## Snapshot, identity, and reproducibility

`PITCHAPI_SNAPSHOT_V1` is one immutable acquisition cohort. It retains permitted
raw bytes, acquisition time, provider and endpoint identities, competition and
season, adapter/schema/configuration/normalization versions and hashes,
PitchAPI aliases, MatchForge fixture/team IDs, raw and normalized SHA-256,
per-match and per-season manifests, corpus and firewall manifests, source
series, dependency lock, processing Git commit, and final snapshot SHA-256.

PitchAPI IDs are aliases, never canonical MatchForge IDs. Existing offline
contracts and tests cover stable aliases, snapshot-specific mappings, changed
provider IDs with migration evidence, explicit remaps, duplicate aliases, and
collision rejection. Future observations create `PITCHAPI_SNAPSHOT_V2` or
later and reference the prior snapshot hash; they never mutate V1. Provider
revisions before MatchForge's first acquisition cannot be reconstructed.

Every result must bind protocol ID, source-series ID, snapshot ID/hash, corpus
hash, firewall hash, model build, Rust simulation build, exact target count,
and evaluation configuration identity. StatsBomb and PitchAPI datasets cannot
satisfy each other's requirements or be pooled. Side-by-side independently
computed metrics require the label `cross_evaluation_robustness`.

## Request and storage budget

The validated endpoint templates are:

```text
GET /v1/leagues/{league_id}/matches?season={YYYY%2FYYYY}
GET /v1/matches/{validated_match_id}/shots
```

| Scope | Season manifest | Match-shot resources | Base calls |
| --- | ---: | ---: | ---: |
| Bundesliga 2021/22 | 1 | 306 | 307 |
| Bundesliga 2022/23 | 1 | 306 | 307 |
| Bundesliga 2023/24 | 1 | 306 | 307 |
| Ligue 1 2022/23 | 1 | 380 | 381 |
| Total | **4** | **1,298** | **1,302** |

The 27-attempt reserve is `ceil(2% * 1,302)`. The hard ceiling is 1,329,
with at most two attempts per path. A manifest count change stops before shot
acquisition and requires a revised owner-approved budget.

Bundesliga 2023/24 and Ligue 1 2022/23 must be reacquired because the earlier
audit intentionally retained no raw response bytes. That audit proved observed
technical completeness, but cannot supply immutable raw hashes, acquisition
manifests, normalization hashes, backup verification, or the final snapshot
hash. The ten unused earlier attempts remain separate and unavailable.

The audit rate was about 26.05 shots/match, projecting about 33,818 shots. At a
planning allowance of 2 KiB/shot, shot content is about 66 MiB. Allowing for
JSON envelopes, four season manifests, request and mapping ledgers, canonical
manifests/hashes, normalized analytical data, filesystem overhead, and
transactional staging keeps the primary under 250 MiB; a separately verified
backup keeps expected storage at or below 500 MiB.

The hard bound is conservative: response caps allow at most 40 MiB for four
season resources and 2,596 MiB for 1,298 shot resources. Primary plus backup
raw worst-case is about 5.15 GiB, leaving about 0.85 GiB for normalized data,
manifests, hashes, and bounded temporary files. Before every response, publish,
normalization, or backup step, compute projected retained plus temporary use.
Reject by `Content-Length` where available; otherwise abort streaming at the
resource cap. Stop before projected total reaches 6 GiB. Quarantine the partial
run, publish no snapshot, and require owner review. Never increase the ceiling
automatically.

## Runtime and failure policy

Run at concurrency 1, no faster than one request/second, with a 30-second
request timeout, at most two attempts per path, one permitted 429 response in
the entire run, and a 45-minute wall-clock ceiling. Honor a valid `Retry-After`
only within the wall-clock limit; otherwise stop.

| Condition | Classification | Required action |
| --- | --- | --- |
| DNS/transport failure, timeout, 408, first 429, 5xx | Retryable | Deterministic bounded backoff; consume reserve; one retry for that path only |
| Second 429 or `Retry-After` beyond wall limit | Protocol stop + owner review | Stop all requests; retain ledger/quarantine |
| 401 or 403 | Protocol stop + owner review | Stop immediately; do not retry |
| 404 | Non-retryable protocol stop | Quarantine response; required complete resource is absent |
| Malformed JSON, wrong content type, schema/scope/count mismatch, incomplete shot resource | Quarantinable resource + protocol stop | Retain evidence; do not admit or continue to snapshot |
| Duplicate/conflicting provider IDs or unsupported mapping | Protocol stop + owner review | Preserve collision evidence; do not guess or overwrite |
| Raw/normalized write, fsync, atomic publish, disk, hash, manifest, or backup mismatch | Protocol stop + owner review | Publish no snapshot; preserve verified staging and ledger |
| Path attempts, retry reserve, 1,329 attempts, 45 minutes, response cap, or 6 GiB exhausted | Hard protocol stop | No extension; owner review required |

Partial acquisition is never a snapshot. Verified content-addressed objects may
remain in quarantined staging; do not delete evidence or overwrite them.
Resume requires owner review, the same pinned cohort/configuration, rehashing
all retained objects, and enough remaining attempts inside the original hard
ceiling. Every prior attempt still counts. Otherwise start a newly authorized
cohort and leave the abandoned cohort append-only.

## Chronological firewall and execution boundary

This protocol is `RETROSPECTIVE_FROZEN_SNAPSHOT_EVALUATION`. For a fixture `M`
at governed kickoff `T`, predictive inputs may use only eligible prior fixtures
with governed kickoff strictly before `T` and outcomes known before the
applicable knowledge cutoff. This covers results, shots, xG, team form,
competition history, lineups where used, and every derived feature.
Rescheduled fixtures use the governed actual kickoff and lifecycle record.
Equal-kickoff fixtures are forecast and sealed as one batch before any outcome
is revealed. Ambiguous availability or lifecycle fails closed.

Existing shared tests cover strict cutoffs, outcome-availability lag,
same-kickoff batching, target sealing, and future-outcome exclusion. PitchAPI
snapshot tests cover deterministic hashes, revision chains, aliases,
migrations, remaps, duplicates, and collisions. Historical corrections already
present in V1 may be treated as retrospective measurements, but reports must
state that the original match-date PitchAPI response is not reproduced.

Acquisition does not authorize evaluation. The lifecycle remains:

1. Policy freeze.
2. Controlled acquisition.
3. Snapshot verification.
4. Corpus construction.
5. Observational xG compatibility evaluation.
6. Exact target reconciliation.
7. Firewall verification.
8. Corpus/snapshot hash freeze.
9. Preregistration freeze.
10. Separate authorization to execute the protocol.
11. Mandatory Rust simulation.
12. Evaluation and reporting.

Any compatibility, corpus, exact-target, identity, or firewall failure stops
before execution.

## Reconciled owner decisions

| # | Question | Status and recommendation | Alternatives | Approval / rejection consequence | Scientific effect | Blocks acquisition | Blocks execution |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | Freeze the high-level architecture? | `RESOLVED — APPROVED`; retain | Amend with a new decision | Approval already controls; rejection redesigns protocol | Yes | No | Yes if reopened |
| 2 | Accept shared competition across disjoint development/evaluation seasons and the four exact roles? | `OPEN`; approve preferred layout | Stronger Ligue 1 development route; new third-competition discovery | Approval freezes roles; rejection blocks acquisition | Yes | **Yes** | **Yes** |
| 3 | Use team history 10 without competition history 100? | `RESOLVED — APPROVED`; retain | New explicit training/target rule | Approval already controls; rejection changes projections | Yes | No | Yes if reopened |
| 4 | Freeze compatibility methodology and thresholds? | `OPEN`; approve as written | Amend only before acquisition | Approval freezes admission; rejection blocks acquisition | **Yes** | **Yes** | **Yes** |
| 5 | Approve snapshot retention, preferred budgets, and controlled acquisition? | `OPEN`; approve 1,302/27/1,329 and 500 MiB/6 GiB | Stronger or broader routes above; reject | Approval permits acquisition only; rejection leaves corpus unavailable | Yes | **Yes** | **Yes** |

## Exact authorization text

The owner can approve the final policy and acquisition by recording exactly:

> I approve `PITCHAPI_RETROSPECTIVE_EVALUATION_V1` as a separate
> `RETROSPECTIVE_FROZEN_SNAPSHOT_EVALUATION` protocol. I reaffirm
> `TEAM_PRIOR_APPEARANCES >= 10`, with no
> `COMPETITION_PRIOR_MATCHES >= 100` target requirement. I approve Bundesliga
> 2021/22 as the sole development group and Bundesliga 2022/23, Bundesliga
> 2023/24, and Ligue 1 2022/23 as the three evaluation groups. I approve the
> preregistered observational xG compatibility methodology, numerical
> thresholds, warnings, multiplicity treatment, sensitivity analysis, and
> fail-closed actions recorded in
> `docs/evidence/pitchapi-pre-acquisition-owner-review-2026-09-24.md`. I approve
> creation and immutable permitted retention of `PITCHAPI_SNAPSHOT_V1`,
> including raw resources, normalized resources, manifests, hashes, canonical
> mappings, lineage, and one verified backup. I authorize the controlled
> acquisition of only those four competition-seasons through the two approved
> endpoint templates, with 1,302 base requests, a 27-attempt retry reserve, and
> a hard ceiling of 1,329 total attempts. The ten unused attempts from prior
> authority remain separate and may not supplement this budget. I approve 500
> MiB expected storage and a 6 GiB hard storage ceiling, with no automatic
> request, time, scope, or storage extension. I authorize acquisition and
> snapshot verification only under the runtime and stop rules in that review,
> at zero authorized monetary spend. This authorization does not approve model
> fitting, corpus admission, preregistration completion, Rust simulation,
> `PITCHAPI_RETROSPECTIVE_EVALUATION_V1` execution, reporting, promotion,
> production use, or any change to StatsBomb `EVALUATION_V2`; each applicable
> later action requires separate owner authorization.

Until that text or an equivalent explicit owner decision is recorded, exact
roles, compatibility thresholds, retention, request/storage budgets, and live
acquisition remain unapproved.
