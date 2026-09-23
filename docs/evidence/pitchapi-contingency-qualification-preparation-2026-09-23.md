# PitchAPI contingency qualification preparation — 2026-09-23

Status: `ENGINEERING PREPARATION COMPLETE — QUALIFICATION BLOCKED`

PitchAPI Bundesliga 2023/24 and Ligue 1 2022/23 remain
`TECHNICALLY_COMPLETE_RESEARCH_ONLY`. This work used synthetic fixtures and
existing sanitized evidence only. It made no provider request, retained or
reconstructed no raw response, admitted no corpus and changed no frozen rule.
The ten unused API attempts remain unavailable.

## Delivered offline

`football.validation.pitchapi_contingency` adds two pure, non-persistent gates:

1. `PitchApiSourceSeriesEvidenceV1` requires per-scope provider evidence for
   upstream supplier, model name/version/build, xG field and penalty semantics,
   export cohort, rebuild/backfill policy, corrections, ID migration,
   knowledge-mode compatibility, attestation hash, snapshot revision/hash,
   acquisition time and permission to retain prior versions. The gate returns
   `UNPROVED` for missing evidence and `FAIL` for different complete series.
   Equal free-form labels and similar distributions cannot pass.
2. `EvaluationV2CorpusGroupV1` and
   `validate_evaluation_v2_corpus_firewall` bind each synthetic group to one
   role, competition, season, internal source snapshot, series hash, target
   plan, cutoff evidence and exact MatchForge match/target IDs. The gate checks
   one development group, at least three evaluation groups, at least two
   evaluation competitions and seasons, at least 120 matches per evaluation
   group, at least 500 exact targets, different development/evaluation
   competitions, no cross-group or protected MatchForge ID intersection, no
   protected competition-season, one source series and a passed point-in-time
   check. It produces separate order-independent SHA-256 corpus and firewall
   identities plus a sanitized report.

The existing `validate_pitchapi_audit` Evaluation V2 disposition now also
requires a passing `PitchApiSeriesGateReportV1`. Matching caller-supplied
series labels alone can no longer produce an Evaluation V2 `PASS`.

Focused synthetic tests cover missing and conflicting model evidence, snapshot
order independence, role/competition/series/fixture/protected-data isolation,
minimum targets, unresolved point-in-time status, deterministic corpus hashes
and the two target-count interpretations described below.

## Adapter and stored-data design

No production PitchAPI adapter was added. Doing so now would invent source and
schema facts that the provider has not supplied and could create an
unauthorized acquisition path. After terms, export and schema approval, the
smallest adapter must:

1. expose only owner-approved fixed export resources; no live/latest fallback;
2. preserve exact bytes before parsing and assign an internal snapshot ID from
   the canonical resource manifest SHA-256, provider export/revision ID and
   acquisition time;
3. normalize fixtures, teams and shots in Python while retaining every
   provider match/team/shot ID and mapping it explicitly to a MatchForge ID;
4. retain the exact period, penalty situation and finite pre-shot xG value plus
   the qualified source-series hash on every normalized shot dataset;
5. publish corrections as new snapshots and `BitemporalCorrectionV1` records,
   never overwrite an earlier snapshot, and apply provider ID migration maps;
6. create deterministic `DatasetBuildSpecV1`, Parquet physical/logical hashes,
   walk-forward target plans and sanitized qualification reports;
7. stop before persistence if the export, model, revision, correction, mapping
   or rights evidence does not match the approved scope.

The SQL storage already supports `http_api` providers, arbitrary source
revision strings, acquired times, manifest hashes and provider mappings.
Python `SourceManifestV1`, `DatasetManifestV1`, the generic acquisition path
and the current StatsBomb firewall still assume a Git source or a specific
provider. They need a compatible provider-neutral API snapshot contract and
registration path only after an exact retained-export contract is approved.
No fake Git SHA may be used.

Rust remains unchanged. Python owns source acquisition, normalization, xG
features, target planning and evaluation. Rust may later receive only a sealed
probability distribution and simulation configuration; it must never receive
PitchAPI payloads, provider IDs, xG rows or training data.

## Why 686 matches do not prove 686 targets

The audit proved 306 Bundesliga and 380 Ligue 1 match-shot resources. Evaluation
targets require prior history, not only complete shot coverage.

Under the frozen ten-prior-team-match rule, balanced-season arithmetic gives:

| Group | Nominal matches | Warm-up matches | Provisional targets |
| --- | ---: | ---: | ---: |
| Bundesliga 2023/24, 18 teams | 306 | 90 | 216 |
| Ligue 1 2022/23, 20 teams | 380 | 100 | 280 |
| Total | 686 | 190 | **496** |

This is an optimistic policy projection, not an executed plan. The retained
audit contains aggregates, not the kickoff/team sequence and outcome-known
times needed to reproduce exact targets.

The reusable `WalkForwardDatasetSpecV1` also defaults to 100 prior competition
matches. The newer Evaluation V2 corpus decision names ten prior team matches
but does not explicitly retain or remove that older default. Synthetic complete
round-robin tests show the difference:

| Group | Team-history-only projection | Current `(team=10, competition=100)` projection |
| --- | ---: | ---: |
| Bundesliga 2023/24 | 216 | 198 |
| Ligue 1 2022/23 | 280 | 280 |
| Total | **496** | **478** |

This policy/implementation mismatch is unresolved and fail-closed. No count is
qualified and no rule was changed. Exact exclusion also depends on strictly
prior known outcomes, same-kickoff batching, the retrospective two-hour lag,
postponements, lifecycle and kickoff validity, stable ID mapping, shot-xG
qualification and zero development/protected intersection. Data defects fail
or quarantine a group; they are not removed selectively to improve the count.

A third complete independent evaluation group is mandatory even if four or 22
targets would reach 500. Every evaluation group needs at least 120 nominal
matches. Under the current 100-competition-match default, 120 matches can
produce at most 20 targets, so the arithmetic minimum is 122 nominal matches
to reach 500 or 123 to exceed it, before schedule and data exclusions. No
nominal size is safe: admission requires an exact target plan and exact total
of at least 500.

## Third evaluation group: documented candidates only

The retained catalog evidence names only Germany Bundesliga and France Ligue 1
with seasons 2021/22 through 2026/27. Austria Bundesliga is known only as a
different league ID; no retained season range exists. No API verification is
authorized.

| Rank | Evaluation candidate | Capacity screen | Unknowns / disposition |
| ---: | --- | --- | --- |
| 1 | Ligue 1 2021/22 | Likely large enough if the complete historical format is later proved | Exact manifest, match/shot counts, series, IDs, revisions, targets and rights all unknown. Best documented third-group lead. |
| 2 | Bundesliga 2022/23 | A proved 306-match structure would project 216 team-only or 198 current-code targets | Same unknowns. Could not also be development if competition names must be separated. |
| 3 | Bundesliga 2021/22 | Same provisional capacity as rank 2 if complete | Same unknowns; lower priority only because it is older. |
| 4 | Ligue 1 2023/24 | Listed historically; exact post-format-change count is not retained | Exact structure and every qualification fact remain unknown. |
| 5 | Bundesliga or Ligue 1 2024/25–2025/26 | Listed, but no completion evidence is retained | Exact scope and all qualification facts unknown. |
| Unranked | Austria Bundesliga | Separate competition identity is retained | No season range, complete season, shot coverage, series or capacity evidence. Only current lead for a competition-separated development group. |

No third group is qualified. Current evidence also cannot identify a separate
development competition. If “development/evaluation competition separation”
means only different competition-season groups, Bundesliga 2022/23 could be a
development candidate. The implemented contingency firewall applies the
stricter reading—different competition names—until the owner clarifies or
amends it.

## Remaining blockers and later work

Provider evidence is still required for governing terms and rights; exact
scope and fixed exports; upstream supplier/model/build; field semantics;
rebuilds, corrections and prior versions; stable IDs and migrations;
historical knowledge-mode compatibility; and exact price, if any.

After those facts and a separate owner approval, engineering still needs:

- a provider-neutral API snapshot/manifest contract and immutable raw store;
- the bounded PitchAPI adapter, parser and canonical registration path;
- exact provider-to-MatchForge mappings and correction integration;
- complete-group qualification, exact target plans and firewall manifests;
- immutable dataset/report publication and full requalification after any
  rebuild or model/ID migration.

Only then could the owner consider Decision 1/Decision 2 amendments, exact
corpus membership, implementation or Evaluation V2. None is authorized now.
