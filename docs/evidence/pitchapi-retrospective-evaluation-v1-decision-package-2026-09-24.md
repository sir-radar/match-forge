# PitchAPI retrospective evaluation V1 — owner decision package

Status: `PROPOSED — EXECUTION NOT AUTHORIZED`

Update on 24 September 2026: owner decision
`APPROVE_PITCHAPI_HISTORY_AND_EVALUATION_ARCHITECTURE_V1` freezes the
team-last-10 history rule and high-level group architecture. Its successor
policy and final review are in
`docs/evaluation/pitchapi-retrospective-evaluation-v1-policy.md` and
`docs/evidence/pitchapi-pre-acquisition-owner-review-2026-09-24.md`. The final
review restores the owner's preferred Bundesliga 2021/22 development layout,
retains the stronger Ligue 1 development layout as an explicit alternative,
and controls where this earlier preparation differs. Acquisition remains
unauthorized.

This package implements the preparation authorized by
`ACCEPT_PITCHAPI_RETENTION_AND_PREPARE_RETROSPECTIVE_SNAPSHOT_EVALUATION_V1`.
It freezes nothing by itself. The ten remaining PitchAPI attempts were not used.
No provider was contacted and no data was acquired.

## 1. Proposed protocol

```text
Evaluation protocol:       PITCHAPI_RETROSPECTIVE_EVALUATION_V1
Historical-time mode:      RETROSPECTIVE_FROZEN_SNAPSHOT_EVALUATION
Source series:             PITCHAPI_SNAPSHOT_V1
Purpose:                   private retrospective, out-of-sample validation
Source:                    PitchAPI shot-level xG only
Acquisition:               one controlled cohort
Development groups:        exactly 1
Evaluation groups:         at least 3
Evaluation competitions:   at least 2
Evaluation seasons:        at least 2
Eligible evaluation size:  at least 500 exact targets after all exclusions
Group screen:              complete domestic season; at least 120 matches
History:                   10 prior eligible appearances for each target team
Competition warm-up:       none beyond the team rule
Knowledge limitation:      frozen later historical snapshot, not original responses
Simulation:                mandatory Rust validation under a separately frozen config
```

The protocol requires deterministic group membership, exclusion ledgers,
target plans, corpus and firewall hashes, immutable snapshots, source-series
isolation, protected-data exclusion, preregistration, chronological folds,
sealed forecasts before target outcomes, and explicit limitations. An audit or
projection is not corpus admission. Every exact scope, ID, hash, configuration,
metric, threshold, fit/calibration interval, Rust budget, and stopping rule must
be frozen before execution.

The proposed one-development/three-evaluation structure is retained. Three
evaluation groups make season stability observable and reduce dependence on
one scope; two competitions provide a cross-competition check; one development
group provides a place to finish mappings, diagnostics, implementation, and
threshold validation without consulting evaluation performance. A smaller
structure would weaken those claims and needs a separate owner amendment.

## 2. Exact differences from Evaluation V2

| Item | `EVALUATION_V2` | PitchAPI retrospective V1 |
| --- | --- | --- |
| Intended source | StatsBomb-qualified route | PitchAPI only |
| Source identity | Exact provider/model/build and compatible series required | MatchForge observational series defined by one cohort, field semantics, frozen compatibility policy, and passing scope reports |
| Historical knowledge claim | Existing fixed-snapshot and provider qualification requirements remain | Explicitly a later frozen historical snapshot; no claim of the response available at match time |
| Pre-acquisition revisions | Provider correction/revision evidence remains required | Unknown and irrecoverable; disclosed, never inferred |
| Retention/use | Existing provider-rights gates remain unchanged | Owner accepts private retention/use risk; provider attestation is not an engineering gate |
| Development source | Frozen StatsBomb La Liga 2015/16 | Proposed PitchAPI Bundesliga 2021/22 |
| Evaluation scopes | Existing V2 policy and later exact freeze | Proposed Bundesliga 2022/23, Bundesliga 2023/24, Ligue 1 2022/23 |
| History rule | Existing owner-approved V2 rules remain untouched | Proposed team-last-10 only; no inherited 100-match target threshold |
| Claims | Formal high-confidence benchmark, if every existing gate passes | Retrospective performance and robustness under the frozen PitchAPI observational series |
| Result identity | `EVALUATION_V2` | `PITCHAPI_RETROSPECTIVE_EVALUATION_V1` |

No V2 source rule, target minimum, corpus rule, firewall, provider-rights rule,
preregistration rule, or Rust requirement is changed by this package.

## 3. Permitted claims and reporting

Evaluation V2 may support the project's formal high-confidence benchmark claims
only after all existing gates pass. PitchAPI V1 may support retrospective
out-of-sample performance, cross-season robustness, calibration against the
frozen observational series, and stability across admitted competition-seasons.

Every result must bind the protocol ID, observational source-series ID,
snapshot UUID/hash, corpus hash, firewall hash, preregistration ID, model build,
simulation build, evaluation/metric/simulation configuration hashes,
evaluation date, and exact target count. Default reporting may not average,
pool, merge, or substitute metrics across protocols.

An optional `cross_evaluation_robustness` report may place independently
computed calibration, Brier score, log loss, prediction-interval behavior,
market/outcome slices, Rust stability, and challenger effect sizes side by side.
It must preserve each protocol's denominators and uncertainty intervals.
Agreement may be described as cross-source robustness; disagreement must be
shown, not averaged away. Neither result becomes automatically authoritative.

## 4. PitchAPI limitations

Every report must disclose that upstream historical xG model identity is not
independently known; provider revisions before acquisition cannot be
reconstructed; historical corrections already present at acquisition may be
used as retrospective measurements; the snapshot was acquired after the
matches; owner-accepted retention/use is not a provider guarantee; and this
result is not equivalent to Evaluation V2.

## 5. Snapshot, revision, and identity architecture

`PITCHAPI_SNAPSHOT_V1` is one immutable acquisition cohort. Each request stores
the unmodified response bytes in a content-addressed raw object and a separate
request record containing acquisition time, provider, endpoint template,
parameter identities, HTTP status, body length, and body SHA-256. Authorization
headers and tokens are never stored. Deterministic normalization produces
canonical JSON manifests and Parquet analytical tables with sorted stable keys,
explicit nulls/types, adapter/schema version, configuration hash, and normalized
SHA-256.

Per-match manifests bind the match alias, canonical MatchForge match/team IDs,
raw shot resource hash, normalized rows/hash, counts, and findings. Per-season
manifests bind the fixture resource, ordered match manifests, competition and
season. The evaluation manifest binds all group roles, exclusions, exact target
IDs, source-series/compatibility reports, target plans, corpus hash, firewall
hash, Git commit, and configuration hashes.

Later observations are new immutable series versions such as
`PITCHAPI_SNAPSHOT_V2`. Their append-only revision record binds the new snapshot
hash to the previous MatchForge snapshot hash, acquisition time, normalized
difference hash, detected provider-ID changes, and one of `NO_CHANGE`,
`PROVIDER_CORRECTION`, `IDENTIFIER_MIGRATION`, or `MIXED`. V1 is `INITIAL`.
This reproduces MatchForge observations from first acquisition onward; it does
not recreate unknown earlier PitchAPI states.

PitchAPI IDs are provider aliases, never canonical identities. MatchForge team
and fixture IDs remain stable. Alias records are snapshot-specific and bind
mapping evidence. Duplicate aliases fail. Reusing one alias for a different
canonical ID fails unless an explicit append-only remap references the prior
mapping. A changed provider ID is a migration only when it references the old
alias and maps to the same canonical ID. Historical aliases remain retained.

## 6. xG compatibility methodology and proposed thresholds

Freeze the compatibility configuration hash before inspecting MatchForge model
performance. Compute diagnostics for every scope and all scope pairs from the
frozen normalized data. Outcomes may be used only for this provider-xG
compatibility analysis, not for model selection.

| Check | Proposed hard criterion |
| --- | --- |
| Schema/semantics | Exact frozen schema; one documented xG field; identical period and shot-situation mappings; zero unknown required values |
| Numeric validity | Every admitted shot xG finite and in `[0,1]`; zero invalid values |
| Missingness | `0.0%` missing xG on admitted shot rows |
| Penalties | At least 20 penalties/scope; every value in `[0.65,0.90]`; within-scope IQR `<=0.05`; pairwise median difference `<=0.05` |
| Calibration sample | At least 1,000 non-penalty shots/scope with binary goal outcome |
| Calibration fit | Logistic goal-on-logit-xG, clipping xG only for the diagnostic at `[1e-6,1-1e-6]`; absolute intercept `<=0.25`; slope in `[0.80,1.20]` |
| Overall distribution | Pairwise two-sample KS statistic `<=0.10` |
| Shot-situation distribution | Same KS threshold for every shared normalized situation with at least 100 shots in each compared scope |
| Discontinuity coverage | All scope pairs overall; adjacent seasons within a competition when present; every sufficiently populated shared situation |

Counts, mean, standard deviation, p10/p50/p90, goal rate, calibration estimates,
sample sizes, and KS statistics are retained. Effect-size thresholds, not
p-values, decide admission because large shot samples make small differences
statistically significant. Insufficient samples are `UNPROVED`; semantic,
range, missingness, penalty, calibration, or discontinuity violations are
`FAIL`. Any `FAIL` or `UNPROVED` scope remains outside the shared series.

A pass permits only: “The admitted frozen PitchAPI competition-seasons are
observationally compatible under the preregistered PitchAPI evaluation
criteria.” It does not prove one unchanged upstream model. The numeric values
above are proposals requiring owner freeze before acquisition and before model
performance is examined.

## 7. Chronological firewall

For target match `M` at kickoff `T`, all features must use only eligible events
from fixtures with governed kickoff before `T` and outcomes known before the
applicable cutoff. The existing shared walk-forward planner groups equal
kickoffs, freezes every forecast in the batch, then reveals outcomes. Target
results, shots, xG, post-match statistics, lineup outcomes, later fixtures, and
derived future knowledge remain structurally absent until sealing.

The target plan, cutoff evidence, access audit, protected-ID manifest, and
development/evaluation role manifest are independently hashed. Any overlap,
late availability, ambiguous kickoff/lifecycle, missing mapping, failed xG
gate, or target-outcome access fails closed. The retrospective snapshot may
contain later provider corrections; causal event ordering is enforced, but
original provider publication-time state is not claimed.

## 8. Proposed groups and independence

| Role | Scope | Nominal matches | Reason | State |
| --- | --- | ---: | --- | --- |
| Development | Bundesliga 2021/22 | 306 projected | Cheapest documented disjoint season for adapter, mapping, thresholds, and implementation | Candidate; unaudited |
| Evaluation | Bundesliga 2022/23 | 306 projected | Third evaluation season | Candidate; unaudited |
| Evaluation | Bundesliga 2023/24 | 306 audited | Current technically complete evidence | Must be reacquired in the controlled cohort |
| Evaluation | Ligue 1 2022/23 | 380 audited | Second competition | Must be reacquired in the controlled cohort |

Development and evaluation may share a competition only across disjoint
seasons and match IDs. Requiring competition-independent development cannot be
met from the evidenced candidate set and would require new discovery. The
shared-competition design is acceptable because no evaluation outcomes may
influence thresholds or implementation; the Ligue 1 group still provides an
independent competition check. Owner must explicitly approve this exception.

Ligue 1 2021/22 remains the first replacement candidate if a proposed group
fails. It is not part of the base request budget. No candidate is qualified by
catalog evidence or the prior non-retaining audit.

## 9. Target-history recommendation and projected capacity

The rules have different purposes. Ten prior team appearances supplies the
approved last-10 feature window. The 100 prior competition-match rule came from
the Sprint 2 planner as a global training-volume floor; it is not a leakage
control and was not approved as a PitchAPI rule. In balanced 18-team and
20-team leagues, completing ten prior appearances per team already implies
about 90 or 100 prior competition matches. Applying both as target eligibility
is therefore legacy overlap here.

Recommendation: require ten prior eligible appearances for both teams, reset
at each season, with no separate 100-match target warm-up. Freeze fit/tune/
calibration windows and any model sample-size requirement separately in the
preregistration. This preserves the feature requirement without silently
turning a Sprint 2 default into PitchAPI policy.

| Scope | Team 10 only | Team 10 + competition 100 | Role in base proposal |
| --- | ---: | ---: | --- |
| Bundesliga 2021/22 | about 216 | about 198 | Development; excluded from 500 |
| Bundesliga 2022/23 | about 216 | about 198 | Evaluation |
| Bundesliga 2023/24 | 216 | 198 | Evaluation |
| Ligue 1 2022/23 | 280 | 280 | Evaluation |
| Evaluation total | about **712** | about **676** | Both exceed 500 before other exclusions |
| Ligue 1 2021/22 replacement | about 280 | about 280 | Not in base plan |

These are round-robin capacity projections, not exact eligible counts. The
exact post-acquisition target manifests must still contain at least 500.

## 10. Exact acquisition and audit proposal

Endpoint templates already evidenced by the audit:

```text
GET /v1/leagues/{league_id}/matches?season={YYYY%2FYYYY}
GET /v1/matches/{validated_match_id}/shots
```

Known league IDs are Bundesliga `l_1Isor4` and Ligue 1 `l_3FJFUl`. Match IDs
must come only from the corresponding validated season manifest.

| Group | Manifest requests | Shot requests | Base total |
| --- | ---: | ---: | ---: |
| Bundesliga 2021/22 | 1 | 306 | 307 |
| Bundesliga 2022/23 | 1 | 306 | 307 |
| Bundesliga 2023/24 | 1 | 306 | 307 |
| Ligue 1 2022/23 | 1 | 380 | 381 |
| Total | **4** | **1,298** | **1,302** |

Proposed retry reserve: 27 additional attempts (ceiling `1,329`, approximately
2% reserve), with at most two attempts per request path. Run at concurrency 1,
at most one request/second, 30-second request timeout, and 45-minute wall-clock
ceiling. Retry only transport failures, 408, 429, and 5xx with server-directed
delay or deterministic capped backoff. Stop immediately on 401/403, unexpected
schema/content type, wrong season/league, response above its size cap, hash or
write verification failure, duplicate/conflicting IDs, any immutable-path
collision, projected disk use above the ceiling, exhausted retry reserve, a
second 429, or the wall-clock ceiling. Partial bytes remain quarantined and can
never be called a snapshot.

No current API attempt may be used. Acquisition requires a new owner budget
covering all 1,329 possible attempts and raw retention.

### Storage and hashing

The prior audit retained no body sizes, so storage is an explicit planning
estimate, not a measurement. The 1,298 matches project roughly 33,850 shots
from the retained audit rate. At 2 KiB/shot plus fixture/manifests, expected raw
and normalized primary storage is under 250 MiB; one verified backup makes the
expected requirement under 500 MiB. Provision 6 GiB and enforce it as a hard
ceiling. Also cap each season response at 10 MiB and each match-shot response at
2 MiB; the caps explain the conservative ceiling.

Hash the exact response body while streaming to a temporary file, fsync, verify
length and SHA-256, then atomically publish to a content-addressed immutable
path. Normalize only from the verified raw object. Hash canonical JSON
manifests and deterministic Parquet logical content; record physical file
hashes separately. Re-read and verify every object and the backup before
freeze. Never overwrite an existing path with different bytes.

Secrets enter only through the approved runtime secret mechanism. They may be
sent only in the required authorization header, never CLI arguments, URLs,
files, logs, exception text, manifests, hashes, tests, or Git. Logs contain
request IDs and redacted endpoint templates only.

### Validation and freeze sequence

1. Owner approves policy/thresholds, roles/history, 1,329-attempt budget,
   6-GiB ceiling, raw retention, and acquisition.
2. Pin Git commit, dependency lock, adapter/schema, normalization config,
   endpoint allowlist, scope manifests, and cohort UUID; run offline tests.
3. Acquire and verify the four season manifests; stop if exact counts differ
   until a revised budget is approved.
4. Acquire each manifest-derived shot resource under the controls above.
5. Reconcile request ledger, resources, fixtures, teams, shots, aliases,
   lifecycle/kickoff fields, and zero unaccounted failures.
6. Normalize deterministically; run identity, completeness, semantics, xG,
   compatibility, protected-data, and chronology gates.
7. Assign stable MatchForge identities and produce mapping/remap evidence.
8. Build per-match and per-season manifests, exact target plans, exclusion
   ledgers, corpus hash, and firewall hash.
9. Copy to the immutable backup, independently re-hash raw and normalized
   objects, make both locations read-only, and seal `PITCHAPI_SNAPSHOT_V1`.
10. Return the exact corpus and gate evidence for owner freeze. Do not fit or
    evaluate until the preregistration and separate execution decision exist.

## 11. Required tests before acquisition

The current repository now has offline tests for immutable snapshot identity,
append-only version/predecessor chains, duplicate revisions, alias collisions,
evidenced remapping, provider-ID migration, changed IDs across snapshots,
duplicate aliases, observational cohort/semantics compatibility, protocol and
result separation, protected/development/evaluation intersections, deterministic
hashes, exact exclusion reconciliation, target projections, calibration and
distribution gates, and configuration/date-bound result identities.

Before acquisition authorization, add integration tests for streaming body
limits, atomic publish/fsync, crash-resume without overwrite, HTTP retry/stop
behavior, content-type/schema rejection, redaction, raw-to-normalized hash
reproduction, Parquet logical determinism, backup restore, full manifest
reconciliation, and disk-ceiling enforcement. Existing shared tests for strict
`<` cutoff, availability lag, same-kickoff batching, target sealing, and future
outcome exclusion must remain passing; add a frozen cohort integration fixture
that exercises the complete PitchAPI path before any live request.

## 12. Risks that cannot be eliminated

- Unknown PitchAPI xG model identity and pre-acquisition model changes.
- Unknown provider corrections or identifier history before first capture.
- Later historical data may differ from what was available on match day.
- Owner-accepted legal/use assumptions are not provider guarantees.
- Observational compatibility can miss model changes that produce similar
  distributions and calibration.
- Competition/season results may not generalize outside the admitted scopes.
- Exact targets and storage remain projections until authorized acquisition.

## 13. Exact owner decisions required before execution

The owner must separately approve or amend:

1. the proposed protocol and its permitted claims/mandatory disclosures;
2. exactly one development and at least three evaluation groups, including
   shared-competition/different-season development independence;
3. team-last-10-only target history and removal of the Sprint 2 100-match
   target threshold from this protocol;
4. every compatibility method and numeric threshold above;
5. the exact endpoint allowlist, 1,302 base requests, 27-retry reserve,
   1,329 hard attempt ceiling, pacing, timeout, and stop rules;
6. 6 GiB storage, immutable raw retention, backup, and secret controls;
7. implementation of the live acquisition/storage path after all preflight
   integration tests pass;
8. the acquired scope qualification reports and exact snapshot/corpus/firewall
   identities after acquisition;
9. the complete preregistration, model/metric/simulation configurations,
   compute budget, and accountable owner;
10. one authoritative PitchAPI evaluation run.

These decisions do not authorize StatsBomb spending, delivery, or Evaluation
V2. StatsBomb remains independently `AWAITING_PROVIDER_RESPONSE`; no follow-up
is authorized while waiting.

## 14. Evaluation V2 immutability evidence

Before this change, the relevant frozen files had these SHA-256 values:

```text
90812c0119e84a5bef94e8726ba9f4a984c33f8a6bb655603c68738994a345b3  docs/evaluation/evaluation-v2-policy.md
164b459089f54ba2023f92457579e400f78f183b88db50cc8620cf4a70a2e6b1  docs/evidence/owner-decision-approve-phase3a-evaluation-v2-corpus-policy-2026-09-21.md
4e7f880fa20b038e226473f860608e61180505f6c741660b6243d726cddb0b24  docs/governance/phase3a-xg-for-evaluation-v2-freeze-proposal.md
```

Final verification must reproduce all three hashes. Any mismatch blocks this
package.

Wayfinder map: `IN PROGRESS`.

Next boundary: owner decisions 1–7 above, an independent StatsBomb response,
or both. No acquisition or evaluation begins automatically.
