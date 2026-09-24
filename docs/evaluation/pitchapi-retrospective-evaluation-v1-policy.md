# PitchAPI retrospective evaluation V1 policy

Status: `FROZEN — CONTROLLED ACQUISITION AUTHORIZED; EVALUATION NOT AUTHORIZED`

This policy is separate from StatsBomb `EVALUATION_V2`. Approved rules are
marked `FROZEN`. Owner decision
`AUTHORIZE_PITCHAPI_SNAPSHOT_V1_CONTROLLED_ACQUISITION_V1` freezes the exact
group roles, compatibility thresholds, immutable retention, and controlled
acquisition limits. Corpus admission, preregistration, model work, Rust
simulation, and evaluation execution remain separately unauthorized.

## Frozen protocol rules

```text
Evaluation protocol:        PITCHAPI_RETROSPECTIVE_EVALUATION_V1
Snapshot series:            PITCHAPI_SNAPSHOT_V1
Historical-time mode:       RETROSPECTIVE_FROZEN_SNAPSHOT_EVALUATION
Development groups:         exactly 1
Evaluation groups:          at least 3
Evaluation competitions:    at least 2
Evaluation seasons:         at least 2
Evaluation targets:         at least 500 exact eligible targets
Target team history:        at least 10 prior eligible appearances per team
Competition history:        no target threshold
Nominal group screen:       at least 120 matches; screening only
Provider mixing:            prohibited
Protected-data reuse:       prohibited
Immutable snapshot:         required
Rust simulation:            required
```

Ten prior team appearances supplies the complete last-10 feature window. The
legacy 100-prior-competition-match rule is a historical training implementation
constraint, not PitchAPI target eligibility. Any future model training floor
must be specified separately and may not silently remove targets.

Each result binds protocol ID, source-series ID, snapshot UUID and hash, corpus
hash, firewall hash, preregistration ID, model build, Rust simulation build,
evaluation/metric/simulation configuration hashes, evaluation date, and exact
target count. Default reports cannot pool PitchAPI and Evaluation V2 metrics.
Cross-protocol reporting must use `cross_evaluation_robustness`.

## Frozen group assignment

This is the owner's preferred layout for final approval. It is the smallest
layout supported by current evidence that meets the frozen group architecture,
but request count is not its scientific justification. It provides a full
chronologically earlier Bundesliga development season, two later Bundesliga
evaluation seasons for temporal transfer, and an independent Ligue 1
evaluation group for competition transfer.

| Role | Scope | Nominal matches | Warm-up exclusions | Projected targets | Other expected exclusions | Minimum pre-acquisition contribution | Why |
| --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| Development | Bundesliga 2021/22 | 306 | 90 | 216 | Unknown until full audit and exact firewall | 0 until qualified | Chronologically precedes both Bundesliga evaluation seasons and cannot count toward the 500-target gate |
| Evaluation 1 | Bundesliga 2022/23 | 306 | 90 | 216 | Unknown until full audit and exact firewall | 0 until qualified | Adds an unaudited future-season test before the audited Bundesliga season |
| Evaluation 2 | Bundesliga 2023/24 | 306 | 90 | 216 | Prior audit saw zero technical shot defects; exact mapping/firewall exclusions remain unknown | 0 until reacquired and qualified | Retains current audited Bundesliga evidence |
| Evaluation 3 | Ligue 1 2022/23 | 380 | 100 | 280 | Prior audit saw zero technical shot defects; exact mapping/firewall exclusions remain unknown | 0 until reacquired and qualified | Supplies the second evaluation competition |
| Backup | Ligue 1 2021/22 | 380 | 100 | 280 | Unknown until full audit and exact firewall | 0 until qualified | Replaces a failed scope or adds a second Ligue 1 season |

Evaluation projection is `216 + 216 + 280 = 712`, giving 212 targets of
headroom over 500. Up to 29.8% of projected targets could be excluded before
the global minimum fails. These are deterministic balanced-schedule
projections under the frozen team-history rule, not admission counts. A
fail-closed minimum before acquisition is zero for every unaquired scope;
catalog and prior non-retaining audits cannot guarantee exact contribution.

Development and evaluation match IDs, target IDs, manifests, fit/tune choices,
and outcomes remain isolated. Evaluation outcomes cannot influence mappings,
compatibility limits, implementation, hyperparameters, or calibration choices.
Bundesliga 2021/22 is suitable for development because it is earlier and
disjoint, supplies a complete last-10 feature warm-up, and is excluded from all
evaluation metrics. Sharing a competition does not make it independent, so all
Bundesliga-only conclusions must be checked against Ligue 1 2022/23.

## Frozen observational xG compatibility gate

Freeze the complete policy hash before acquiring candidate groups. Compute
diagnostics from the frozen snapshot before inspecting MatchForge forecasting
performance. A scope with any `FAIL` or `UNPROVED` result is excluded. `WARN`
does not change the hard result, but requires a named finding and sensitivity
result in the owner review.

### Exact methods and thresholds

| Check | Definition | Sample | PASS | WARN | FAIL | Rationale |
| --- | --- | --- | --- | --- | --- | --- |
| Schema | SHA-256 of ordered field names, types, null rules, enum mappings, units, and adapter version | Every resource | Exact equality; zero unknown required enum values | None | Any mismatch or unknown | Prevents comparing different normalized meanings |
| Finite/range | Count `x` where `not finite(x)` or `x < 0` or `x > 1` | Every shot | Zero | None | Any invalid value | xG is a probability |
| Missingness | `missing_xG / shot_count` | Every shot | `0.000` | None | `> 0` | Feature aggregation cannot silently impute missing shots |
| Period semantics | Exact normalized period mapping; regulation feature admits periods 1 and 2 only | Every shot | Zero unknown/misclassified periods | None | Any unknown or inconsistent mapping | Keeps regulation feature meaning fixed |
| Situation semantics | Exact normalized situation mapping | Every shot | Zero unknown/misclassified situations | None | Any unknown or inconsistent mapping | Required for conditioned comparisons |
| Penalty sample | Count of normalized penalty shots | Each scope | `>= 20` | None | `< 20` is `UNPROVED` | Avoids interpreting unstable penalty summaries |
| Penalty range | Minimum and maximum penalty xG | Each scope | All in `[0.65,0.90]` | None | Any outside | Detects changed penalty treatment without requiring one fixed value |
| Penalty spread | `Q3 - Q1` | Each scope | `<= 0.04` | `(0.04,0.05]` | `> 0.05` | Penalty values should be tightly grouped |
| Penalty cross-scope shift | Absolute difference between scope medians | Every scope pair | `<= 0.04` | `(0.04,0.05]` | `> 0.05` | Detects material penalty-policy changes |
| Calibration sample | Non-penalty shots with binary goal outcome | Each scope | `>= 1,000` | None | `< 1,000` is `UNPROVED` | Supports stable two-parameter calibration diagnostics |
| Calibration model | `logit(P(goal)) = a + b*logit(xG)`; diagnostic clipping only at `[1e-6,1-1e-6]` | Each scope | Fit converges; finite `a,b` | None | Non-convergence/non-finite is `UNPROVED` | Measures level and scaling consistency |
| Calibration intercept | Absolute fitted `a` | Each scope | `<= 0.20` | `(0.20,0.25]` | `> 0.25` | Larger level error is materially inconsistent |
| Calibration slope | Fitted `b` | Each scope | `[0.85,1.15]` | `[0.80,0.85)` or `(1.15,1.20]` | Outside `[0.80,1.20]` | Detects compressed or exaggerated xG scale |
| Overall distribution | Two-sample KS `D = sup_x |F_i(x)-F_j(x)|` | Every scope pair | `D <= 0.08` | `0.08 < D <= 0.10` | `D > 0.10` | Effect-size guard against material scale shifts |
| Situation distribution | Same KS statistic within each shared situation | At least 100 shots in each scope/situation | `D <= 0.08` | `0.08 < D <= 0.10` | `D > 0.10`; below sample floor is `UNPROVED` | Separates provider shifts from situation-mix shifts |

Run all overall scope pairs and every shared situation meeting the sample floor.
Compute exact/asymptotic KS p-values consistently, then Holm-Bonferroni adjust
the complete family at `alpha=0.05`. Effect sizes determine hard admission.
Adjusted `p < 0.05` with `D <= 0.08` is `WARN`, not `FAIL`, because large samples
can make negligible shifts significant. Record counts, means, standard
deviations, p10/p50/p90, goal rates, fitted estimates, KS values, raw p-values,
adjusted p-values, and all exclusions.

### Sensitivity analysis

Before admission, rerun and retain:

1. calibration clipping at `1e-5` and `1e-4`;
2. calibration with and without penalties;
3. overall KS with penalties removed;
4. situation KS at sample floors 75, 100, and 150;
5. every hard effect threshold at 80% and 120% of its proposed value, bounded
   to valid probability ranges;
6. leave-one-scope-out summaries.

A hard PASS that becomes FAIL under the stricter 80% threshold is reported as
`WARN_SENSITIVITY`; it remains eligible only after owner review. Failure under
the preregistered primary threshold is always `FAIL`. Thresholds cannot be
changed after acquisition based on observed candidate results.

Passing supports only: “The frozen PitchAPI scopes are observationally
compatible under the preregistered PitchAPI evaluation protocol.” It does not
prove one hidden upstream mathematical model.

## Snapshot and reproducibility policy

One controlled cohort creates immutable `PITCHAPI_SNAPSHOT_V1`. It contains
exact raw body hashes, normalized logical and physical hashes, per-match and
per-season manifests, MatchForge team/match IDs, snapshot-specific PitchAPI
aliases, mapping decisions, acquisition timestamps, endpoint identities,
adapter/schema/configuration versions, dependency lock, code Git commit,
corpus manifest, firewall manifest, and final snapshot SHA-256.

Raw bytes are streamed to temporary files, hashed, length-checked, fsynced, and
atomically published to content-addressed paths. Normalization reads only
verified raw objects. Backup restore and every manifest edge are rehashed before
freeze. Existing paths are never overwritten with different bytes.

A later observation is `PITCHAPI_SNAPSHOT_V2` or another new version linked to
V1 by prior snapshot hash, detected provider-ID changes, normalized difference
hash, and correction classification. MatchForge revisions are append-only.
Provider revisions before first MatchForge acquisition remain unknown and
cannot be reconstructed.

## Acquisition authorization and alternatives

All options reacquire the currently audited groups because the prior audit
retained no raw responses. The existing ten-attempt remainder is excluded.

### Option A — preferred and minimum evidenced route

Groups: Bundesliga 2021/22 development; Bundesliga 2022/23, Bundesliga
2023/24, and Ligue 1 2022/23 evaluation. This is the smallest evidenced plan,
but development shares Bundesliga with two evaluation seasons.

| Item | Value |
| --- | ---: |
| Season manifests | 4 |
| Match-shot resources | 1,298 |
| Base requests | **1,302** |
| Retry reserve | **27** |
| Hard attempt ceiling | **1,329** |
| Projected evaluation targets | **712** |
| Projected shots | about **33,818** |
| Expected primary raw + normalized storage | under **250 MiB** |
| Expected primary + verified backup | under **500 MiB** |
| Hard storage ceiling | **6 GiB** |

Qualification value: meets frozen architecture with 212 projected target
headroom. No materially smaller plan is evidenced: three 306-match Bundesliga
scopes and one 380-match Ligue 1 scope are the least costly evidenced complete
seasons that still provide one development group, three evaluation groups, two
evaluation competitions, two seasons, and 712 projected targets. A smaller
route would require a newly evidenced complete scope and a new owner review.
Weakness: development choices may be more specific to two Bundesliga
evaluation seasons.

### Option B — stronger role separation alternative

Groups: Ligue 1 2021/22 development; Bundesliga 2022/23, Bundesliga 2023/24,
and Ligue 1 2022/23 evaluation.

| Item | Value |
| --- | ---: |
| Season manifests | 4 |
| Match-shot resources | 1,372 |
| Base requests | **1,376** |
| Retry reserve | **28** |
| Hard attempt ceiling | **1,404** |
| Projected evaluation targets | **712** |
| Projected shots | about **35,746** |
| Expected primary raw + normalized storage | under **275 MiB** |
| Expected primary + verified backup | under **550 MiB** |
| Hard storage ceiling | **6 GiB** |

Qualification value: same target headroom as Option A, but limits development
overlap to one evaluation competition and leaves Bundesliga development-free.
The 74 extra base requests buy a stronger development/evaluation firewall.
It is scientifically stronger on role separation but is not silently selected
over the owner's preferred route.

### Option C — higher confidence with backup

Option A plus Ligue 1 2021/22 as a predeclared backup/additional evaluation
group.

| Item | Value |
| --- | ---: |
| Season manifests | 5 |
| Match-shot resources | 1,678 |
| Base requests | **1,683** |
| Retry reserve | **34** |
| Hard attempt ceiling | **1,717** |
| Primary projected evaluation targets | **712** |
| Backup/additional target capacity | **280** |
| Maximum projected evaluation capacity if admitted | **992** |
| Projected shots | about **43,719** |
| Expected primary raw + normalized storage | under **325 MiB** |
| Expected primary + verified backup | under **650 MiB** |
| Hard storage ceiling | **8 GiB** |

Qualification value: provides an already catalog-evidenced replacement if one
scope fails, adds a fourth evaluation season, and tests Ligue 1 across two
seasons. It does not add a third competition, so its gain is resilience and
within-competition temporal robustness, not wider competition generalization.

For all options: concurrency 1; at most one request/second; 30-second timeout;
at most two attempts/path; retry only transport failure, 408, 429, and 5xx;
stop on 401/403, second 429, schema/content-type mismatch, scope/count mismatch,
body-size violation, hash/write/immutable-path failure, conflicting IDs, disk
ceiling, retry exhaustion, or 45-minute wall ceiling. Season response cap is
10 MiB; match-shot response cap is 2 MiB. Exact endpoints remain:

```text
GET /v1/leagues/{league_id}/matches?season={YYYY%2FYYYY}
GET /v1/matches/{validated_match_id}/shots
```

Manifest count changes stop the run before shot acquisition and require a
revised budget. Tokens remain runtime secrets and cannot enter URLs, arguments,
logs, files, manifests, hashes, tests, or Git.

## Five owner decisions

| # | Exact question | Status | Recommended default | Alternatives and consequences | Blocks offline implementation | Blocks acquisition | Can affect validity |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | Freeze one development, at least three evaluation groups, two competitions, two seasons, 500 exact targets, isolation, and Rust? | **APPROVED** | Approved structure | Smaller design weakens generalization and needs amendment | No | No after other approvals | Yes |
| 2 | May roles share a competition across disjoint seasons, and are the proposed exact roles accepted? | **APPROVED** | Bundesliga 2021/22 development; Bundesliga 2022/23, Bundesliga 2023/24, Ligue 1 2022/23 evaluation | Ligue 1 development and broader routes were not selected | No | No | **Yes** |
| 3 | Freeze team history at 10 and exclude the legacy 100-match target rule? | **APPROVED** | Approved team-last-10 rule | Reintroducing 100 removes 36 projected Bundesliga targets across primary evaluation groups and needs a new decision | No | No | Yes |
| 4 | Freeze the exact observational compatibility methods, thresholds, warnings, multiplicity, and sensitivity rules above? | **APPROVED** | Frozen as written before acquisition | Post-acquisition threshold changes require a new protocol and cannot rescue a scope | No | No | **Yes** |
| 5 | Which acquisition option and exact raw-retention/request/storage authority is approved? | **APPROVED** | Option A: 1,302 base, 27 retries, 1,329 ceiling, 500 MiB expected and 6 GiB hard storage | Other options remain unauthorized | No | No | Yes |

After these five, exact acquired scope qualification, corpus/firewall freeze,
complete preregistration, model implementation, Rust execution, and one
evaluation run each require their own later authorization. None is implied by
acquisition approval.

## Scientific limitations

- Hidden upstream xG model identity and changes remain unknown.
- Provider revisions before first MatchForge acquisition are unrecoverable.
- Frozen later historical measurements may contain corrections unavailable on
  original match dates.
- Observational compatibility can miss model changes with similar outputs.
- Two evaluation competitions limit wider competition generalization.
- Projections are not exact targets until acquisition, mapping, compatibility,
  lifecycle, cutoff, protected-data, and firewall gates pass.
- Owner-accepted private retention/use assumptions are not provider guarantees.

## Next authorization boundary

Controlled acquisition may run only under
`AUTHORIZE_PITCHAPI_SNAPSHOT_V1_CONTROLLED_ACQUISITION_V1`. The ten unused
attempts from earlier authority remain separate. Corpus admission,
preregistration completion, model fitting, Rust simulation, and evaluation
execution still require later owner decisions. StatsBomb remains independent,
unchanged, and `AWAITING_PROVIDER_RESPONSE`; do not follow up until a response
arrives.
