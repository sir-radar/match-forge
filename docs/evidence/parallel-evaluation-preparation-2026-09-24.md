# Parallel evaluation preparation — 2026-09-24

Status: `PREPARED — OWNER DECISIONS REQUIRED`

This record keeps two separate tracks:

- `EVALUATION_V2 / STATSBOMB`: frozen protocol, awaiting provider response.
- `PITCHAPI_RETROSPECTIVE_EVALUATION_V1`: separate retrospective protocol,
  still `TECHNICALLY_COMPLETE_RESEARCH_ONLY`.

No StatsBomb follow-up, PitchAPI contact, API request, raw-response retention,
acquisition, corpus admission, model fitting, or evaluation run occurred. All
ten unused PitchAPI attempts remain unavailable.

## History-rule analysis

The rules have different origins and purposes.

| Rule | Origin | Intended purpose | Protocol authority |
| --- | --- | --- | --- |
| Each target team has at least 10 prior eligible appearances | Phase 3A Evaluation V2 corpus proposal, approved without amendment in `APPROVE_PHASE3A_EVALUATION_V2_CORPUS_POLICY_V1` | Ensure the frozen last-10 xG feature has a complete prior-only window for both teams | Explicitly belongs to `EVALUATION_V2` |
| At least 100 prior competition matches | Sprint 2 target planner introduced in commit `35b48f5`; remains the default in `WalkForwardDatasetSpecV1` | Supply a global pre-evaluation training population for the Sprint 2 baseline | Sprint 2 legacy; not named in the Evaluation V2 owner decision |

The checks are logically independent but overlap in balanced leagues. Team
history controls feature availability. Competition history controls global
training volume. Neither prevents leakage by itself. Leakage protection comes
from prior-known outcomes, strict `< cutoff` availability, same-kickoff batch
freezing, and sealed target outcomes.

Current planner reuse applies both rules conjunctively. That is not proof that
the 100-match rule was approved for Evaluation V2. It must not be silently
carried into the PitchAPI protocol.

### Target impact

These are deterministic round-robin projections, not admitted target counts.
Postponements, governed kickoff claims, two-hour retrospective availability,
lifecycle, mapping, xG, protected-data, and firewall exclusions can only lower
them.

| Group | Team history 10 only | Team 10 plus competition 100 | Difference |
| --- | ---: | ---: | ---: |
| Bundesliga 2023/24 | 216 | 198 | -18 |
| Ligue 1 2022/23 | 280 | 280 | 0 |
| Current two PitchAPI groups | 496 | 478 | -18 |
| StatsBomb V2: Serie A 2015/16 + Bundesliga 2023/24 + Ligue 1 2022/23 | about 776 | about 758 | -18 |
| Ligue 1 2021/22 candidate | about 280 | about 280 | 0 |
| Bundesliga 2022/23 candidate | about 216 | about 198 | -18 |
| Bundesliga 2021/22 candidate | about 216 | about 198 | -18 |

The current two PitchAPI groups miss 500 under both interpretations: by 4 with
team history only and by 22 with both rules. A third evaluation group is still
required under the proposed architecture. Adding a Bundesliga candidate gives
about 712 or 676 targets. Adding Ligue 1 2021/22 gives about 776 or 758.

### Rule decision needed

For Evaluation V2, retain the owner-approved team-history rule. Owner must
decide whether the inherited 100-match threshold is also target eligibility or
whether any model training floor should be a separate `minimum_training_matches`
rule. For PitchAPI, inherit neither number automatically. Team history 10 is
scientifically required only if its frozen model uses the same last-10 feature.

## Proposed PitchAPI group architecture

This is a decision proposal, not a frozen policy.

| Proposed requirement | Statistical rationale | Leakage control | Generalization benefit | Target effect |
| --- | --- | --- | --- | --- |
| One development group | Provides one place to freeze adapter behavior, diagnostics, thresholds, and tuning before evaluation results | Development match IDs and season must be disjoint from evaluation; no evaluation outcome can influence choices | Prevents direct tuning on all evaluation groups | Development targets do not count toward the 500 minimum |
| At least three evaluation groups | Reduces dependence on one season and prevents the two audited groups from being treated as enough | Each group gets its own chronological target plan and same-kickoff batches | Tests repeated season behavior | Current two groups must gain one more group |
| At least two evaluation competitions | Avoids a single-league conclusion | No new leakage control beyond exact group firewalls | Tests competition transfer | Already possible with Bundesliga and Ligue 1 |
| At least two evaluation seasons | Avoids one football-year conclusion | Requires season-exact identities and no cross-group match overlap | Tests time transfer | One additional season is required |
| At least 500 exact eligible evaluation targets | Preserves enough held-out observations for proper-score and calibration analysis | Count only after every exclusion and firewall check | Limits small-sample claims | Current groups fail; documented third-group options clear provisionally |
| At least 120 nominal matches per evaluation group as a screening floor | Rejects groups that cannot contribute meaningfully before detailed acquisition | Not an admission rule; exact eligible targets remain decisive | Prevents tiny slices from masquerading as independent groups | A 120-match group can still contribute too few targets |

Development/evaluation competition independence remains an owner choice. The
lowest-request catalog-evidenced plan uses Bundesliga 2021/22 for development,
then Bundesliga 2022/23, Bundesliga 2023/24, and Ligue 1 2022/23 for evaluation.
It shares a competition across roles but keeps seasons and match IDs disjoint.
A stronger competition-independent development rule needs another evidenced
competition; Austria is only a catalog lead and has no retained season capacity.

## Third-group and development qualification plans

| Candidate | Nominal capacity | Projected eligible targets | Independence and role | Snapshot compatibility and unresolved evidence | Future calls |
| --- | ---: | ---: | --- | --- | ---: |
| Ligue 1 2021/22 | 380 if the retained catalog range resolves to a complete season | about 280 under either history rule | New season, same competition as audited Ligue 1; strongest third-evaluation lead | Expected to fit `PITCHAPI_SNAPSHOT_V1`; exact manifest, shot coverage, mappings, xG series, corrections, stable revisions, rights, and historical availability remain unproved | 381 base: 1 manifest + 380 shot resources |
| Bundesliga 2022/23 | 306 if complete | about 216 team-only; 198 with competition 100 | New season, same competition as audited Bundesliga; evaluation candidate | Same unresolved evidence | 307 base: 1 manifest + 306 shot resources |
| Bundesliga 2021/22 | 306 if complete | about 216 team-only; 198 with competition 100 | New season; development candidate in lowest-request plan, or evaluation candidate | Same unresolved evidence | 307 base: 1 manifest + 306 shot resources |
| Austria Bundesliga | Unknown | No justified projection | Better competition independence; possible development group | Only a retained league ID exists. No retained season range, manifest size, or shot coverage | 1 discovery call first; then `1 + N` base calls after a valid season and `N` matches are proved |

A manifest-only call proves acquisition-time fixture count, IDs, kickoffs, and
lifecycle fields. It cannot prove match-shot completeness. Full calls can prove
only acquisition-time payload shape, coverage, and observed distributions.
No API call can prove upstream model identity, historical revisions before
capture, legal rights, or pre-acquisition corrections.

Exact new base budgets, excluding any separately frozen retry reserve:

- lowest-request full plan, Bundesliga 2021/22 development plus Bundesliga
  2022/23 evaluation: **614**;
- Ligue 1 2021/22 evaluation plus Bundesliga 2021/22 development: **688**;
- all three documented candidates: **995**.

These are future proposals only. The remaining 10 attempts cannot execute any
plan and were not used.

## Corpus, snapshot, and compatibility preparation

The offline corpus contract now binds an explicit PitchAPI retrospective
protocol and policy hash. Each group records nominal matches, exact corpus and
target IDs, reconciled exclusion counts, source-series hash, snapshot hash,
target-plan hash, cutoff evidence, firewall access-audit hash, and point-in-time
status. The gate verifies each group UUID/hash against a supplied immutable
snapshot identity. The shared planner already handles chronological ordering,
strict outcome-availability lag, same-kickoff batching, and history thresholds.
Before admission, exclusion ledgers must separately account for
postponement/kickoff, lifecycle, MatchForge mapping, xG compatibility,
protected data, and development/evaluation firewall failures. Protected or
firewall intersections fail; they are not ordinary exclusions.

`PITCHAPI_SNAPSHOT_V1` is prepared as an immutable identity over:

- acquisition timestamp and snapshot UUID;
- unique resource references with raw and normalized hashes;
- MatchForge ID/PitchAPI alias mapping hash;
- adapter version, configuration hash, and Git commit;
- optional predecessor snapshot hash for append-only revisions.

Future season, corpus, and firewall manifests must bind those identities. This
can reproduce MatchForge state from acquisition onward. It cannot recover or
identify PitchAPI changes made before the first retained acquisition.

The xG compatibility methodology is prepared but its scientific thresholds
remain unset. It checks exact schema, finite `[0,1]` xG, penalty semantics,
shot-situation semantics, period semantics, per-competition/season missingness,
mean/standard deviation/quantiles, logistic calibration intercept and slope,
and pairwise two-sample Kolmogorov-Smirnov discontinuities. Threshold values
must be frozen before real performance results are examined. Even a `PASS`
means observational compatibility only; it does not prove identical upstream
xG models. Provider attestation remains separately necessary.

## StatsBomb response-assessment checklist

Every row starts `UNKNOWN`. A complete, compatible written answer can make a
row `PASS`; an explicit refusal or incompatibility makes it `FAIL`; omission or
ambiguity stays `UNKNOWN`. Provider answers alone never admit a dataset/export.

| Requested answer | Evaluation V2 gate | Contract evidence | Technical evidence after authorized delivery | Provider attestation | Audit still required | Dataset/export admitted by response | Later owner approval |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Inventory | Complete domestic season; at least 120 matches/group; 500-target feasibility | Named seasons, exact included/excluded matches and counts | Manifest reconciliation; complete metadata/events/lineups/shots | Yes | Yes | No | Exact scope, price/terms, acquisition, corpus |
| Competition/season coverage | At least 3 evaluation groups, 2 competitions, 2 seasons | Exact competition/season definitions and coverage obligation | IDs, counts, lifecycle and kickoff completeness | Yes | Yes | No | Same |
| Exact xG model/version | Frozen `shot.statsbomb_xg`; finite retained shots | Owner, field, model/build/export version, semantics, recalculation dates | Schema/range/penalty/period audit and public overlap | Yes; technical similarity cannot prove it | Yes | No | Accept xG evidence or decide protocol amendments |
| Cross-season series identity | One compatible series across development and evaluation groups | Written same-series statement covering all four provisional groups and recalculations | Build/manifest and overlap comparison | Yes, decisive | Yes | No | Accept evidence or amend/stop |
| Fixed export/version | Immutable fixed-snapshot knowledge mode | Export ID, schema version, effective timestamp, manifest, checksums | Byte preservation and independent hashes | Yes | Yes | No | Delivery/acquisition, then corpus |
| Revision/correction history | Reproducibility and rules for when data was known | Correction policy, change log, prior-version access, no silent overwrite | Append-only reissue and correction-ledger audit | Yes | Yes | No | Terms, acquisition, corpus |
| Stable identifiers | Deterministic MatchForge mapping | Permanence and migration rules for every provider entity | Uniqueness, referential integrity, alias migration | Yes | Yes | No | Corpus only after mapping passes |
| Retention rights | Immutable reproducibility archive | Executed Order amendment granting raw/export/manifest/hash/backup/prior-version retention after termination | Storage and restore audit | Contract required; email is insufficient | Yes | No | Final terms, spend, signature, retention/acquisition |
| Modelling rights | Lawful feature fitting, evaluation, calibration, simulation | Express download, local storage, normalization, hashing, private statistical/ML and Rust simulation rights | Access-control and use-scope audit | Contract required | Yes | No | Same |
| Derived-data rights | Retain artifacts and required evidence | Perpetual internal use of derived datasets, artifacts, forecasts, calibration/simulation output, aggregate evidence | Output classification/non-reconstructiveness | Contract required | Yes | No | Same |
| Post-contract retention | Reproducibility survives expiry/termination | Survival language overriding deletion duties for approved raw/derived items and backups | Archive/restore audit | Contract required | Yes | No | Same |
| Pricing | Commercial authorization | Itemized quote: currency, taxes, term, export/support fees, schedule, validity | Quote-to-Order reconciliation only | Quote required | No scientific audit | No | Raise `$0` cap before any obligation |
| Required Order Form/SOW amendments | Legal and reproducibility gate | Incorporated Order language for fixed delivery and all rights above, with precedence | Contract-to-delivery conformance | Executed contract required | Yes after delivery | No | Review draft; separate signature/spend authority |
| Point-in-time/source metadata | Lifecycle, kickoff, same-batch, and target sealing | Availability/update-field meanings and histories | Historical cutoff and same-kickoff audit | Yes | Yes | No | Corpus approval after pass |

If every response row passes, route becomes only `CONDITIONALLY_QUALIFIABLE`.
It still requires exact terms and price approval, separate signature/spend and
delivery/acquisition authority, immutable capture, technical qualification,
exact target/corpus/firewall hashes, owner corpus freeze, complete
pre-registration freeze, verified implementation, and separate authorization
for the one authoritative Evaluation V2 run.

## Offline implementation completed

- Replaced PitchAPI's hard-coded `EvaluationV2CorpusGroupV1` contingency type
  with a separate policy-bound retrospective group and gate.
- Bound protocol and policy identities into corpus hashes.
- Added reconciled nominal/target/exclusion counts and immutable snapshot
  identity inputs.
- Added evaluation-result identity requiring protocol, provider/source-series,
  snapshot, corpus, firewall, model build, simulation build, and target count.
- Default result-set validation rejects mixed identities; a cross-protocol
  comparison must be explicitly labelled `cross_evaluation_robustness`.
- Added policy-driven xG structural, distribution, calibration, missingness,
  and discontinuity gates with an explicit observational-only limitation.
- Added synthetic regression tests. No live acquisition path or raw storage was
  added.
- Updated machine-readable project status and local Wayfinder map to show both
  tracks.

## Separate blockers and owner decisions

### `EVALUATION_V2 / STATSBOMB`

Blocker: written StatsBomb inventory, technical answer, fixed-export and
revision details, draft Order-level exceptions, and non-binding quote. Do not
follow up until a response arrives.

Owner decisions after response: accept/reject exact scope and xG evidence;
approve/reject price and contract text; separately authorize any signature,
spend, delivery, retention, acquisition, technical qualification, exact corpus
freeze, implementation, and authoritative run.

### `PITCHAPI_RETROSPECTIVE_EVALUATION_V1`

Blockers: no frozen group policy; history/warm-up rule unresolved; no frozen xG
compatibility thresholds; no development group or third evaluation group;
upstream model/series, rights, immutable revision, corrections, stable-ID, and
pre-acquisition history remain unproved; acquisition and raw retention remain
unauthorized.

Owner decisions now required:

1. Freeze or reject the proposed one-development/three-evaluation/two-
   competition/two-season/500-target architecture and 120-match screening floor.
2. Decide whether development and evaluation may use different seasons of the
   same competition.
3. For each protocol, decide team-history-only versus a separate global
   training minimum; do not silently inherit Sprint 2's 100-match threshold.
4. Freeze xG compatibility methodology and numeric thresholds before real
   results.
5. Later, separately authorize provider/legal evidence, exact API request and
   retry budget, immutable raw retention, and acquisition. The current 10
   attempts remain unavailable.

Wayfinder map: `IN PROGRESS`.

Next boundary: repository-owner decisions above, or a StatsBomb response.
