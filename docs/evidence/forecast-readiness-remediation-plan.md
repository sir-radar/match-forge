# Forecast readiness investigation and remediation plan

Investigation date: **3 November 2026**. Delivery scope: **research and documentation only**.
Source checkout: `fd606e3` on `ft/data-status-remediation`, after merging `main`
`e4ea615c`. No production fix, migration, identity admission, recovery mutation,
model fit, evaluation, promotion, cutover or deployment is part of this task.

## Investigation checkpoints

| Phase | Scope | Result |
| --- | --- | --- |
| 1 | Current requirements, main synchronization, operating baseline and prior-target accounting | PASS_WITH_WARNINGS; commit `a28e16f` |
| 2 | Source/code traces, identity, coverage, parity and external research | PASS_WITH_WARNINGS; commit `677a646`; data proof and isolated profiling gaps recorded |
| 3 | Actionable issue specifications, dependencies and acceptance review | PASS_WITH_WARNINGS; prose, links, IDs, receipt hashes and whitespace checks PASS |

## 1. Executive summary

The earlier **153** verified upcoming blockers are not the current backlog.
At the fresh baseline, all **29 Coventry**, **20 Málaga** and **13 Armenian**
targets have `FORECAST_AVAILABLE`; **91** original targets remain blocked.
These recoveries preceded this investigation. Do not count them as potential
new gains or design another identity merge to recover them again.

The fresh scheduled-future population contains **6,320** fixture records:
**2,365** verified available, **196** verified blocked (148 insufficient history,
48 source-incomplete), and **3,759** provisional source-incomplete records.
The 196 include the 91 remaining original targets and 105 additional targets.
The universe moves with time, provider discovery and background workers.
Stored availability is a diagnostic label; later sections separately test identity
and history prerequisites. Provisional records and multiple representations must
not be added to a promise of unique forecast gains.

The handoff freshness check has **190** verified upcoming blockers; six B1 targets
have passed their kickoff without changing availability (section 12). The frozen
196-target inventory remains the basis for issue accounting.

There are **226** competitions marked available and **301,307** eligible
historical results at the baseline cutoff. The five historical parity jobs
completed execution but each produced a **BLOCKED** diagnostic report. They
repeat the shared Architecture V2 comparison requirements; they are not five
independent fixture-reconciliation failures.

## 2. Operating baseline and evidence method

### Snapshot and scope

Baseline B1: `2026-11-03 14:56:39.190037 UTC` (15:56:39 Africa/Lagos), database
`football`, PostgreSQL 18.6, snapshot `17918226:17918226:`. Connections set
`default_transaction_read_only=on`; collections explicitly begin
`REPEATABLE READ READ ONLY` and roll back. Credentials stay in the local `.env`.
The [PostgreSQL transaction contract](https://www.postgresql.org/docs/18/sql-set-transaction.html)
explains the consistent snapshot and enforced write restrictions.

Private receipts and query text are under `.local/forecast-readiness-investigation/`.
They are not distributable football datasets. The tracked report will retain
exact target IDs, aggregate results and reproducible query recipes. Snapshot
identifiers are descriptive, not replayable after their transaction closes.
Collections made later are separate snapshots, not extensions of B1.

The first baseline collector successfully completed every population query, then
failed its final stage-settings query because it used `stage_order` instead of
schema column `stage`. The successful read-only results remain in `baseline.json`;
the failed query is disclosed rather than represented as a passing collection.
The stage query is corrected in the separate detailed collection. Initial
sandbox denials for Git metadata, localhost and GitHub were resolved through
reviewed access. No automatic approval rejection occurred.

| Population | B1 measurement | Interpretation |
| --- | ---: | --- |
| Competition availability | 226 available; 1,017 insufficient history; 361 source-incomplete; 54 no fixtures | 1,658 competition rows, not a market-qualification count |
| Eligible history | 301,307 | Existing eligibility function at B1 knowledge cutoff |
| Retained history | 479,460 | Includes ineligible observations; not additive with eligible history |
| Latest history decisions | 301,307 eligible; 178,151 identity-policy ineligible; 2 non-played | One latest decision per fixture |
| Context report work | 148,095 pending of 229,235 rows; zero recorded errors | Backlog, not 148,095 missing football matches |
| Performance reports | 7 pending of 3,794 | Secondary derived reporting |
| Comparison reports | 0 pending of 1,362 | No current backlog in this queue |
| Forecast refresh work | 0 pending of 8,276 | Empty queue does not prove all targets are forecastable |
| Native history scopes | 1,224 total, only 2 SUCCEEDED | Completion requires exact scope evidence |
| Parity follow-ups | 5 executed SUCCEEDED, all outcomes BLOCKED | Worker success differs from parity success |

| Provider | Retained product history | Eligible history | Eligible competitions |
| --- | ---: | ---: | ---: |
| API-Football | 58,949 | 58,077 | 318 |
| football-data.org | 5,389 | 2,646 | 8 |
| Football-Data.co.uk | 236,709 | 136,927 | 20 |
| FotMob | 87,743 | 29,813 | 75 |
| OpenFootball | 89,930 | 73,828 | 45 |
| PitchAPI | 740 | 16 | 3 |

Provider totals must be read from B1, not copied from earlier recovery receipts.
StatsBomb and retained research providers use separate representations; their
resource/event counts are not product-history counts.

### Repository and programme dependencies

[PR #179](https://github.com/sir-radar/match-forge/pull/179) is the current branch's
open delivery PR. [PR #178](https://github.com/sir-radar/match-forge/pull/178) remains
open at `463ec15a8a0720fb48e842af5a009cf140545f90`. Neither is merged or deployed by
this task. PR #178's StatsBomb recurrence prevention records database-generated
UUIDs honestly as `provider_native`; its independent relationship prerequisite
and actual legacy correction remain blocked. A five-fixture research pilot is
not operating forecast or broad V4 acceptance.

The operating migration is `202611020200`. Architecture V2 remains in progress;
cutover and retirement remain blocked. Sprint 2 remains FAIL and later scientific
work is not reopened. This is an owner-requested investigation, not a claimed
Wayfinder implementation ticket. No terminal route is mutated. See
[project status](../project-status.json), the latest sections O/P of the
[data recovery report](data-status-remediation-report.md), and the
[source acquisition register](../source-acquisition.md).

### Investigation standard

Trace source registration → parser → provider identity → admitted MatchForge
identity → fixture reconciliation → dated history decisions → eligible history
→ ten-match rolling inputs → forecast publication. Use existing SQL functions
and Python owners. A name match, source download, successful job or admitted
competition alone does not prove the rest of this chain.

Research records distinguish factual football evidence, exact native-ID evidence,
access/entitlements and scientific eligibility. Newly retrieved facts cannot be
backdated into earlier forecast inputs. This document recommends later work;
its illustrative execution phases do not authorize that work.

## 3. Confirmed findings

### Target-specific causes, rather than availability labels

B2 (`14:58:19.119021 UTC`, snapshot `17921085:17921085:`) traces all 258
unique records in the union of the original 153 and current 196 blocked targets.
It calls `fixture_identity_blockers` without mutating admissions and counts
`product_eligible_history_at` using the same exact/date-only cutoff rules as
`ProductSync._target_history`. All 196 current blocked targets have a specific
first cause; none has both identity and history prerequisites satisfied.

| Mutually exclusive B1 target group, tested in B2 | Targets | Next barrier |
| --- | ---: | --- |
| Identity blocked; both sides already have ten eligible results | 5 | Exact native team relationship/admission |
| Identity blocked; both sides have ten retained but insufficient eligible results | 15 | Identity plus dated historical qualification |
| Identity blocked; at least one side has fewer than ten retained results | 28 | Identity plus additional authentic history |
| Identity passes; both sides have ten retained but insufficient eligible results | 26 | Qualify retained history; no guaranteed release |
| Identity passes; at least one side has fewer than ten retained results | 122 | Acquire/qualify additional authentic history |
| **Total** | **196** | Groups are disjoint; later issue impacts overlap |

The five immediate identity candidates are Rochdale–Doncaster
`ae988ae0-adc1-5335-9fc4-ff02bc44c51a`, Huddersfield–Luton
`073b77c4-a7e6-5fbc-8957-2caffbc8e391`, Northampton–Oldham
`8e72c406-288c-5dcf-ac8a-b3ae4f2f09eb`, Wigan–Mansfield
`993b50d0-3c38-52b7-8f62-bdee6cf6d637`, and Pamplona–Eibar
`0e7f724a-6894-5599-a8f6-6f30c7f8dec8`. Fresh source classification still returns
`VERIFIABLE_CROSSWALK_AND_CONTEXT_REQUIRED` for relevant English native mappings;
existing large history counts do not supply the missing relationship proof.

The ten-match requirement is in
[`forecast_history_window`](../../python/football/src/football/product/domain.py),
not a minimum of ten head-to-head matches. The production path is
`ProductSync._prepare_forecasts` → `_batch_history` → `_target_history` →
`forecast_from_history` → `_publish_prepared_forecast` in
[`sync.py`](../../python/football/src/football/product/sync.py).
History decisions, provider identity and source knowledge precede those functions.
Do not add model database queries, lower the minimum, or use target outcomes.

### Coventry and Málaga: recovered targets, unresolved wider origin relationships

Coventry's recovered targets use MatchForge team
`21c6f977-cea1-5551-bb07-8ff204ddbf26` (FDO `1076`, FotMob `8669`). The API-Football
`1346` origin remains separately `74e76cfd-e222-5ff6-b58e-b503c8f8360b`;
Football-Data.co.uk `Coventry` is `f22144e8-449e-5de2-9125-4adcc351c3a6`;
OpenFootball `Coventry City` is `ec2e22c2-311f-5fea-b29d-2a51f0039331`.
These UUIDs must not be collapsed by name. Fresh checks confirm the native FDO
origin and reviewed FotMob link. FDO `ELC` competition admission recovered
retained history through the existing fallback path. B2 counts **45 eligible /
49 retained** Coventry results for example target
`d91dfb10-fe75-5f8d-8118-5a9a0aea85f2`; it already has a published forecast.

Málaga's recovered targets use API-Football `535`, MatchForge
`f89ad343-fd17-59b7-b4fe-4536e58e7f8f`, with the reviewed FotMob `9864` link.
FDO `84` remains `9121e8b9-467f-5e0b-a03b-2cfaf12c2288`; Football-Data.co.uk
`Malaga` remains `a2ae6f71-0500-5852-a215-59e65fe4b355`; OpenFootball `Málaga CF`
remains `80c0b812-dd7a-5b0d-aac3-b1e87113cf3b`. B2 counts **32 eligible / 50
retained** Málaga results for target `48c38317-2de9-56ca-a58f-2ccba6d28022`;
it already has a forecast. All 49 original Coventry/Málaga targets have forecast
rows in B1. Separate U21, reserve, `Malaga B` and `Málaga II` identities are
not substitutes for senior history.

The preceding recovery inserted 40 Málaga native results, left native fixtures
`1217677`/`1217899` blocked at the team/timestamp guard and did not import the
46 newly retrieved Coventry results. Those are **remaining history coverage
questions**, not 49 still-unavailable targets. The old receipt has exact source
snapshot, hashes and rejected rows; the current observation table has no entries
for the two rejected API-Football IDs, so an observation replay alone cannot
recover them.

[`crosswalk_resolution._revise_mapping`](../../python/football/src/football/product/crosswalk_resolution.py)
retains `entity_id`; changing its method is not a merge.
[`identity_correction._qualify`](../../python/football/src/football/product/identity_correction.py)
requires an incorrect FDO explicit crosswalk projected onto an origin, an approved
API-Football target and retained supporting fixture/context proof. Valid native
origins do not satisfy that contract. Prefer directly eligible native history
for immediate coverage. Extend prospective linked correction only for a proven
relationship with an explicit compatibility reason; never weaken `_qualify` to
accept arbitrary origins. New corrections must leave all earlier-cutoff results
and published input hashes unchanged.

### Ghana: replaced mapping rows leave old fixture participants stranded

The 30 original Ghana targets involve old Medeama UUID
`a2c3853c-e62b-5e64-8260-1ddf9a3899d2` and/or Port City UUID
`eace79b0-415c-5d1e-92e1-f75568c227b0`. Their API-Football mappings were closed
on October 16 and revoked. Current API-Football `12255` maps to Medeama
`95464491-fd01-54e3-b2bf-4994571d86d2`, and `26805` maps to Port City
`6bcd1a34-f170-56a4-8901-32bb82e88847`, both admitted origins. FotMob
`106975`/`2103806` are reviewed against those current targets.

This is a concrete old-participant/current-mapping mismatch. Old Medeama retains
210 results but zero eligible; old Port City retains six and zero eligible.
`product_fixture_team_at` reads dated admissions attached to mappings for the
stored participant; it does not automatically equate old and new UUIDs sharing
a native identifier. Re-admitting only the new mapping cannot repair old targets.
Source-backed linked reconstruction of the affected fixture/history records is
required. Even after identity repair, Port City's history must independently
meet the minimum. Do not attribute all 30 to missing acquisition or assume all
30 become ready after a mapping correction.

### Scotland: source geography is fixed; historical identity remains split

The retained 2000/01 ZIP is still **215,164 bytes**, SHA-256
`56d48575f4100b37467f945fe8e06c69d70040f36071909493634d2d703ed6ef`, snapshot
`c3cb0119-6c75-5d5f-af91-db5f89864e44`, resource
`77e58390-1520-5d03-8d87-b0057f4bcec5`. Direct byte verification and the existing
retained-identity verifier agree. `SC1`, `SC2`, `SC3` each contain 180 completed
rows and ten distinct club labels. The corrected parser assigns Scotland and
tiers 2/3/4, while retaining date-only precision and original row IDs.

The original 30-team archive problem expands to **41 current `World` mappings**
across later archives, including aliases `Raith`/`Raith Rvs`, `Airdrie`/`Airdrie Utd`,
`Edinburgh City`/`FC Edinburgh`, and historical Gretna/Clydebank. All 41 persisted
latest decisions still say `ORIGIN_ANCHOR`; fresh classification returns
`UNRESOLVED: RETAINED_SOURCE_EVIDENCE_REQUIRED` because corrected parsing no
longer supplies that `World` identity context. This distinction exposes stale
admission evidence; it is not permission to silently rewrite those decisions.
Ten separate current Scottish mappings remain unresolved crosswalks; two current
Scottish origin mappings verify.

All three competition proofs freshly classify `CROSSWALK`. Stored status has
changed since the earlier withheld-admission report: **SC2 is now CROSSWALK**;
SC1 and SC3 still have stored unresolved decisions. Their active mapping IDs are
`01a1044a-3067-79ef-800d-1037e934d469` (SC1),
`01a1044a-3065-714d-93eb-5fb63eee381b` (SC2), and
`01a1044a-3069-7e3d-8152-d4d3c117ab3e` (SC3). A later read-only snapshot counts
5,137 eligible Football-Data.co.uk SC2 rows plus 554 API-Football rows across
all three competitions. The earlier 554-only baseline is obsolete; none of this
background gain belongs to this investigation.

A low-level `PostgresIntegrityVerifier.verify_raw_resource` call reported the
ZIP missing in the modern `raw/` layout. The file actually remains at its
registered legacy path. Existing `resolution_data.resource_check` already checks
that registered path and verifies the bytes. This rejected diagnostic lead is
not evidence of another missing original and does not justify a duplicate
verifier. Use the existing legacy-aware check.

### Systemic historical ingestion and recovery findings

- Football-Data.co.uk has **730 `PROVIDER_MATCH_ID_REUSED` conflict records over
  ten snapshots**, 151 team/timestamp conflicts over six snapshots and 19
  unreviewed cross-provider conflicts over six snapshots. These are conflict
  records, not guaranteed distinct recoverable matches. `parse_csv_resource`
  builds native IDs from `source_path#row_number`; rolling `Latest_Results.csv`
  reuses those positions for different fixtures. The guard correctly refuses
  identity reuse. Preserve old IDs and distinguish source-version observations
  before any future ingestion change.
- At B1, 178,151 latest history decisions are identity-policy ineligible. This
  total includes multiple causes and does not mean 178,151 erroneous decisions.
  The 26 history-only targets with enough retained rows are a bounded first
  recovery cohort; 122 need additional history in their current identity scope.
- B1 has 11,934 distinct FotMob and 1,589 distinct PitchAPI native IDs with an
  unmatched FINISHED observation. A later latest-observation-only census reduces
  this to **9,576 FotMob / 1,508 PitchAPI** current FINISHED IDs. Historical
  unmatched revisions persist after later reconciliation, so neither count is
  a forecast gain. Latest mapping reasons include unavailable source seasons,
  no exact candidate, contradictory mappings, and explicit relationship proof.
- `_usable_provider_season_label` in
  [`operational_provider_sync.py`](../../python/football/src/football/product/operational_provider_sync.py)
  deliberately holds absent/unknown seasons. `_record_failed_observation` retains
  failures and source provenance. Deriving season solely from kickoff would
  bypass a real contract; replay exact season-resource metadata instead.
- Provider scopes remain 870 PENDING, 338 FAILED, 14 DEFERRED and two SUCCEEDED.
  FotMob's 238 identity failures and 95 completed-with-errors cases require
  different actions from live-priority deferrals. The legacy queue has 500
  quota/cooldown holds, nine deterministic identity conflicts, two FDO 429 holds
  and 132 successes. Do not classify all pending work as retryable network loss.
- DED, PD and BSA have no committed native FDO competition mapping in the
  inspected current set. Earlier admission attempts rolled back at downstream
  enqueue deadlines. The deployed admission trigger calls
  `record_product_history_decisions`; inserted decisions invoke row-level
  context refresh fanout over eligible future targets. The fanout is a verified
  code path and a strong bottleneck candidate; its precise runtime share still
  needs isolated profiling. Raising deadlines or dropping refreshes is not a fix.

## 4. Five parity reports and deployment dependencies

The following five work items are all `SUCCEEDED`, each with a checksum-bound
`BLOCKED` report and retained-comparison verification `PASS`:

| Native case | Work ID | Cause request ID |
| --- | --- | --- |
| PitchAPI `m_0c0woG` | `fa47db26-e183-5d21-9b47-003754f0e9a9` | `1cbcd0f3-a46e-4cf5-b36a-7c0698f4dcac` |
| PitchAPI `m_0Aknsd` | `70ce98ed-c5cf-5621-896b-555f715c3b94` | `9a176628-fdec-4e9b-9cce-5dd70cb4b600` |
| PitchAPI `m_08g6fR` | `625aaf73-e724-58ac-888d-f968a072b190` | `d3fbddf1-4000-4f65-a064-07c7c86efcab` |
| PitchAPI `m_0AXpZd` | `48318dc7-fa10-57ff-8695-5fa54ef1269a` | `980471aa-64e7-47be-aafe-b3b1b8114ded` |
| PitchAPI `m_0C3SKQ` | `3d55f24e-84c9-53c1-9a33-6bb17d7cfcd8` | `391be03d-a044-4c47-8a56-cd6d57fa1046` |

Every report has the same required comparison gaps:

| Contract group | Recorded result | Upstream dependency / required evidence |
| --- | --- | --- |
| Provider acquisition/source bytes | BLOCKED | Registered originals and exact scoped old/new acquisition comparisons |
| Native parsing/normalization | BLOCKED | Complete required provider/resource scopes, beyond bounded retained samples |
| Identity/canonical state | BLOCKED | Unresolved/contradictory relationships and canonical decisions |
| Coverage/quality | BLOCKED | Complete resource/fixture coverage and all differences explained |
| Serving/read models | BLOCKED | Equivalent complete production reads after upstream qualification |
| API/consumer contracts | BLOCKED | Equivalent consumer payloads, route and lineage contracts |
| Feature/forecast inputs | BLOCKED | Frozen cutoffs, 59 recorded Elo conflicts and 327 recorded history gaps require disposition |
| Work orchestration | BLOCKED | Full pending/in-flight ownership, retry/fencing and completion comparison |
| History coverage | NOT_RUN | Complete scoped old/new history comparison has not been registered |
| Performance/external reports | NOT_RUN | Complete scoped old/new report comparison has not been registered |
| Forecast artifacts/routing | NOT_RUN | Complete scoped artifact lineage/routing comparison has not been registered |

The Elo/history exception figures are **historical comparison evidence**, not
recalculated B1 target counts. The reports' earlier identity diagnostics contain
970 unsafe groups, 4,969 unresolved and 108 contradictory classifications, while
B1's persisted latest admission counts have since changed. Do not label that
retained diagnostic as a fresh identity audit.

[`verify_parity` and `overall_status`](../../python/football/src/football/product/resolution_parity.py)
recheck retained files and current diagnostics; `migration_report` in
[`resolution_migration.py`](../../python/football/src/football/product/resolution_migration.py)
reads the tracked Phase 35 blocker-resolution evidence. It cannot manufacture
new full-runtime comparisons. There is no demonstrated five-job execution defect.
Retrying identical reports or relabeling SUCCEEDED as parity PASS cannot meet
these contracts.

The deployed schema includes file/parity/stage tables and all 13 stage routes
remain `LEGACY`. The old statement that these tables are absent is stale.
PR #178's `202611020100` migration concerns honest mapping methods; this branch's
`202611020200` concerns history failure deadlines. The operating migration table
must be inspected for each version, not only `max(version_id)`, before later
rollout. Neither migration proves parity. Resolve scope/evidence gaps and rerun
existing gates in the authorized architecture programme; do not perform cutover
or scheduler retirement as forecast-data cleanup.

## 5. External research and decisions

Sources below were searched/read on 3 November 2026. Indexed excerpts are
identified where full pages were unavailable. They are research evidence, not
newly registered football inputs. No credentialed provider endpoint was called.
No provider request limit was evaded. Public facts require retained source
registration and exact native-ID verification before later operational use.

| Ref | Question and searches | Primary evidence / result | Recommendation and limitation |
| --- | --- | --- | --- |
| R1 | What do historical SC1/2/3 represent? Searched native codes and 2000/01 division names. | SPFL [First Division](https://spfl.co.uk/league/championship/archive/111), [Second Division](https://spfl.co.uk/league/league-one/archive/215), [Third Division](https://spfl.co.uk/league/league-two/archive/249); retained CSV membership agrees. | Country is Scotland; preserve period-specific division context. Current competition names do not prove club continuity or exact provider links. |
| R2 | Can Airdrie, Airdrie United and Clydebank be treated as one club? Used club, federation and historical-archive searches. | [Airdrie club history](https://www.airdriefc.com/club-history) records 2002 liquidation; [Clydebank trust history](https://www.clydebankfc.com/the-trust/trust-history/) records the transfer; [club timeline](https://www.clydebankfc.co.uk/club-timeline.php) exposes competing continuity claims. | Use dated club identities and exact season participation. Sporting continuity, legal membership and current branding are distinct. Do not merge these labels automatically. An explicit policy decision is required only where the established identity policy does not resolve the proven succession. |
| R3 | Does Ghana lack historical football facts, or a valid identity chain? Searched exact clubs, promotion and official participation. | GFA [2026/27 clubs](https://www.ghanafa.org/index.php/eighteen-clubs-confirmed-for-2026-27-ghana-premier-league-season), [Port City promotion](https://www.ghanafa.org/index.php/port-city-fc-clinch-ghana-premier-league-qualification-with-four-games-to-spare), [Medeama fixtures](https://www.medeamasc.org/fixtures). | Facts support participation and a route to earlier Port City Division One results. They do not equate the old and new MatchForge UUIDs; exact retained native IDs and admission history must do that. |
| R4 | Which API-Football seasons are technically accessible? | [Provider workflow](https://www.api-football.com/news/post/how-to-get-all-data-from-a-league-with-api-football) distinguishes league/season coverage and account access; free 2026 history is described as 2022–24. | Keep account cap, quotas and response failures. Do not request 2025/26 using public coverage as entitlement. Current account dashboard was not accessed. |
| R5 | Are FDO competition codes and historical resources stable contracts? | [v4 quickstart](https://www.football-data.org/documentation/quickstart), [v4 reference](https://docs.football-data.org/), [pricing](https://www.football-data.org/pricing). | Reuse approved native competition mappings and retained responses. A plan advertisement does not prove account history access; native team origins stay separate unless relationship proof qualifies. |
| R6 | Can another open result archive fill gaps without a new acquisition engine? | [OpenFootball football.json](https://github.com/openfootball/football.json) supplies public-domain results in season files. | Reuse pinned importer and resource-specific coverage. It does not supply xG/player context or native commercial-provider identity proof. Prefer this over a new bulk scraper where coverage exists. |
| R7 | Can PitchAPI solve missing source seasons? | [Provider reference](https://pitchapi.dev/) documents native resources, catalogue history and retry behavior. | Reuse exact season responses and retained replay. Do not infer all archived scopes, same-feed independence or pre-kickoff knowledge from advertised availability. |
| R8 | What is Mainz women's continuity? German-language club searches distinguish senior women from men. | [Mainz announcement](https://www.mainz05.de/news/frauenfussball-kuenftig-auch-im-05-trikot-tsv-schott-mainz) describes the Schott women's transfer; [2023 membership report](https://mv.mainz05.de/brosch2023.pdf) documents the completed move. | Investigate dated women's history under the exact women's native IDs. Never substitute the men's team or assume all Schott historical rights/IDs transfer. Six target fixtures have 10 retained / seven eligible Mainz results. |
| R9 | Does Garudayaksa have pre-promotion senior history? Indonesian name, league and predecessor searches were used. | Official [club page](https://www.ileague.id/clubs/single/BRI_SUPER_LEAGUE_2026-27/garudayaksa_fc), [2025/26 regulations](https://assets.ileague.id/uploads/files/regulasi-pegadaian-championship-2025-26.pdf), and [27-match final table](https://www.ileague.id/table/download/89/PEGADAIAN%20CHAMPIONSHIP%202025-26/1/0/Grup%201) provide an acquisition lead. | Prefer Garudayaksa's own 2025/26 results to assuming a predecessor merger. Nine retained / five eligible results currently affect ten targets. An academy or U19 result is not a senior label. |
| R10 | Where can Bắc Ninh's earlier senior fixtures be verified? Initial VFF-only and province searches were broadened to the competition operator and Vietnamese wording. | VPF [club page](https://vpf.vn/team/bac-ninh/), [2025/26 draw](https://vpf.vn/tin-tuc/thong-cao-bao-chi-le-boc-tham-va-xep-lich-thi-dau-giai-hnqg-2025-26-va-cup-qg-2025-26/), and [exact round-22 registration](https://vpf.vn/hang-nhat-tai-lieu/hang-nhat-thong-bao/danh-sach-dang-ky-thi-dau-clb-bac-ninh-vs-clb-tre-pvf-cand-vong-22-hnqg-bia-sao-vang-2025-26/). | Acquire dated senior results and exact provider bindings. Six retained / three eligible results affect four targets. Generic province and U11/7-a-side hits were rejected. |
| R11 | Can Bangladesh identities/seasons be established from public reports? Searched BFF regulations, exact club names, season fixtures and independent tables. | [BFF regulations](https://www.bff.com.bd/index.php/category/regulations) establish competition documents; [RSSSF season archive](https://www.rsssf.org/tablesb/bang2026.html) supplies a factual lead; news reports disagree in season labeling. | Research Fakirerpool, Arambagh, Dhaka Wanderers and City Club separately. No exact native link is proved by these pages. Obtain BFF match records and original provider seasons; do not resolve the disagreement with a date guess. |
| R12 | Why are continental targets short of history? | AFC [2026/27 entry list](https://www.the-afc.com/en/more/afc_competitions.html/news/202627-line-ups-confirmed-for-afc-men%E2%80%99s-club-competitions), [competition rules](https://assets.the-afc.com/downloads/tournament-regulations/AFC-Champions-League-Two-2026-27-Competition-Regulations-Jun18upd.pdf), [J.League fixture register](https://www.jleague.jp/en/acl2/match/search-list/). | Cross-check exact senior entrants and domestic history. Continental `World` competition geography is legitimate; do not replace it with a club country or merge similarly named teams. |
| R13 | How should the admission fanout be optimized? | PostgreSQL 18 [trigger behavior](https://www.postgresql.org/docs/18/trigger-definition.html), [transition relations](https://www.postgresql.org/docs/18/sql-createtrigger.html), [PL/pgSQL examples](https://www.postgresql.org/docs/18/plpgsql-trigger.html). | Profile in a disposable populated restore. Prefer one deduplicated set of affected refresh keys per statement using existing queues, preserving generation/fencing rules. Benchmark before choosing transition tables over a scoped set-based writer. |
| R14 | How can snapshots and concurrency remain correct? | PostgreSQL 18 [transaction isolation](https://www.postgresql.org/docs/18/transaction-iso.html), [SET TRANSACTION](https://www.postgresql.org/docs/18/sql-set-transaction.html). | Record separate repeatable-read cutoffs, use deterministic source facts, never apply a new admission at an old knowledge cutoff. Read-only EXPLAIN is permitted; destructive/profile mutations belong in an isolated restore. |

Research confidence is high for code paths, B1/B2 counts, Scottish country/tiers
and the existence of the listed historical source leads. It is conditional for
unproved native-ID/club-continuity relationships, exact acquisition yield and
which optimized fanout plan will meet existing deadlines. Multiple search paths
were used for Scotland, Bangladesh, Vietnam and Indonesia. Missing direct BFF
match/ID evidence and provider entitlements remain gaps, not exhausted research.
Flashscore/Soccerway share Livesport ownership under the existing access register;
they do not count as two independent confirmations. No new identity library is
recommended: the missing pieces are exact evidence and compatibility in existing
owners, not fuzzy matching capability.

## 6. Distinct issue inventory

Severity describes integrity risk; priority describes execution order. P0 means
blocking integrity/phase control, not authorization for emergency mutations.
`READY` qualifies engineering work with defined tests, not unproved data actions.
`RESEARCH`, `EXTERNAL`, `DEPENDENT` and `OWNER` remain explicit constraints.

| ID | Root cause / later task | Severity / priority | Readiness | Target relationship |
| --- | --- | --- | --- | --- |
| FR-001 | Old Ghana participant UUIDs no longer reach admitted current mappings | High / P1 | RESEARCH; reconstruction compatibility required | 30 original targets, conditional |
| FR-002 | Unqualified native target relationships outside Ghana | High / P1 | RESEARCH for proof; existing review workflow reusable | 18 current targets, including five history-sufficient |
| FR-003 | Retained results fail dated identity/history qualification | High / P1 | DEPENDENT on exact failed predicates and FR-001/002 where applicable | 26 history-only + 15 identity-blocked targets, overlapping other issues |
| FR-004 | Current identities have too little retained eligible history | High / P1 | RESEARCH / EXTERNAL by provider scope | 122 history-only + 28 identity-blocked targets |
| FR-005 | Corrected Scottish parser and stale historical World identities disagree | Critical / P1 | READY for bounded revalidation tooling; relationships remain RESEARCH | 41 mappings, three competition scopes; forecast gain unproved |
| FR-006 | Competition admission cannot finish downstream enqueue within deadline | High / P1 | READY for isolated profiling and minimal optimization | DED/PD/BSA; no measured target unlock |
| FR-007 | Rolling CSV row positions are reused as provider match identifiers | Critical / P1 | READY for red regression; ingestion compatibility design required | 730 conflict records over ten snapshots |
| FR-008 | Authentic incoming results collide with canonical fixture identity | High / P2 | RESEARCH for exact fixture proof | Two Málaga native results; rejected Coventry season; 151 archive conflicts |
| FR-009 | Retained provider observations lack season/exact fixture reconciliation | High / P2 | READY for scoped metadata replay diagnostics; admission DEPENDENT | Latest unmatched FINISHED IDs: FotMob 9,576 / PitchAPI 1,508 |
| FR-010 | History scopes mix missing evidence, deterministic errors, quotas and live deferral | High / P2 | READY for bounded operational diagnosis; acquisition scope-dependent | 1,224 native scopes, 643 legacy queue rows |
| FR-011 | Unverifiable registered originals and published manifests | Critical / P1 | EXTERNAL for authentic bytes; lifecycle disposition OWNER where needed | 33 suspect raw registrations, 22 missing dataset manifests; 26 model manifests (18 artifact links across 13 forecasts) |
| FR-012 | Required full-production Architecture V2 comparisons do not exist/pass | Critical / P1 for rollout | DEPENDENT; cutover OWNER | Five reports, 11 comparison groups; no direct forecast gain |
| FR-013 | Derived report work remains substantially behind current data | Medium / P2 | READY for existing bounded worker; performance change only after profiling | 148,095 context generations at B1; seven performance rows |
| FR-014 | StatsBomb legacy origins lack supported method and independent target proof | High / P2 | DEPENDENT on PR #178; RESEARCH for relationships | 21 legacy mappings, not new baseline targets |
| FR-015 | Broader markets lack qualified source/player/settlement inputs | High / P3 | RESEARCH / EXTERNAL; scientific release OWNER | Existing 53 data-collection / 14 player-data diagnostic families |
| FR-016 | Quarantined fixtures and conflicting results require source-specific resolution | Critical / P2 | RESEARCH; retain exclusion until proven | 2,686 ambiguous and 11,806 impossible-schedule member decisions |

Every original/current verified target is assigned in Appendix A. Secondary
causes may remain after the first cause is resolved. An issue is not complete
merely because its diagnostic status or queue becomes empty.

## 7. Detailed implementation specifications

All specifications describe **later authorized work**. Each must start with a
fresh, frozen affected-ID inventory and finish with a separate verified commit.
Use Appendix A for target IDs and Appendix B for mapping/source inventories.
Shared verification requirements in section 10 apply in addition to the explicit
criteria below. Do not turn evidence collection into an unreviewed operating fix.

### FR-001 — Reconstruct Ghana fixtures stranded on replaced team mappings

**Identification.** High severity, P1; identity/history; RESEARCH for exact old/new
relationship proof, then DEPENDENT implementation. Thirty original Ghana targets
are listed as FR-001 in Appendix A. Section 3 gives both generations of team UUIDs,
native IDs and mapping closure times. This is systemic participant reconciliation,
not thirty unrelated missing-history fixes.

**Problem and evidence.** Current native mappings qualify against new UUIDs while
old scheduled fixtures do not reach them. There are 210 retained results involving
old Medeama and six involving old Port City; these participant counts are not
added into a distinct-match total. The dated functions return the old participant when no unique effective
admitted identity exists. Provider acquisition alone cannot update that chain.
R3 supports club participation; it does not independently authorize a UUID merge.
Fresh current-mapping verification is recorded in the final receipt. Confidence
in the mismatch is high; sufficiency of every old-to-new relationship is unproved.

**Preferred solution and alternatives.** Preserve stored football facts and all
old decisions. Reuse the existing linked correction fields
`corrects_decision_id`/`target_mapping_id`, dated effective-identity functions,
review events and recovery queues where a narrowly defined same-native-ID
reconstruction can be qualified. First prove the original and replacement native
IDs in their exact source/season context. A direct native-history import is a
valid alternative where it yields history on the accepted identity, but does not
by itself repair old scheduled participants. Reject bulk UUID replacement,
re-admission of revoked rows and a generic origin allowlist expansion.

**Implementation sequence.**

1. Freeze the 30 targets, their match mappings, old/new team mapping IDs and all
   dated decisions. Verify both source registrations and actual fixture participants;
   explicitly check native-ID reuse, country, senior status and club continuity.
2. Characterize the existing correction rejection with a failing isolated test.
   Add only the missing proof-backed compatibility case to the existing identity
   owner after its evidence prerequisite is met. Keep the FDO-specific path intact.
3. Bind the review to exact source hashes, original decision and target mapping.
   Append a prospective correction and use existing scoped history/fixture recovery;
   do not edit old participant facts or republish existing forecasts.
4. Reconstruct eligible history on both sides and rerun the unchanged champion
   preview. Acquire additional Port City history through FR-004 if still short.

**Verification and acceptance.** Extend `test_team_identity_correction.py`,
`test_product_identity_admission.py` and `test_resolution_recovery.py` under
`tests/integration/`: old-cutoff ID/history hashes unchanged; wrong native ID,
senior/youth mismatch, reused ID, missing bytes and conflicting targets rejected;
retry event/work IDs stable; revocation removes future eligibility; concurrent
correction/recovery respects existing ordered locks. Acceptance requires all 30
targets individually dispositioned with exact remaining causes, not all declared
available. **Impact:** up to 30 target records conditional on identity/history;
zero guaranteed new forecasts. **Risks:** admission fanout FR-006, lost old-cutoff
meaning, false club continuity. No migration is presumed; justify one only if
existing linked fields cannot represent the proven case.

### FR-002 — Complete exact native relationship evidence for other target identities

**Identification.** High, P1; provider identity; RESEARCH. Eighteen B1 targets
outside Ghana fail `fixture_identity_blockers`; five already satisfy history,
while thirteen also need history. Exact fixtures/native IDs are in Appendix A.

**Problem and evidence.** Current provider-derived targets require admitted home,
away and competition mappings for their source provider. Large canonical history
under the same displayed name cannot establish that link. Fresh verification of
English API-Football mappings including `37`, `61`, `1339` and `1349` fails the
explicit-crosswalk/context requirement. R1/R3/R5/R12 supply research methods and
context, not missing native relationship assertions. Confidence is high in the
failed predicate; specific data approvals remain unproved.

**Solution and steps.** Begin with the five history-sufficient fixtures in section
3. Use `mapping_detail`, `mapping_candidates` and `qualify_operation` in the
existing Resolution Center. Trace each native match to its original payload and
both team IDs, then to the accepted counterpart through an exact fixture/season
proof. Distinguish unavailable proof from an actually incorrect crosswalk. Use
existing `APPROVE`/fixture review only if the preview qualifies; otherwise retain
RESEARCH. Extend correction compatibility only if a proven relationship fails a
specific existing contract, following FR-001 rather than adding a competing
review path. Recheck all mappings for the source provider, since its aggregate
qualification can fail despite a different provider's valid history.

**Verification and acceptance.** Existing identity/decision/recovery integration
suites must reject name-only, confidence-only, wrong home/away, reserve/women's
substitution, missing raw bytes and stale evidence versions. Five candidate
fixtures must pass exact identities and the unchanged forecast preview before
claiming five potential unlocks; all eighteen receive a final per-target cause.
No new migration or library is expected for ordinary qualified reviews.
**Impact:** zero proven gains; up to five require identity alone, thirteen require
additional history. **Risks/dependencies:** FR-003/004 and source independence.
No owner decision is needed merely to research or prepare a qualified preview.

### FR-003 — Recover retained results by the exact failed eligibility predicate

**Identification.** High, P1; dated history; DEPENDENT. Twenty-six history-only
B1 targets have at least ten retained rows per side; fifteen identity-blocked
ones share that retained-sufficiency condition. These populations are disjoint
from FR-004's raw-deficient group but overlap FR-001/002.

**Problem and evidence.** Retained counts overstate model inputs. Examples are
Mainz women 10/7, Cannes 11/4, Rudes 50/9, Da Nang 73/5 and Fakirerpool 16/3
(retained/eligible). Existing `product_match_history_decisions` and
`product_eligible_history_at` are authoritative. A generic
`ProductIdentityTrustV1` reason does not identify which team, competition, source
or fixture predicate failed. R8/R11/R12 offer factual leads, not blanket admission.

**Solution and steps.** For each deficient team in Appendix A, export its exact
retained fixture/source IDs and latest decisions at a frozen cutoff. Evaluate
existing source validation, team/competition admission, effective participants,
fixture representative/quarantine and source-known predicates separately.
Group identical failed upstream mappings; address them once through the existing
owner. Reuse `record_product_history_decisions` only for affected fixture IDs
after a valid prospective change; use the existing source replay for missing
imports. Do not add a second eligibility engine or flip `eligible` directly.
Existing diagnostics may be extended to expose the failing existing predicates
and bound evidence, rather than inventing a replacement contract.

**Verification and acceptance.** Extend `test_history_diagnostics_api.py`,
`test_product_identity_admission.py` and recovery suites: one missing predicate
keeps the row excluded; non-played/unknown score basis stays excluded; date-only
same-day, same-kickoff, future source knowledge and target fixture are excluded.
Before/after fixture-ID sets and hashes must match at the earlier cutoff, and
new eligible rows must each resolve exact source and admission lineage. Report
all 41 target records without double-counting identity work. **Impact:** 26
history-only candidates plus fifteen dependent records, with no assured yield.
**Risks:** stale admissions and FR-005/006/016; no schema change is assumed.

### FR-004 — Acquire genuinely missing eligible history, scoped to current teams

**Identification.** High, P1; acquisition/coverage; RESEARCH or EXTERNAL per
provider. At least one current participant has fewer than ten retained results
in 122 history-only targets and 28 identity-blocked targets. Their current
identity scopes cannot meet the minimum by reclassifying existing rows alone.

**Problem and research.** Garudayaksa has nine retained/five eligible rows across
ten targets; Bắc Ninh six/three across four; Dhaka Wanderers nine/two across six;
City Club four/four across four. Other youth, reserve, women's, promoted and
small-league teams occur in Appendix A. R4/R6/R7/R9–R12 identify coverage leads.
The official Garudayaksa 27-match table establishes prior senior participation,
not 27 already importable match records. VPF identifies earlier Bắc Ninh fixtures.
Bangladesh season labels remain contradictory across public reports.

**Preferred approach.** Reuse existing provider-specific acquisition, immutable
manifests and historical importers. Prefer exact native history from an already
supported provider over a new scraped dataset or speculative cross-provider
correction. First inspect retained resources and season lists; then request only
the missing eligible team/season slices within existing entitlements. Where an
official source has no supported adapter, first prepare exact dated match evidence
and a minimal native-resource/parser specification; do not introduce a general
scraper. Preserve source-only facts until identity and regulation-score semantics
qualify. Scope any new adapter/migration as a separate reviewed implementation.

**Steps and acceptance.** Freeze deficient team IDs/counts; verify exact senior,
reserve, age/gender and season; exhaust retained eligible native resources;
perform bounded permitted acquisition and source registration; dry-run parsing,
identity and import in an isolated restore; only then run authorized scoped
recovery. Test partial/empty seasons, plan denial, 429, corrupt payloads,
unknown enums, timezone/date-only values, same-batch exclusion and duplicate
replay. A completed scope must bind its full expected native-ID list and explain
omissions; ten rows cannot be fabricated from a season total. **Impact:** up to
150 target records conditional on qualification, overlapping FR-001/002; no
new competition count is established. **Risks:** paid/unsupported coverage,
source rights, FR-009/010 and historically unknown facts. Keep each denied scope
explicitly blocked while independent work proceeds.

### FR-005 — Reconcile Scottish World namespaces without rewriting history

**Identification.** Critical integrity risk, P1; parsing/identity; READY for a
bounded revalidation census, RESEARCH for relationships and ambiguous succession.
Forty-one active World mappings and three competition scopes are identified in
Appendix B; the original 30 are the 2000/01 archive participants in section 3.

**Problem and root cause.** The fixed `_DIVISIONS` entries change fresh source
country/tier interpretation, but prior admitted country-dependent origin UUIDs
remain World. `origin_id` includes country for Football-Data.co.uk, so changing
a product country alone would create UUID mismatch rather than correct lineage.
All 41 fresh checks fail while stored decisions say ORIGIN_ANCHOR. R1 validates
participation; R2 shows why Airdrie/Clydebank and similar successors cannot be
collapsed. Confidence is high in namespace failure, conditional in successor links.

**Implementation.** Preserve original CSV bytes, parsed identifiers, decisions
and IDs. Inventory every retained SC1/2/3 source and all affected aliases/periods,
not only the first archive. Revalidate each current mapping with the corrected
parser and record prospective invalidation through the existing admission owner
only after its downstream consequences are rehearsed. For verified same-club
relationships, use an explicitly supported linked correction/reconstruction to
Scotland-scoped identities; characterize the current FDO-only rejection first.
Keep Airdrie (pre-2002), Airdrie United, historical/new Clydebank, Gretna and
ambiguous aliases separate until exact period/continuity proof qualifies.
Reconcile dependent fixtures/history before admitting more competition scope.
Do not revoke the newly admitted SC2 or assume its 5,137 rows are all defective.

**Acceptance.** Existing parser, admission, correction and recovery suites cover
all three codes; original30 and expanded41 inventories; old cutoff unchanged;
wrong-country and tampered ZIP rejection; alias collisions and succession
negative tests; dated revocation/retry behavior; no leaked same-day date-only
history. Freeze all SC2 eligible IDs and verify any later exclusions/additions
individually. Scope completion requires every affected mapping disposition and
no unsupported automatic merge. **Impact:** 540 original source rows are an
investigation cohort, not promised new history; later archives overlap and
current forecast gain is unmeasured. **Dependencies/risks:** FR-006 and exact
identity policy; coordinate any required additive migration with PR #178.

### FR-006 — Remove excessive admission-to-refresh fanout

**Identification.** High, P1; SQL/recovery concurrency; READY for isolated profiling.
FDO DED/PD/BSA source-backed competition admissions previously rolled back during
downstream enqueue; eight other native competition mappings are currently present.

**Root cause and research.** The deployed `record_product_admission_change`
requalifies a competition's retained history. Each inserted history decision can
call `enqueue_product_context_for_history`, scanning future targets and resolving
effective participants. Prior receipts establish deadline failure; deployed SQL
establishes repeated fanout. They do not identify the exact expensive plan node.
R13 supports statement-level transition relations; R14 preserves transaction
and visibility requirements. This distinction avoids optimizing an assumed cause.

**Implementation sequence.** Restore the latest approved populated snapshot into
a disposable database with operating isolation checked. Reproduce DED/PD/BSA
admission under the existing deadline and capture query/lock plans and affected
refresh keys. Compare a scoped set-based writer with `AFTER INSERT` transition
relations. Prefer the smallest plan that deduplicates refresh keys across one
history statement and uses existing queue functions, ordered locks and generation
increments. Keep qualification and durable invalidation atomic; do not move
synchronous eligibility off-thread without a separately reviewed consistency
contract. Introduce a new additive SQL migration only after checking current PR
migration order; never edit accepted migrations.

**Tests and acceptance.** Extend admission, public-report and recovery integration
suites with representative DED/PD/BSA-sized cohorts, concurrent history writes,
revocation, lease loss, retry and a target requested while a worker completes.
Require unchanged eligible decision set, exact required refresh-key set, no lost
pending generation, bounded memory/locks and completion within the unchanged
existing deadline on the same populated restore. Publish before/after timings
and plans; a higher timeout is not acceptance. **Impact:** three admission scopes
potentially recoverable; numerical history/forecast yield must be measured, not
assumed. **Dependencies:** none for profiling; identity/source proof before actual
admission. **Risk:** lost invalidation or reversed lock ordering.

### FR-007 — Stop treating rolling CSV row positions as stable match identity

**Identification.** Critical, P1; Football-Data.co.uk parsing/ingestion compatibility;
READY for a failing regression and contract design. There are 730 recorded
provider-ID reuse conflicts over ten snapshots; Appendix B gives query/inventory
references. These may include repeated observations of the same real fixture.

**Root cause.** `parse_csv_resource` builds `source_path#row_number`. Replacing or
reordering `Latest_Results.csv` makes the same provider key describe a different
match. The canonical guard correctly preserves the old mapping. This is not
missing team-name matching or a reason to relax uniqueness. R6 establishes the
alternative of pinned seasonal resources where available; existing immutable
source/snapshot contracts supply the correct occurrence context.

**Solution and steps.** Reproduce with two retained-style rolling responses whose
row 2 changes or moves. Inventory every consumer and uniqueness constraint of
`provider_match_id` in `historical_backfill`, `match_provider_mappings`, fixture
identity evidence and source observations. Prefer immutable season files for
ordinary backfill. For rolling inputs, keep original row keys as source occurrence
identifiers bound to snapshot/resource/version, and resolve the real fixture
through existing exact participant/date/competition evidence. Never reinterpret
or rewrite an already published old row ID. If the current registration contract
cannot distinguish source occurrences, document the necessary additive mapping
compatibility before implementing it; a new opaque ID format alone is insufficient.

**Acceptance.** Tests cover row insertion/reordering, corrected scores on the
same match, a new match at the old row number, reversed orientation, same-team
schedule collision and identical-byte retry. Old mappings, decision history,
source hashes and earlier-cutoff forecasts remain unchanged. Each of the 730
conflict records receives either an exact resolved occurrence or a reason it
remains held; deduplicate real matches before reporting recovery. **Impact:**
unknown number of distinct results; zero measured target unlocks. **Risks:**
cross-module ID compatibility and FR-008/016; do not globally change all archive
keys or add fuzzy fixture identity.

### FR-008 — Resolve canonical team/timestamp collisions from exact original rows

**Identification.** High, P2; fixture reconciliation; RESEARCH. Two rejected
API-Football Málaga rows (`1217677`, `1217899`), the unimported 46-row Coventry
season and 151 Football-Data.co.uk team/timestamp conflict records are explicit
cohorts; they are not assumed to share one factual resolution.

**Root cause and evidence.** `guard_product_history_fixture_identity` refuses an
incoming representation inconsistent with retained team/kickoff identity.
The prior shadow attempt rolled back; current observations contain neither
rejected Málaga native ID. Section 3 and Appendix B bind source snapshots/hashes.
The guard is functioning, while the exact real-fixture representative or time
precision remains unresolved. R5/R6/R14 support native source and dated comparison;
public name agreement does not establish a duplicate.

**Steps.** Read each rejected original row; retrieve every existing participant,
kickoff claim, match mapping, source result and active fixture resolution in its
bounded neighborhood. Classify true duplicate, reschedule, date-only overlap,
wrong competition/orientation, source correction or contradictory source.
Use existing `RESOLVE_DUPLICATE`, `fixture_identity_resolutions` and canonical
resource resolution only when their proofs qualify; keep both source records.
Replay the retained rejected row through its original importer after the linked
resolution, since no stored operational observation exists to replay. Do not
expand the kickoff tolerance or replace a stable canonical fixture ID.

**Acceptance.** Extend historical-backfill, operational-sync and resolution
integration tests for exact/date-only collisions, conflicting scores, wrong
orientation, retries and old-cutoff reconstruction. Each accepted row must map
to a verified unique representative and source; unresolved rows stay quarantined.
Report two Málaga outcomes and the exact accepted/rejected Coventry subset.
**Impact:** at most two additional Málaga native observations in that named
subset, not two new forecasts; broader yield is unmeasured. **Dependencies:**
FR-001/002/007 if an identity or rolling-ID defect is found. No new schema is
presumed; independent source proof remains the main limitation.

### FR-009 — Replay exact season metadata and current unresolved observations

**Identification.** High, P2; operational normalization/reconciliation; READY for
bounded diagnostics and proven metadata replay; data admission is DEPENDENT.
Latest-observation-only unmatched FINISHED counts are 9,576 FotMob and 1,508
PitchAPI, while historical revision counts are larger.

**Root cause.** `_usable_provider_season_label` cannot create a valid fixture
when season metadata is absent, and `_record_failed_observation` preserves the
failure rather than fabricating a season. Other rows lack exact canonical
candidates or contradict admitted mappings. A latest decision may say matched
while an old unmatched observation remains immutable. R7 and the native season
catalogues are the evidence route; source-name/date inference is not.

**Implementation.** Build a deterministic inventory keyed by provider/native
match, latest observation and current resolution state. Exclude already-resolved
historical revisions from active recovery. Group by missing metadata versus
identity/canonical/score failures. For missing seasons, recover the exact retained
league-season response/checkpoint and bind its resource, native competition,
season and participant scope through existing replay code. If authentic metadata
is absent, acquire that bounded resource through the existing adapter. Never use
current season as a historical fallback. Reuse `prepare_targets`, bounded recovery
pages and existing importer owners once evidence qualifies.

**Acceptance.** Extend operational-sync, provider-work and history-diagnostics
suites: missing/unknown and conflicting season remain explicit; valid stored
season replay produces the same IDs on retry; old unmatched revisions remain
unchanged; one native ID counts once; no relabeled LIVE/CANCELLED result becomes
a played label. Prove full source-to-history lineage for each recovered row and
rerun only affected target previews. **Impact:** 11,084 latest finished native
IDs are a diagnostic maximum, not distinct new canonical matches or forecast
promises. **Risks/dependencies:** FR-001/002/008/016; partial source seasons must
remain partial. No new registry or generic replay engine is needed.

### FR-010 — Treat scope failures, quotas and live-priority deferrals separately

**Identification.** High, P2; work orchestration/acquisition; READY for scoped
operational diagnosis, DEPENDENT for identity/source cases. B1 has 1,224 native
scopes and 643 legacy queue rows, with exact state/error groups in section 3.

**Problem and research.** Only two native scopes are SUCCEEDED; most pending
work is not ready-to-run valid history. `BLOCKED_IDENTITY`, failed retained-row
replay, unavailable native lists, 429, quota exhaustion and
`LIVE_SYNC_HAS_PRIORITY` require different actions. R4/R5/R7 confirm provider
coverage and rate-limit constraints. A status rename or broad retry cannot
satisfy missing proof, and deliberately live-first scheduling is not by itself
a scheduler defect. Starvation duration must be measured before changing policy.

**Steps.** Inspect `provider_history_scopes`, `history_work`, `history_worker` and
`history_requests` for each current queue key. Bind shared work IDs, due times,
last source/checkpoint and exact error classification. Replay proven retained
rows offline first; retry transport/quota failures only at existing deadlines;
leave deterministic identity failures held under the existing classification.
Measure deferral age and safe available capacity in an isolated workload. Add a
bounded fairness change only if reproducible starvation violates the current
policy, retaining live priority and persistent quotas. Mark SUCCEEDED only when
native expected-ID coverage and import receipts prove completion.

**Acceptance.** Existing history acquisition/queue/provider-work integration
suites cover lease expiry, old worker fencing, crash before/after import,
partial-season completion, cancellation, deterministic held failures and repeated
429/deferral. Retry must converge to one import without busy-looping or quota
bypass. Measure queue age/completed scopes separately from retrieved/eligible
rows and forecasts. **Impact:** no numerical forecast gain can be attributed to
queue draining alone. **Dependencies:** FR-006/008/009 and source proof.
**Risk:** starving live sync or falsely completing partial scopes; no new scheduler
or broad runtime cutover is recommended.

### FR-011 — Restore exact missing originals or retain honest lifecycle blockers

**Identification.** Critical, P1; source/artifact integrity; EXTERNAL for missing
bytes and OWNER for any new lifecycle disposition. Current checks find 33 suspect
raw registrations still BLOCKED through the legacy-aware verifier, 22 missing
manifests among 24 datasets, and 26 missing manifests among 5,230 model
registrations. The models have 18 artifact links across thirteen baseline
forecasts. Appendix B records exact IDs and paths.

**Root cause and limits.** Registrations include repeated placeholder-shaped
checksums and historic test lineage. A published registration is not proof of
physical bytes or safe current dependency. Earlier evidence says the thirteen
forecasts were already retired; this investigation rechecks the dependency IDs
and missing manifests, not every retirement event or all 5,204 other models.
The Scottish ZIP is verified present through its registered legacy path and is
explicitly excluded. R14 and existing immutable file contracts govern restoration.

**Steps.** Use `resolution_data.resource_check`, `PostgresIntegrityVerifier`,
`resolution_files.recovery_plan` and `publish_file`. Search registered paths and
known backups for exact matching bytes; validate hash, size, manifest and complete
input lineage in an isolated restore. Restore only bytes that match the original
registration. If absent, acquire authentic replacement data as a new source and
build a new dataset/artifact only under separately authorized build contracts.
Keep the original failed registration and append the existing exclusion/retirement
or unresolved disposition as appropriate; never replace the expected checksum,
forge a manifest or delete old registrations to make parity green.

**Acceptance.** File-recovery and integrity integration suites reject wrong
bytes, symlinks/path escape, partial publication, stale lease and conflicting
recovery requests; exact retry converges. Every candidate receives a hash-backed
restore or explicit absent-original outcome, with all active dependency checks
performed before operational claims. All unchanged models/forecasts remain
byte-identical. **Impact:** integrity/parity recovery; no current target unlock
has been proved. **Risks:** historical synthetic test records can remain global
gate blockers even when unreachable; only the owner can approve a necessary new
lifecycle policy, and that policy must not weaken frozen scientific evidence.

### FR-012 — Complete full-scope parity evidence rather than rerunning five reports

**Identification.** Critical for rollout, P1; Architecture V2 verification;
DEPENDENT on upstream source/identity/coverage fixes, OWNER for cutover. Five
report IDs and all eleven failing/unrun contract groups are listed in section 4.

**Root cause.** `migration_report` consumes frozen tracked comparison evidence;
`verify_parity` refreshes diagnostics and checks retained hashes. Neither executes
all missing production comparisons. The worker may succeed while
`overall_status` correctly stays BLOCKED. Existing tables and LEGACY stage routes
show this is no longer an absent-parity-table problem. R14 supports stable
comparisons; complete-runtime parity must follow the repository's existing
Phase 35 contracts, not a new smaller acceptance universe.

**Steps.** Disposition every retained difference and bind fresh accepted evidence
for acquisition, parsing, identity, canonical state, coverage/quality, serving,
API, feature inputs and work ownership. Execute the three previously NOT_RUN
history/report/artifact-routing comparisons over the complete required scopes in
an isolated populated runtime. Use existing migration evidence builders and
tracked receipts with exact Git/lock/source hashes. Recheck all eleven groups;
then run the existing Phase 35 readiness gate. An accepted narrow forecast-data
fix does not itself authorize that programme's later phases.

**Acceptance.** Existing parity gate/integration/stage suites must preserve
BLOCKED for incomplete scopes, missing bytes, wrong evidence hash, unresolved
identity, stale database identity and retained arithmetic changes. Require the
full required group set with `required_runtime_scopes_complete=true`, all
original thresholds, individually explained differences, and the existing gate's
actual result. Do not relabel 59 Elo or 327 retained history exceptions as fixed
using current target counts. **Impact:** rollout readiness only; zero direct new
forecasts demonstrated. **Risks:** stale evidence, scope shrinkage and premature
cutover; FR-011 missing authentic bytes may remain a real external blocker.

### FR-013 — Finish bounded report generations and measure remaining throughput

**Identification.** Medium, P2; derived reports/operations; READY for existing
bounded workers, performance changes conditional on measurements. B1 has 148,095
pending context rows, seven performance rows and zero comparison rows, with no
recorded errors in these queues.

**Root cause and evidence.** The backlog is persisted requested generations not
yet projected; it is not evidence that football history or forecasts are missing.
[`public_reports.py`](../../python/football/src/football/product/public_reports.py),
existing report scheduling and generation-aware work own publication. The
admission/history fanout in FR-006 can keep requesting new generations. R13
informs deduplication, but a global bulk update is not safe completion.

**Steps.** Freeze report kind, scope, requested generation and oldest age. Measure
arrival/completion rate, runtime and representative slow queries. Reuse existing
bounded CLI/worker processing with current lease/generation checks; prioritize
relevant target scopes within existing scheduling. Inspect genuinely failing
items separately from merely pending ones. Optimize only measured query/fanout
hotspots. Do not set completed generations manually or add another report queue.

**Acceptance.** Extend existing public-report and recovery suites for a new
request during projection, rollback, retry, stale lease, missing football data
and shutdown between pages. A frozen generation cohort reaches completion or
has an exact blocker, and fresh public detail/list/history reports agree with
source hashes and availability. Report new arrivals separately from backlog
burn-down. **Impact:** fresher diagnostics and consumer reports; zero forecast
gain should be attributed without a separately changed eligible input.
**Risks/dependencies:** FR-006, query pressure and concurrent background work;
no migration is expected for use of existing workers.

### FR-014 — Keep StatsBomb recurrence prevention separate from legacy recovery

**Identification.** High, P2; canonical identity/V4; DEPENDENT on PR #178,
RESEARCH for independent relationships. Twenty-one legacy team/competition
mappings and their 380-fixture competition chain remain blocked under that PR's
pinned evidence. Those are not 380 newly forecastable operating targets.

**Root cause and research.** The original StatsBomb writer allocated UUIDv7 IDs
but labeled native mappings deterministic. PR #178 uses `provider_native` for new
rows and preserves old ones; it implements no proof-free correction. Its pinned
[identity report](https://github.com/sir-radar/match-forge/blob/463ec15a8a0720fb48e842af5a009cf140545f90/docs/V4_IDENTITY_ADMISSION_RECOVERY_REPORT.md)
was inspected. [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html#name-uuid-version-7)
does not make a generated UUID a provider-derived origin. [Reep's coverage](https://reep.football/coverage/)
distinguishes bridge-only IDs and shared feeds; its pinned release's failed
quality gate cannot be replaced with present website advertising. A fresh
[StatsBomb repository](https://github.com/hudl/open-data) read confirms the public
resource route, not the missing cross-provider relationship.

**Steps.** Coordinate PR #178 migration/writer order and final source revision;
do not duplicate or cherry-pick an incomplete correction design into this branch.
Obtain one exact independently verifiable legacy-source-to-accepted-target
relationship, including competition, season, senior/gender, native IDs and raw
hashes. Only then specify the minimum missing prospective team or competition
correction in its existing owner. Team and competition semantics must remain
separate. Extend the proven case incrementally; preserve the five-fixture NPFL
research-only pilot and keep unproved mappings blocked.

**Acceptance.** Reuse that PR's native-ID, correction, review and historical
boundary regressions: no old UUID/method/source history rewrite, wrong or
same-feed evidence rejected, old-cutoff identity unchanged, revoked relationship
excluded and idempotent corrected replay. Actual legacy recovery requires a
positive qualified case, not only recurrence tests. **Impact:** no baseline
forecast gain established; player appearances/minutes and model sufficiency
remain unqualified. **Risks:** method honesty being mistaken for admission,
unsupported origin allowlists and unauthorized V4/scientific continuation.

### FR-015 — Qualify source and player inputs before claiming broader market readiness

**Identification.** High, P3; market/source/model qualification; RESEARCH/EXTERNAL,
with scientific release OWNER. The previously recorded bounded diagnostic has
53 DATA_COLLECTION_REQUIRED and fourteen INSUFFICIENT_PLAYER_DATA families.
These are retained diagnostic counts, not a fresh global market census or 67
missing baseline goal forecasts.

**Root cause and research.** Fixture/result history cannot establish player
exposure, appearances, injury knowledge, event semantics or bookmaker settlement
rules. PR #178's five-fixture/ten-goal-label research pilot remains a bounded
source/target qualification. R4/R6/R7 and the StatsBomb resource documentation
show materially different provider capabilities. More results from OpenFootball
cannot manufacture player/event features; a prediction API does not qualify
baseline features or a frozen evaluation.

**Steps.** Reuse current capability/observation/market diagnostics from the V4
branch and explicit required-input definitions. For each family, freeze target
scope, provider semantics, identity, coverage, football/knowledge cutoffs and
settlement-equivalence requirements. Acquire only missing supported input types,
retain unknown minutes/exposure as unknown, and rerun data qualification in an
isolated experiment. Design/model/evaluation work requires the programme's
separate authorized scientific stage after data acceptance; do not fold it into
this remediation roadmap as an automatic next phase.

**Acceptance.** Existing native observation, coverage and market-diagnostic tests
must distinguish missing, unsupported, research-compatible and accepted inputs.
Require exact player identities/participation, prior knowledge, complete declared
coverage and source-equivalent outcomes before changing a market's readiness.
One coherent joint goal distribution and immutable raw probabilities remain
required. **Impact:** unquantified broader-market feasibility, no additional B1
forecast count. **Risks/dependencies:** FR-004/011/014, account entitlements and
scientific insufficiency; no new model or prediction endpoint is authorized here.

### FR-016 — Resolve quarantines and result disagreements without treating them as transport errors

**Identification.** Critical integrity risk, P2; source quality/fixture identity;
RESEARCH. B1 contains 2,686 active ambiguous-quarantined and 11,806 active
impossible-schedule-quarantined member decisions. The later quality census has
38 QUARANTINE and 2,146 WARNING findings, plus 1,845 source-result conflict rows:
1,835 FotMob/FotMob, six Football-Data.co.uk/OpenFootball, two FotMob/API-Football
and two Football-Data.co.uk self-conflicts. Counts overlap source revisions and
fixtures; they are not additive target losses.

**Root cause and evidence.** Multiple representations, revised results, period
semantics and incompatible team/kickoff evidence are deliberately excluded.
`OperationalProviderSync._insert_qualified_history` requires qualified played
scores; conflict publication preserves previous and incoming source values.
The current inventory does not prove that all conflicts are parser defects or
that latest-provider values are correct. R1/R5/R7/R12 identify official matching
context and native semantics; secondary aggregators may share a feed.

**Steps.** Prioritize conflicts in the bounded neighborhoods of B1 targets and
FR-003/008 candidates. Group by exact source pair, fixture and reason. Compare
original regulation/extra-time/penalty values, reschedule history, orientation,
team season and genuinely independent official evidence. Reuse existing
canonical resource decisions, fixture review and quarantine reprocessing only
when proof resolves the exact rule. Leave original facts and exclusions visible;
corrected data is a new observation/version, not an overwrite. Do not retry
identity/quality failures as network errors or automatically prefer the newest
source.

**Acceptance.** Extend existing operational-sync, historical-backfill, resolution
view/recovery and quality tests: impossible schedules remain held, ambiguous
candidates are not arbitrarily chosen, regulation labels never use shootout
scores, a new source correction affects only later knowledge, and retry creates
no duplicate decision. Each targeted conflict receives exact evidence and a
source-specific disposition. **Impact:** no defensible global forecast estimate;
measure only independently qualified target changes. **Risks/dependencies:**
FR-007/008, provider semantics and truly unavailable originals; no broad quarantine
release or scientific threshold change is recommended.

## 8. Prioritized backlog and dependency-aware execution roadmap

The ordering favors evidence-backed shared engineering work while exact identity
research proceeds. It does not convert any later phase into current authority.

| Execution phase | Tasks and dependency | Concrete exit evidence |
| --- | --- | --- |
| A — Freeze and prepare proof | Refresh B1 target IDs; FR-001/002 exact-source packets; FR-005 full Scottish periods/aliases; FR-003 failed-predicate inventory | Each target/mapping has a current owner, source hashes and a reproducible first cause; no approvals inferred from names |
| B — Remove shared blockers | FR-006 populated admission profiling/optimization; FR-007 rolling-resource regression and approved compatibility; qualified FR-001/002 cases only after A | Existing deadlines met, refresh-key parity and migration compatibility pass; each proof-complete case has a positive/revocation/retry test |
| C — Recover current eligible history | FR-003 and qualified FR-005; FR-008 exact fixture cases; FR-009 exact metadata replay; FR-004 targeted native acquisition with FR-010 quota/retry control | Source/fixture/identity/history lineage per accepted row; earlier-cutoff hash unchanged; no duplicates; actual target previews |
| D — Derived reporting and integrity | FR-013 bounded refresh; FR-011 authentic-byte search/restore and owner-reviewed lifecycle gaps; FR-016 scoped conflicts | Frozen report generations handled; exact file checks; all exclusions retained or explicitly qualified |
| E — Forecast-readiness verification | Re-run exact affected target prerequisites and unchanged champion previews/publication through existing owners, only when separately authorized | Unique newly available/published targets counted once; unchanged prior forecasts/artifacts; remaining causes explicit |
| F — Architecture/scientific handoff | FR-012 complete-scope programme evidence; FR-014 relationship prerequisite; FR-015 separately authorized market/scientific qualification | Existing phase gate records actual PASS/PASS_WITH_WARNINGS/FAIL and returns control to owner; no automatic cutover or later research |

Explicit dependencies: `FR-006 → large FR-001/003/005 admissions`;
`FR-007 → rolling-source subset of FR-008`;
`FR-001/002/005 → affected FR-003/009`;
`FR-004 + FR-010 → newly acquired FR-003`;
`FR-008/016 → contested history`;
`accepted history → FR-013 + target preview`;
`FR-011 + accepted upstream production scopes → FR-012`;
`independent relationship proof + PR #178 → FR-014`;
`qualified data + separate scientific authority → FR-015`.

Safe parallel opportunities for a future authorized team are evidence gathering
by independent provider/club scope, isolated FR-006 profiling, and FR-011 backup
inventory. They must not share operating mutations, schema ownership, correction
transactions or the same branch edits. This investigation uses no subagents.

Ready engineering work: FR-006 profiling/optimization with a reproduced failing
case; FR-007 regression/compatibility inventory; FR-009 current-observation and
exact-season diagnostics; FR-010 scoped work diagnosis; FR-013 existing bounded
worker execution. FR-005 revalidation census is ready, but changing 41 admissions
is dependent on a rehearsed dated correction/disposition plan. The remaining data
actions need proof, authentic bytes or an existing programme gate before they
can be called ready. No new external account, subscription or spend is recommended.

## 9. Forecast impact without double-counting

| Measurement | Defensible interpretation |
| --- | --- |
| Coventry 29 + Málaga 20 + Armenia 13 | 62 already available original targets; **zero prospective gain** from redoing them |
| Five FR-002 fixtures with sufficient eligible history | Up to five conditional unlocks after qualified native identity; none is proof-ready merely from current counts |
| Twenty-six FR-003 history-only records | Up to 26 conditional targets from retained history qualification; no promise that every retained row is scientifically admissible |
| Ghana 30 | Up to 30 conditional identity/reconstruction targets; Port City and some opponents also need history |
| Other identity-blocked thirteen | Need both identity and history; not additional to the FR-004 population |
| FR-004 raw-deficient 150 | Includes 122 history-only and 28 identity-blocked records; overlaps Ghana/FR-002 |
| Entire B1 verified blocked set | **196 unique target records is the upper ceiling for this frozen inventory**, not an expected gain |
| Provisional upcoming 3,759 | Requires separate identity/representation/coverage qualification; not counted toward the 196 or any promised recovery |
| 730 rolling-ID conflicts; 11,084 latest finished unmatched native IDs | Recovery candidates with duplication/qualification uncertainty; cannot be added to forecast counts |
| Newly available competitions | No evidence-backed number; a fixture gain within an already available competition adds zero competitions |

**Confirmed new forecasts from this investigation: zero. Guaranteed future
unlocks: zero.** A reasonable first measurement cohort is the five history-ready
identity candidates, followed by the 26 retained-history candidates and the
proof-complete Ghana cases. Prefer actual qualified gains to a speculative total.
All recovery attribution must exclude time passage and background-worker gains.

## 10. Verification and acceptance plan

### Required evidence for every later implementation task

1. Freeze exact affected fixture, mapping, source, work and artifact IDs with the
   starting code SHA, dependency lock hash, schema versions, football cutoff,
   knowledge cutoff and knowledge mode. Preserve original bytes and baseline
   history/forecast hashes. Identify whether each result is a source observation,
   canonical match, eligible history row or target forecast.
2. Write a focused failing behavior test where a defect is confirmed; retain
   real evidence failures as blocked fixtures rather than fabricate proof.
   Exercise both success and rejected branches, unchanged earlier-cutoff queries,
   same-kickoff/date-only exclusions, target-outcome absence and revoked mappings.
3. Use a disposable populated restore for database mutations, replay, profiling
   and migrations. Verify operating/shadow database identity and file root before
   connecting mutation paths; enforce read-only on all operating diagnostics.
   No broad migration or unbounded recovery command belongs in the preflight.
4. Validate idempotency, atomic rollback, concurrent corrections, request UUID
   reuse, generation changes during projection, stale leases and source tampering.
   Never bypass locks, increase acceptance deadlines, suppress checks or recast
   partial coverage as complete.
5. During development run focused existing suites for the changed owner. After
   final code changes, inspect the Makefile graph and run one applicable
   `env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATA_ROOT make check integration`
   aggregate in its disposable harness. Add relevant browser journeys only for
   changed Admin flows. Do not rerun targets already included in the aggregate.
6. Compare before/after at the same earlier cutoff (identical ID sets and hashes)
   and at the explicit later admission cutoff (only source-backed additions or
   justified prospective exclusions). Preserve prior published forecast/model
   bytes, artifact bindings, champion checksum and raw probabilities.
7. Reuse existing bounded forecast/recovery/public-report owners after separately
   authorized rollout. Confirm detail, fixture list and forecast history agree
   on actual publication/input hashes. Retry creates zero duplicates. A dry-run
   readiness result is not a published forecast.
8. Publish unique affected-target outcomes and explain all remaining blockers.
   A task passes only its defined scope; a phase/map passes only its full frozen
   acceptance conditions. Record actual PASS, PASS_WITH_WARNINGS or FAIL, commit
   before the next authorized task, and return control at programme gates.

For this prose-only investigation, repository policy requires text/reference
review and `git diff --check`, not production lint/build/test/integration runs.
Read-only SQL and existing verifier executions are investigation evidence, not
claims that future fixes pass these implementation tests.

## 11. Remaining gaps, decisions and limits

- Full exact relationship packets remain missing for the old/new Ghana
  participants, eighteen other native targets, Scottish successors/aliases and
  StatsBomb legacy mappings. Native IDs shared across revisions and official
  club participation narrow research; they do not remove club-continuity checks.
- The 26 retained-history targets need row-specific failed eligibility predicates;
  Appendix A proves shortage and retained opportunity, not a complete admissible
  replacement history. The remaining provisional/global backlog has aggregate
  and shared-root investigation, not an exhaustive per-record proof review.
- DED/PD/BSA deadline failure is established, but the exact execution-plan share
  and chosen SQL optimization need isolated profiling. No profiling mutation was
  performed in the operating database or an unverified clone.
- Missing authentic originals may exist outside this workstation. No remote
  object store, provider dashboard, paid entitlement, inaccessible private case
  packet or remote production runtime was audited. Generic repeated hashes are
  not proof of recoverable source bytes. The 5,204 physically present model
  manifests were not all logically reverified in this task.
- BFF direct historical match evidence and exact provider-season bindings remain
  incomplete despite official-document, local-name and independent-archive
  searches. Visit a new primary match register, retained season response or
  genuinely independent exact-ID source before repeating equivalent searches.
- Airdrie/Clydebank/Gretna succession may require an explicit owner identity-policy
  decision if existing rules cannot represent the proven relationship. Genuine
  missing-original lifecycle policy, new spend/access, scientific release,
  architecture cutover and retirement also remain owner decisions. Research,
  isolated characterization and routine supported implementation choices do not
  require repeated owner approval.
- No “exhaustive” claim is made for all 178,151 ineligible rows, 3,759 provisional
  upcoming records, every quarantine or every external data source. All original
  153 and current 196 verified blockers are inventoried and assigned; broad
  populations have distinct root-cause tasks and explicit next evidence actions.
- Project-status authority is unchanged: investigation completion does not mean
  forecast remediation, Architecture V2, V4, a Wayfinder map or a scientific
  phase is complete. Stop after delivering this plan; subsequent fixes need
  their own authorized tasks.

## 12. Investigation acceptance and freshness

Investigation result: **PASS_WITH_WARNINGS**. All original 153 targets and all
196 B1 verified blockers have exact fixture/native IDs, effective participant
IDs, retained/eligible counts and issue assignments. The union has 258 records:
62 previously available, 30 FR-001, eighteen FR-002, 26 FR-003 and 122 FR-004.
All five parity reports are assessed against each of eleven contract groups.
Sixteen distinct issues have implementation steps, current owners/dependencies,
verification requirements and bounded impact statements. Scope limits are in
section 11; this is not exhaustive per-record qualification of every stored row.

The final target freshness read F1 is **2026-11-03 15:21:44.955089 UTC**
(16:21:44 Africa/Lagos), snapshot `17952802:17952802:`, read-only. It finds
**190** verified upcoming blockers (142 history, 48 source-incomplete), 2,362
verified available and 3,759 provisional records. All 196 frozen B1 target
availability labels are unchanged; six no longer meet the future-kickoff query.
The falling count therefore does not demonstrate six recovered forecasts.
B1 remains the exact remediation cohort; F1 is the handoff freshness measurement.
No investigation operation changed football data or created a forecast.

A separate final source/schema read at 15:14:01 UTC verifies current Ghana
mappings as two ORIGIN_ANCHOR and two CROSSWALK. All thirteen stages remain
LEGACY. Applied recent migrations are `202610310500/600/700/800` and
`202611020200`; **`202611020100` from PR #178 is absent**. The highest migration
number alone would conceal this gap. Apply/validate that migration before its
new writer in any future authorized rollout; no migration was applied here.

Current integrity follow-up confirms 33 suspect raw resources BLOCKED and the
Scottish resource PASS using the legacy-aware owner. Twenty-two dataset
manifests and 26 model manifests remain missing. Later quality counts are
reported separately from B1. The first detailed collector's final conflict query
used nonexistent `detected_at`; prior successful results remain valid and the
separate follow-up uses the actual schema. An initial quality query used
`disposition` rather than the actual finding columns and rolled back; its
corrected read-only run completed. Failed collector attempts are retained locally;
none is counted as a passing diagnostic. No production check or future acceptance
condition was weakened to obtain these findings.

Prose review covers the task's research-completeness checklist and
[`docs/review-checklist.md`](../review-checklist.md). Local file links, stable issue
IDs, target uniqueness, cohort arithmetic, appendix-to-receipt equality, applied
migration membership and Markdown structure are checked before commit.
`python3 .local/forecast-readiness-investigation/validate_report.py` passes:
258 unique targets, sixteen issues, twelve valid local links, 41 Scottish mapping
IDs, five parity report IDs, thirteen receipt hashes and balanced Markdown fences.
`git diff --check` passes at each prose checkpoint. Production test/build
commands are intentionally omitted under AGENTS.md's documentation-only rule.
The investigation and codebase/phase/scientific status are separate: no project
phase or map is declared complete.

## Appendix A. Exact target inventory

B1 selects fixtures; B2 supplies effective participants, eligible/retained counts and identity reasons. `O` means in the original 153, `N` means an additional B1 blocker. `DONE` means already available before this investigation. Counts are eligible/retained per effective participant, not newly recovered rows. Every row records stable MatchForge UUIDs and current native match IDs; source bytes stay private.

| Fixture ID / kickoff UTC | Native match ID | Home name / effective UUID / eligible-retained | Away name / effective UUID / eligible-retained | Cohort / first issue |
| --- | --- | --- | --- | --- |
| `5a4be7e7-f56a-54f4-ab9f-74ed0f816120` / 2026-11-03 15:00:00 | api_football:1598739 | Marítimo U23 / `04be6f52-b802-5da3-9997-643040a82a20` / 0-0 | Moreirense U23 / `93833e31-b7e5-5a2d-82e8-09733e2e6085` / 0-0 | N / FR-004 |
| `64d82a8d-b470-5893-a98a-f6b4492fd4f2` / 2026-11-03 15:00:00 | api_football:1640301 | Olympic El Qanah / `672e045e-349c-5052-9263-18241a4a6adb` / 0-2 | Future FC / `1e223465-0c89-5a6a-a22e-16f7cacfb0d7` / 25-25 | N / FR-004 |
| `6f025213-84e6-5855-9fea-780fb8a4bf16` / 2026-11-03 15:00:00 | api_football:1637361 | Atlético Madrid U19 / `0d614b8f-3266-55dc-870c-ac70f4be7183` / 8-8 | Bayern München U19 / `dbbfd6a8-40fe-5d9d-aa34-48dfb5d0c061` / 33-33 | N / FR-004 |
| `802d510d-f615-560e-b5a1-80e159c69b40` / 2026-11-03 15:00:00 | api_football:1640302 | Abu Qair Semad / `54d12666-7ec5-55cc-a583-c1d44c6aa7d4` / 0-0 | Ceramica Cleopatra / `0313c15d-371b-53d4-b0fb-948533206880` / 25-25 | N / FR-004 |
| `92cd2023-edf9-5efd-abba-e5f12a507eec` / 2026-11-03 15:00:00 | api_football:1598736 | Gil Vicente U23 / `0487c8c8-4b5d-5c15-9e75-bdb709ddc078` / 28-28 | Felgueiras U23 / `f20b5a49-d9a3-5a44-8853-6f8bd1414bde` / 0-0 | N / FR-004 |
| `b1ab13ea-5138-5e31-9d98-5d86e71e299e` / 2026-11-03 15:00:00 | api_football:1637362 | Barcelona U19 / `fd4dd236-2fde-57dd-b58d-d4feed1a9eb5` / 10-10 | Aston Villa U19 / `3e624b6d-86e6-57eb-85e4-6c7800fed67b` / 8-8 | N / FR-004 |
| `da16a76e-f98f-5049-802b-6eb9d3ed03ac` / 2026-11-03 15:30:00 | api_football:1638855 | Maccabi Tel Aviv U19 / `8c83a58e-b544-5458-8c35-334bb3d6a5ab` / 0-0 | Zurich U19 / `5e319c51-6be5-5736-bf1a-5eb1e982519f` / 0-0 | N / FR-004 |
| `0b597b0b-21ea-5113-a313-3dab64dcaff8` / 2026-11-03 16:00:00 | api_football:1558552 | Jezero / `e153c9df-24b4-5572-a1e1-f3462307951c` / 73-229 | Dečić / `cee0a2c8-14c7-59c6-93f7-61b624ff49fb` / 5-5 | N / FR-004 |
| `334c3fc0-68c2-5341-a0dc-4ce8ad38632b` / 2026-11-03 16:00:00 | api_football:1629971 | Esteghlal FC / `5d658f7b-fb83-5b42-ad7d-d3ecf1be235d` / 0-0 | Al Shamal / `b135b322-4c1b-5222-a4d7-b1eddec73e3e` / 0-0 | N / FR-004 |
| `577cc243-36d8-5b64-9499-033d4d87bf09` / 2026-11-03 16:00:00 | api_football:1642277 | AEL / `af920e49-7bcd-5968-8370-fc16bfe26405` / 3-4 | Iraklis Yerolakkou / `2a763185-62a3-56aa-9e7e-d80b3a6ac180` / 0-0 | N / FR-004 |
| `667f20af-203f-5909-821e-c0aa24a24832` / 2026-11-03 16:00:00 | api_football:1630391 | Al Hussein / `b08eb992-4f9b-539f-91ac-19b7fe6c0a98` / 1-17 | Al Shorta / `87b4c43f-7620-57d6-b3b0-d866a912eb18` / 0-0 | N / FR-004 |
| `77c82ea7-65ca-5e11-8436-1ae272525240` / 2026-11-03 16:00:00 | api_football:1627352 | Petro de Luanda / `8f06f8c5-8a8f-562f-a5ca-5e13dfcb742f` / 0-0 | Desportivo Huíla / `9e9af3e7-33cd-5cc6-857d-86648b772ab4` / 0-0 | N / FR-004 |
| `d8574f71-7574-59b6-b4a7-a70ebe89f0d8` / 2026-11-03 16:00:00 | api_football:1639311 | Istra 1961 / `64883bca-9fef-5ce6-b46e-63c9e1839a9a` / 72-72 | Neretva Metković / `7cc2d3b5-27d7-5038-b40b-14dc4bd2fe1e` / 0-0 | N / FR-004 |
| `15dcdb30-8032-5418-9d08-1075c1f68fec` / 2026-11-03 16:15:00 | api_football:1648024 | SNIM / `ab1a9b81-d689-5fe4-b37c-23705c3da208` / 0-0 | Chemal / `1b03b0b7-e1d7-5689-8c4a-0fdc985c27fb` / 0-0 | N / FR-004 |
| `2edbf8b7-72e9-58b2-808e-9b1e1347a7a4` / 2026-11-03 16:30:00 | api_football:1646175 | Spartak Kostroma / `4fabc32a-7765-5172-887a-aee14fd7d086` / 23-25 | Volna Nizhegorodskaya / `29686783-aa34-564c-ac5a-94901d1893fc` / 0-0 | N / FR-004 |
| `18951c18-2ac3-558f-919c-60962cec1af5` / 2026-11-03 17:00:00 | api_football:1640479 | Lyngby / `6c03163d-104c-56a3-be7b-ebf50fe6bf5d` / 0-0 | Randers FC / `a94f237b-d6a5-5221-bff9-a88ddfa74560` / 0-0 | N / FR-004 |
| `690c3a28-3e28-5a68-80e5-d9f59c574de5` / 2026-11-03 17:00:00 | api_football:1632526 | APR / `df08ab18-ec79-55f9-bd93-77acefb8d008` / 0-0 | Gasogi United / `715e3324-b61e-5954-8b18-a46f02b0e6e8` / 0-0 | N / FR-004 |
| `b6e56b77-20ac-5a12-8ede-ed316db66ba4` / 2026-11-03 17:00:00 | api_football:1638854 | Goztepe U19 / `c7da70d5-4330-5804-a1a2-42f1f2aa3153` / 0-0 | AZ U19 / `b94c661b-a3e1-58bb-8bca-c645400d6d85` / 7-7 | N / FR-004 |
| `c2e28d7c-414a-5ddc-b278-2ac638ce0914` / 2026-11-03 17:00:00 | api_football:1642281 | Karmiotissa / `854c1d8d-e297-597c-b717-acaec2a7e322` / 1-2 | Ermis / `72a65e51-db2e-5664-912c-a9744d8391e0` / 0-0 | N / FR-004 |
| `e797e5d9-088c-5d1e-9798-6e1fb06411a7` / 2026-11-03 17:00:00 | api_football:1648166 | Mamelodi Sundowns / `0643263e-9a3f-5083-9ee6-4a541f63c0dc` / 0-0 | Golden Arrows / `edcd256b-63b8-5ed8-a07d-6290ab73af55` / 0-0 | N / FR-004 |
| `f9854844-ba3d-5d8e-a9ff-efd854d41d05` / 2026-11-03 17:00:00 | api_football:1647645 | AS Celtas W / `91653c6c-b052-57a6-a56e-25188a9d9f14` / 0-0 | Espanyol W / `c141f136-595c-5772-871f-854e7cafd3ef` / 30-30 | N / FR-004 |
| `04851fba-1382-5c38-9c5a-99d2886e0937` / 2026-11-03 18:00:00 | api_football:1644336 | Anaitasuna / `5ee3f67d-331d-5da5-b0e0-77463fe37c55` / 0-0 | Alaves / `632b481c-686b-50b2-99f0-06fc36385129` / 15-17 | N / FR-004 |
| `065d8ded-3b9e-5380-be27-79324b5355b8` / 2026-11-03 18:00:00 | api_football:1612155 | Lanús Res. / `6b548708-11fa-54d6-a942-7dc0ac0741f0` / 1-1 | Atl. Rafaela 2 / `b789f546-960d-5595-8550-bba6238b6bc6` / 2-2 | N / FR-004 |
| `0e7f724a-6894-5599-a8f6-6f30c7f8dec8` / 2026-11-03 18:00:00 | api_football:1644365 | Pamplona / `f56ab7c6-d7d0-5c24-9d1f-bf8ad528cca8` / 34-34 | Eibar / `0fa7b973-87d3-51ff-b602-0d8d42ab8c0b` / 963-1032 | N / FR-002 |
| `1a510a01-dd65-5f9a-99ba-ba52dd905a47` / 2026-11-03 18:00:00 | api_football:1612160 | Sarmiento Res. / `fb9e65b3-11f1-5328-9ead-aa4fd95142f2` / 0-0 | Banfield Res. / `e3c750e6-1ca2-5a7a-a51c-f8c4ab798ead` / 1-1 | N / FR-004 |
| `24f081ca-ae29-5328-a089-9a2a3878b202` / 2026-11-03 18:00:00 | api_football:1647089 | Carmópolis / `b0ffa65c-49e1-5ebd-a763-d90462980919` / 0-0 | Caninde / `c15feaa7-3bfc-5b06-ad4d-3c199e694864` / 13-13 | N / FR-004 |
| `26281652-1be6-50a7-90e8-94b2211e93bc` / 2026-11-03 18:00:00 | api_football:1494327 | Sirius / `07b1f35a-9fbf-51ff-b2c6-069bd608a0a9` / 0-2 | Halmstad / `237c5ba3-4c8b-59f3-9a77-554932d71b3b` / 52-53 | N / FR-004 |
| `4afc1d85-b319-5856-aae1-494adc5b2fb5` / 2026-11-03 18:00:00 | api_football:1645610 | NEOM / `b38d0382-8629-54c7-85eb-64320a1ad352` / 0-0 | Al-Duhail SC / `5d6f3f81-96a4-5923-9e4e-e5b5f52f4ce0` / 0-0 | N / FR-004 |
| `5bbd6652-c0c8-5f14-b63f-8c4598e6ce71` / 2026-11-03 18:00:00 | api_football:1582149 | AGF W / `966cffc6-d829-50bc-bbfd-34ba5f1097e9` / 0-0 | Midtjylland W / `213375e0-184c-5bef-8ff9-ac797666e289` / 0-0 | N / FR-004 |
| `6fc2e20a-baa6-5958-8ea1-2a28fd9cd744` / 2026-11-03 18:00:00 | api_football:1647090 | Flamengo SE / `b9fb22a9-1735-5aba-b09b-11c228805e36` / 13-13 | Olímpico SE / `7855f648-d947-5144-b9cf-a5a18b7d468b` / 0-0 | N / FR-004 |
| `7c5b0e51-939f-5f4f-9204-3f0e08253e87` / 2026-11-03 18:00:00 | api_football:1647088 | América de Pedrinhas / `2076414b-8e0c-5e79-aca7-127f4ede8990` / 15-15 | Socorrense / `72784f61-a51e-57ca-bc13-5c64176cac0e` / 8-8 | N / FR-004 |
| `95ef4032-a29f-5d66-91b5-8fafc6158aed` / 2026-11-03 18:00:00 | api_football:1612154 | Independiente Riva. Res. / `921a0f8e-9327-5135-9fe8-4006ad43e2e3` / 2-2 | Estudiantes La Plata Res / `eb68648f-7b19-5a7d-ab86-421cd8434873` / 1-1 | N / FR-004 |
| `9f637909-a705-50a3-87f1-0e1a7914ee2b` / 2026-11-03 18:00:00 | api_football:1612156 | Newell's Old Boys Res. / `c9c0e6c8-af0c-5ced-ace4-a3ebc55fdfbf` / 2-2 | Independiente Res. / `974a3bf5-3900-5d4d-8e4b-947c4767a58b` / 1-1 | N / FR-004 |
| `af60dcf3-d6e0-5f37-be86-379b39c8dc0d` / 2026-11-03 18:00:00 | api_football:1612146 | Argentinos Juniors Res. / `87acef03-cc14-55a1-a0a4-87f88c1e702d` / 0-0 | Talleres Córdoba Res. / `8c663b55-3241-5669-b8b7-553d0cd0bf28` / 0-0 | N / FR-004 |
| `bf776c0c-c4b0-554a-9394-97af165c2db2` / 2026-11-03 18:00:00 | api_football:1640298 | Enppi / `1202153d-3058-5135-a452-292bed5f394b` / 25-25 | Asyut Petrol / `6667c2a4-215d-555a-ba4e-851f6fdee90b` / 0-0 | N / FR-004 |
| `dca8a710-84b6-55d5-a7c1-0c286e0f7bf7` / 2026-11-03 18:00:00 | api_football:1582481 | Karlsruhe II / `51cd81c4-9ff2-5fe0-91e0-c42fd779f885` / 0-0 | FC Nöttingen / `31328fb2-7c7c-5325-851b-fce04b413557` / 34-34 | N / FR-004 |
| `dc4c4ccd-f6ba-5b66-9f65-a061ed2a5d26` / 2026-11-03 18:15:00 | api_football:1629972 | Al-Hilal Saudi FC / `7961e83f-9315-571e-939b-1a959125d6a2` / 36-37 | Shabab Al Ahli Dubai / `f9967669-6cbf-5ad2-9e7b-ebb8629f96bd` / 7-8 | N / FR-004 |
| `07772a54-a77b-5af9-b4b2-de90fd278a8b` / 2026-11-03 19:00:00 | api_football:1619517 | FC Halifax Town / `18f35937-51f3-5dda-99d9-3347b1df1781` / 0-4 | Nottingham Forest U21 / `e541036a-97a1-5764-9cf2-27fe53285339` / 1-1 | N / FR-004 |
| `0eedf28a-2f99-5675-93e3-5015f9496a48` / 2026-11-03 19:00:00 | api_football:1627116 | Charlton Athletic U21 / `29501ff5-5829-5aab-b4dc-9ed9a8f8fbd7` / 0-0 | Stockport County U21 / `7dfaaa32-a3a2-5e28-9bc5-320313bb4b4b` / 0-0 | N / FR-004 |
| `293f2bf7-4c35-5173-937a-8e004a58c5f9` / 2026-11-03 19:00:00 | api_football:1619524 | Wealdstone / `63961a7a-8867-563e-b6b2-90f5e13cef0b` / 232-288 | Derby County U21 / `ce71625f-ab35-51e6-8306-76dfdbb4115e` / 0-0 | N / FR-002 |
| `2a26261c-563c-5691-a3cf-eb63a826275e` / 2026-11-03 19:00:00 | api_football:1619516 | Boston United / `be3e802e-a2f2-5406-817b-7cead02291f6` / 92-110 | Leicester City U21 / `4a4334e0-c40c-5fb0-bb5e-5407bdb28d65` / 1-1 | N / FR-002 |
| `3dc5e5ae-5c59-53ba-a3d5-eed57de581ca` / 2026-11-03 19:00:00 | api_football:1588892 | Newport County / `f4576ea7-5926-58cc-83bc-b2f06d4ea482` / 0-0 | Crystal Palace U21 / `85ca16ef-6163-53de-a7c8-9b3519cd8dc4` / 0-0 | N / FR-004 |
| `56e90f27-d965-59a9-9a30-2a3f319b3886` / 2026-11-03 19:00:00 | api_football:1588831 | Rotherham / `665fcbb8-75f3-52c5-af05-417128b86be1` / 1072-1521 | Newcastle United U21 / `8865acc8-9630-5961-be82-0e9a145741a0` / 0-0 | N / FR-002 |
| `6f3916d9-3ddb-5956-9bf2-8c137aa1845c` / 2026-11-03 19:00:00 | api_football:1627164 | Gillingham FC U21 / `d28b14d9-9ed3-5288-9429-df9084f88c2b` / 0-0 | Huddersfield Town U21 / `2c8593fd-5467-5917-b28d-f36bd279657a` / 0-0 | N / FR-004 |
| `729a5007-c107-5ee8-b9ca-39a20d7021d4` / 2026-11-03 19:00:00 | api_football:1619523 | Truro City / `0aebc5ac-af1c-5ceb-9ae9-1a71d7912776` / 0-0 | West Bromwich Albion U21 / `d41a1688-29ed-5ff7-9323-809727d5e8ae` / 1-1 | N / FR-004 |
| `78c6f7a5-b421-55a9-944b-ff330868b8b7` / 2026-11-03 19:00:00 | api_football:1623283 | Middlesbrough U21 / `e6b026ec-7131-570f-bcd8-094184de35f7` / 0-0 | Valencia U21 / `b20bdb30-d1c4-5316-86fd-3adb9195e041` / 0-0 | N / FR-002 |
| `932c511a-cb9f-53a4-834a-50a73e1a96b4` / 2026-11-03 19:00:00 | api_football:1622001 | Brentford U18 / `6f30a80f-5ef7-52a3-9f1b-01ef1f858a4a` / 0-0 | Brighton U18 / `ea7074df-5a58-559b-a25e-d6503d2f4e68` / 0-0 | N / FR-004 |
| `95cdb24b-a5a4-5900-a166-2ee0cb089c92` / 2026-11-03 19:00:00 | api_football:1619520 | AFC Hornchurch / `5e9fea99-aa6c-57f0-9b74-1d8c9099a9fc` / 15-17 | West Ham United U21 / `ef06cc3b-5242-51eb-b2e7-c91d97d14006` / 0-0 | N / FR-002 |
| `99395bf4-3b6d-5b80-bb03-2274004c61d8` / 2026-11-03 19:00:00 | api_football:1619521 | Scunthorpe / `a610a46f-2c88-5ce5-84b8-4e65f30da481` / 1055-1470 | Wolves U21 / `4afb7ce0-2133-574c-99a5-6516c363a932` / 0-0 | N / FR-002 |
| `ae988ae0-adc1-5335-9fc4-ff02bc44c51a` / 2026-11-03 19:00:00 | api_football:1588858 | Rochdale / `5d90e0cf-65cf-5e37-91d1-bdea187ebb1e` / 312-1818 | Doncaster / `2066f0f6-0549-5c1a-a7c1-d67134543beb` / 928-1281 | N / FR-002 |
| `cf1db11d-1bec-5b4d-ad84-3ceb3a03f01b` / 2026-11-03 19:00:00 | api_football:1619518 | Gateshead / `da6c6954-094b-56b8-9fba-4408b512a5dd` / 565-659 | Stoke City U21 / `62af37db-96bf-5e01-8104-901fc2db7f20` / 0-0 | N / FR-002 |
| `d96209b4-76a3-5998-988a-e602ce2b0d93` / 2026-11-03 19:00:00 | api_football:1588901 | Cambridge United / `8c653e08-cdb7-5b30-9b5d-d1f7d8297cdc` / 20-23 | Brighton U21 / `8ade715b-7a79-5242-b3cc-e23142857882` / 0-0 | N / FR-004 |
| `e8339a6a-af2e-5b66-bb5d-f6da06706515` / 2026-11-03 19:00:00 | api_football:1619519 | Hartlepool / `ece32478-593b-5b4a-83ba-d1d6d67a3b90` / 1160-1519 | Leeds United U21 / `29e12b45-5138-5e13-8da4-067615f9098e` / 0-0 | N / FR-002 |
| `e99c739f-0928-50cd-9dee-a91e40009b4a` / 2026-11-03 19:00:00 | api_football:1619522 | Sutton Utd / `da3024c1-9870-542a-a24b-6508768a3325` / 2-2 | Southampton U21 / `a76f692c-e66d-5178-9a29-77aad80a1003` / 0-0 | N / FR-004 |
| `f73f0831-bb6a-5f94-9084-3e12e5eeae9f` / 2026-11-03 19:00:00 | api_football:1641837 | Schaan II / `65f05f61-85b9-5850-87a7-544c7c2996d5` / 1-1 | FC Vaduz / `60b69702-6841-5eb4-8e70-1a9409b4ea42` / 6-6 | N / FR-004 |
| `64d3fb08-23c9-5037-990d-9d42eb0cd00f` / 2026-11-03 19:30:00 | api_football:1619525 | Braintree / `998fca2f-1fac-5ebd-99a6-12ed99c922b6` / 0-0 | Norwich City U21 / `6a78a120-04f9-52b8-8682-06446c69a631` / 0-0 | N / FR-004 |
| `d42e4479-5c94-594f-8343-c84f71b34318` / 2026-11-03 19:30:00 | api_football:1647255 | Flamengo U20 / `5fd4ad43-a2ff-5fdf-9aab-66360cacf084` / 17-17 | Operário PR U20 / `61e41c41-2c02-57c2-a4e7-d3878d786d29` / 1-1 | N / FR-004 |
| `05440828-c132-59bc-8f9a-eefc181eb71c` / 2026-11-03 19:45:00 | api_football:1646404 | Ross County / `c714f2fb-6d72-53e5-b518-53f6389f6ff0` / 40-44 | Celtic II / `5f10401b-b736-5be8-a142-5b37d959e9e6` / 0-0 | N / FR-004 |
| `073b77c4-a7e6-5fbc-8957-2caffbc8e391` / 2026-11-03 19:45:00 | api_football:1564322 | Huddersfield / `ce58e06a-10ce-5b69-8837-a8870ee869f6` / 1025-1515 | Luton / `fe357f9e-e0fc-50bb-8e50-89a492f686af` / 1072-1519 | N / FR-002 |
| `07db0ca2-dfbc-50d0-ae01-836076d2a816` / 2026-11-03 19:45:00 | api_football:1563240 | Blackburn / `966f613c-52ec-51c4-9c23-3d2966ea0138` / 1-1 | Stoke City / `b6d1a4d8-0310-5b30-8e56-5e5912238358` / 1-1 | N / FR-004 |
| `11494738-c65e-5955-8d34-eaf4fe5f9301` / 2026-11-03 19:45:00 | api_football:1596452 | Ashton United / `eea060fa-ab1e-5587-93cc-04c505cd1e3c` / 1-1 | Warrington Town / `719ffcad-1809-5ae6-94a6-b040b9f704e4` / 44-46 | N / FR-004 |
| `14efb0ef-0359-50ef-8975-b467bf2f172d` / 2026-11-03 19:45:00 | api_football:1619528 | Woking / `96897116-9bca-5c87-b56c-7cbd712b840a` / 677-782 | Birmingham City U21 / `6bfe3d00-fcf3-5e87-9a2f-6e6a9e425f85` / 0-0 | N / FR-002 |
| `23ca761a-0df6-533a-a386-b2ca690b3138` / 2026-11-03 19:45:00 | api_football:1596466 | AFC Emley / `473eb119-eacc-5b25-b9d3-d3537fb065f8` / 2-2 | Bamber Bridge / `4eb0d582-b394-5cd0-987b-1c6e8f7136bc` / 0-0 | N / FR-004 |
| `2463acd7-e11e-58b3-ad24-843b6b393c40` / 2026-11-03 19:45:00 | api_football:1563245 | Watford / `440b0339-8804-52e0-800e-c4c3f8591e72` / 1-193 | Lincoln / `3548f488-fba4-5606-9da0-0b6980414b1b` / 20-20 | N / FR-003 |
| `2c94c310-176c-5904-9b3b-10294a8b7a5b` / 2026-11-03 19:45:00 | api_football:1619529 | Worthing / `17e5e259-9896-51e0-ae4f-b8414c518c06` / 14-18 | Fulham U21 / `fed0d577-1f03-5579-81b2-9225ca86083a` / 0-0 | N / FR-002 |
| `325c815b-0b39-5357-a5f6-8b395c8fb35a` / 2026-11-03 19:45:00 | api_football:1619527 | Tamworth / `7d3a1818-66c5-5c07-af0e-4bd3a44b1b55` / 0-424 | Everton U21 / `a4d89c22-c972-5396-aea7-6293e6d3f8f5` / 0-0 | N / FR-002 |
| `360d03ce-c405-5682-b62a-aac28bc7f642` / 2026-11-03 19:45:00 | api_football:1596904 | Bury Town / `3068962a-7305-5646-89d2-39f48da0b412` / 2-2 | Kettering Town / `26670d7f-d6a4-5583-a8ee-9fe8d745c5d1` / 0-0 | N / FR-004 |
| `3869e77f-72e8-5485-b165-243bb233cf0c` / 2026-11-03 19:45:00 | api_football:1596024 | Brentwood Town / `f10bd369-6997-5590-9c6d-9305708973fa` / 3-3 | Leatherhead / `89ab5eae-80f4-5fac-a94a-970bf3b1d700` / 1-1 | N / FR-004 |
| `38f469b3-55eb-54e5-b740-415079e4e92b` / 2026-11-03 19:45:00 | api_football:1597415 | Poole Town / `cd691d54-a35a-5990-b9ee-53f658f8b235` / 2-2 | Hanwell Town / `7cddbc2b-703c-5f09-b2cd-8a82a7e8d480` / 1-1 | N / FR-004 |
| `392b1049-39c0-545e-a931-700b84931d0c` / 2026-11-03 19:45:00 | api_football:1563241 | Derby / `c97c7c8a-7b89-52ee-8f24-2ab22f3b6524` / 1-1 | Norwich / `e8c5b93a-5ccb-532e-892f-f17a310ac3bf` / 1-1 | N / FR-004 |
| `416fa23e-651f-5d23-bb4d-7694692477b1` / 2026-11-03 19:45:00 | api_football:1596444 | Curzon Ashton / `e60c466d-681f-5a4c-93e6-bb2d5821fe75` / 44-46 | United of Manchester / `c15d3f62-f8af-5c9f-b85d-2d8a58e43bb3` / 0-0 | N / FR-004 |
| `4aab2451-0abd-577b-8d8d-4fa0636d4bf7` / 2026-11-03 19:45:00 | api_football:1597424 | Chippenham Town / `a83b388d-4e15-5adf-a90e-158a53b3a0ec` / 1-1 | Evesham United / `0677d4b4-f1c2-533b-b06a-c31bceefc751` / 2-2 | N / FR-004 |
| `4b622420-8610-5988-9d42-204a5e5ed1ec` / 2026-11-03 19:45:00 | api_football:1563244 | QPR / `e9fbf654-4f77-528f-971e-314c6c321872` / 1-1 | Burnley / `b1020b91-c500-53a8-ad0d-db73b2cd24c1` / 34-297 | N / FR-004 |
| `4f904d74-2168-5907-9541-eb45095f7ad2` / 2026-11-03 19:45:00 | api_football:1563242 | Portsmouth / `ce31b311-ca2b-5aa6-99b5-c45358125ace` / 2-5 | Swansea / `f016c84c-53c0-56d0-b9fa-df13f648a4b7` / 1-1 | N / FR-004 |
| `516bf5e9-c8f5-540d-8951-263a5314528d` / 2026-11-03 19:45:00 | api_football:1596457 | Guiseley AFC / `e6662f41-fb47-5ed1-b807-3ff5bfc8cc80` / 1-1 | Leek Town / `f055eef0-ea04-5e57-b0c4-b6280d2163ad` / 1-1 | N / FR-004 |
| `52e216b1-0d15-5e26-a1d3-305eedda57ba` / 2026-11-03 19:45:00 | api_football:1646406 | Stenhousemuir / `4c3c91a2-0e7e-59e3-a140-d172b8be6e78` / 40-40 | Berwick Rangers / `84e5e5fc-b5e0-5dc4-bab3-8c2b8c4356ec` / 2-2 | N / FR-004 |
| `5c3d1731-afec-5324-a178-0ee4a9e1b736` / 2026-11-03 19:45:00 | api_football:1596010 | Wingate & Finchley / `ed885c9c-ff2a-571e-995f-31030045bea6` / 0-0 | Burgess Hill Town / `5b31dbf7-4917-5f67-81ed-0e254da7679b` / 3-3 | N / FR-004 |
| `5f72c676-9b77-5fd9-b170-a704c477144b` / 2026-11-03 19:45:00 | api_football:1597367 | Bracknell Town / `e5dda90b-32db-518d-9bbd-8968bf5ddf4d` / 2-2 | Chertsey Town / `85b9413e-5454-5680-b3cd-d077ef5becf0` / 0-0 | N / FR-004 |
| `61230c9b-1d53-52aa-84f5-9c10eef27b0f` / 2026-11-03 19:45:00 | api_football:1646392 | Aberdeen U21 / `75f64d87-e609-56d6-8d61-9d2c686273e4` / 0-0 | Queen's Park / `31c10150-4f47-5813-8045-11cee7b129e9` / 38-41 | N / FR-004 |
| `63066251-bf55-55cf-8ba2-6c0b3cb17e6f` / 2026-11-03 19:45:00 | api_football:1619526 | Aldershot Town / `5bdde342-9907-5ab3-b104-82f4a5f69cfe` / 0-4 | Ipswich Town U21 / `61b66634-b700-5fb6-986c-401c03447734` / 0-0 | N / FR-004 |
| `6da4ed31-cd00-5c26-ae9b-319845cc3816` / 2026-11-03 19:45:00 | api_football:1646398 | East Kilbride / `3205db37-7d01-5351-9b29-8d2983652c56` / 5-8 | Stirling Albion / `e4cb27da-1f26-56d6-a5c5-f47fd28a770f` / 37-41 | N / FR-004 |
| `6da75054-db2c-53f0-a2e6-88f5d84a0f47` / 2026-11-03 19:45:00 | api_football:1597372 | Plymouth Parkway / `964337d7-82f2-507f-866f-dc35bc40dc46` / 0-0 | Uxbridge / `17a8523d-00dc-53d5-b99e-25b4a3991834` / 3-3 | N / FR-004 |
| `823612a9-5c52-51a5-8d9c-7b73016cd9f0` / 2026-11-03 19:45:00 | api_football:1596454 | Bury / `539cde6b-2bfc-5715-90c0-9960ecd0e11c` / 2-2 | Avro / `62a7e59a-7701-59cd-b36d-04dd51724981` / 1-1 | N / FR-004 |
| `8a4c045a-f082-55d4-a5b2-3ef82f78df4d` / 2026-11-03 19:45:00 | api_football:1588390 | Dorking Wanderers / `6bbc65ae-2f47-596c-8371-9e3135fee0a6` / 0-2 | Hampton & Richmond / `46f166e8-d251-59f6-9c72-61bf415ee246` / 0-1 | N / FR-004 |
| `8e72c406-288c-5dcf-ac8a-b3ae4f2f09eb` / 2026-11-03 19:45:00 | api_football:1563787 | Northampton / `416a68ff-f97b-5636-8d64-3cdadfe97b27` / 1171-1513 | Oldham / `dddd2e86-63a7-5dca-a353-2067f8f10ab3` / 1045-1517 | N / FR-002 |
| `95ef751c-49d4-51c4-ac81-652d2327ee0c` / 2026-11-03 19:45:00 | api_football:1588309 | Farnborough / `c574a5cc-8361-55e4-8dc5-74dbfd1d6c38` / 0-0 | Ebbsfleet United / `2c4ee19f-420d-521f-b9cb-07f6ca1ed6a5` / 0-4 | N / FR-004 |
| `993b50d0-3c38-52b7-8f62-bdee6cf6d637` / 2026-11-03 19:45:00 | api_football:1564342 | Wigan / `50781f0e-f73a-561c-9c3a-40179364d540` / 962-1458 | Mansfield Town / `1910ba4b-246f-510c-9600-a0121c8b7594` / 316-338 | N / FR-002 |
| `af47d516-c684-5e46-9cf5-40271f0b6658` / 2026-11-03 19:45:00 | api_football:1595997 | Lewes / `20787304-cfec-59bf-823d-cd1da58b0738` / 0-0 | Dartford / `b7efb8d1-6e4e-5b4a-b4b6-ebb908cec4f7` / 1-1 | N / FR-004 |
| `b3411bcd-70d4-58fa-8419-16b42096a66e` / 2026-11-03 19:45:00 | api_football:1646400 | Formartine United / `1b5e8b17-5d72-5bf5-ba9c-35de38daf3cf` / 2-2 | Cove Rangers / `78fe6957-eaff-55ff-bb5d-eeb2c67ebbb0` / 43-47 | N / FR-004 |
| `bdf8082d-e457-5576-95d5-b72faecf0aa3` / 2026-11-03 19:45:00 | api_football:1646397 | Clydebank / `2f8d8b43-fe02-554e-b4e2-ee570d4872e7` / 5-5 | Alloa Athletic / `1eafeab3-f319-53ac-ad52-530cc627d9a4` / 37-41 | N / FR-004 |
| `d1acdd33-1d9c-57e5-854b-c126404373c3` / 2026-11-03 19:45:00 | api_football:1595994 | Eastbourne Borough / `eff2145c-6aee-567f-bdd6-4f2001a0b921` / 0-0 | Stanway Rovers / `1f99ba3e-b31d-5fe8-81e9-e0bc43b5c710` / 3-3 | N / FR-004 |
| `e5e620b5-20d8-5726-a547-a2d1e7037796` / 2026-11-03 19:45:00 | api_football:1646407 | St. Mirren U21 / `79a7b14e-935e-5772-944f-8a20a820c367` / 0-0 | Peterhead / `dc11f317-f7d8-5495-9d6b-4fb1af396cef` / 38-42 | N / FR-004 |
| `e5fde629-aeb7-5cd7-849e-ecaf9d661655` / 2026-11-03 19:45:00 | api_football:1596903 | Anstey Nomads / `6752d6d1-1dae-53e3-a8b1-9593d2b7372d` / 1-1 | Real Bedford / `d977428c-12e5-5b32-8808-779753702ef5` / 1-1 | N / FR-004 |
| `e7a70350-6a1a-5e86-8f19-de2618594a92` / 2026-11-03 19:45:00 | api_football:1610755 | Torreense W / `8093f1c8-75a4-514b-b205-42bd89c0e035` / 0-0 | SL Benfica W / `13f22959-5f51-5746-924d-a91ad10f0a8e` / 0-4 | N / FR-002 |
| `fd751952-c53c-54c4-b9e5-c7c04729ec56` / 2026-11-03 19:45:00 | api_football:1563243 | Preston / `9a7cfb23-ed79-5db9-b9af-d6b9ef728c99` / 1-1 | Sheffield Utd / `7ae76e2c-e5bd-5dad-b506-42930842dd47` / 7-7 | N / FR-004 |
| `137cabf7-75d8-5521-8295-d490ef1d1a42` / 2026-11-03 20:00:00 | api_football:1647615 | Sporting Cristal W / `e1709cd4-a61e-53b3-8f09-57f74fd933e8` / 0-0 | Alianza Lima W / `4b1e92bf-4782-54f7-acb3-11043291b7f8` / 4-4 | N / FR-004 |
| `1b1ad4d4-a020-5a7c-bed5-9d74b2fa1216` / 2026-11-03 20:00:00 | api_football:1549539 | Comerciantes Unidos / `9f498d1e-4bcc-5f3c-872f-c7f2ce15b160` / 0-0 | ADT / `3bc553eb-0964-55b1-aa59-f8f0404bf938` / 0-0 | N / FR-004 |
| `c2dcc792-7143-58ff-abb5-32fd82b206d2` / 2026-11-03 20:00:00 | api_football:1563246 | West Brom / `adf9d9e9-7e9f-5eab-9697-ec75b9c6c1c8` / 1-1 | Southampton / `7c52f01f-04d0-571a-a6f9-3afb575f83e6` / 1-382 | N / FR-004 |
| `d2e170b1-eb6e-5043-8b9c-d1bc34bdf18c` / 2026-11-03 20:00:00 | api_football:1563239 | Birmingham / `1ce8dc0f-071d-5be2-989b-886781d84f07` / 20-20 | Millwall / `e2a33039-e2b5-59f5-862f-f374e595ba29` / 1-1 | N / FR-004 |
| `4b24fe04-2deb-53b7-9f65-562b3deebafc` / 2026-11-03 20:30:00 | api_football:1639831 | Mushuc Runa SC / `82b33e9e-69f8-5f90-8e30-90af2cf6443d` / 0-0 | Manta FC / `e5d96c4b-ff17-5ea4-8b52-507d3f86eae4` / 36-36 | N / FR-004 |
| `b3a3f351-d49b-5677-85d6-ecc61f5ab859` / 2026-11-03 21:30:00 | api_football:1646928 | Monagas SC / `a42e70ec-6588-5647-9c75-16ea89e522bf` / 0-1 | Caracas FC / `652a0059-516a-56be-98fa-e3885049f03c` / 7-9 | N / FR-004 |
| `03a9e427-f352-593f-b044-ca4d08eeeff2` / 2026-11-03 22:00:00 | api_football:1612158 | River Plate Res. / `8cd8c55e-169f-5881-a66b-ddbfc217233a` / 2-2 | Tigre Res. / `ce091eab-7c71-5817-ba74-36c49c339e10` / 0-0 | N / FR-004 |
| `34ef39c5-aaa0-5aef-a453-7161623f503c` / 2026-11-03 22:30:00 | api_football:1492443 | Chapecoense-sc / `1a968f06-2e9e-578c-acfd-ee9ea792bc61` / 0-0 | Mirassol / `3908928d-e84e-51c2-924d-d9062a7090a8` / 0-2 | N / FR-004 |
| `d766aea6-ab04-5c1e-88ac-24be27f898f0` / 2026-11-03 23:00:00 | api_football:1645454 | Aurora / `5743d4c3-4c8e-554f-9177-0c55cf1412eb` / 8-8 | Independiente Petrolero / `4e658907-ed00-5e02-b37c-76e16a3ef66a` / 0-0 | N / FR-004 |
| `0d8983e1-0e3f-5329-96cd-d2ae4cb6bbee` / 2026-11-03 23:30:00 | api_football:1646929 | Deportivo Tachira FC / `a9531ffb-6d4f-5961-9cde-f4a1c0c3b7b2` / 6-6 | Puerto Cabello / `083d7f35-065d-54e5-a60b-8b178ace8037` / 3-3 | N / FR-004 |
| `e32d4aab-d858-54a2-9d66-42a1b88d57a5` / 2026-11-04 10:00:00 | fotmob:6054695 | FC Seoul / `47e56793-620f-555f-bb6d-be973b703d2f` / 3-4 | Viettel / `b5f883ec-6601-5844-9acc-e074c7008b61` / 17-107 | O / FR-004 |
| `ac3a80c9-0056-5278-bfcc-06c6a0e211ec` / 2026-11-04 13:45:00 | fotmob:6054596 | Arkadag / `2c24e1bc-3c4d-5bac-a5f6-5e22fec6461d` / 3-12 | Gol Gohar / `30120434-c005-5bae-8a3c-99a00211357e` / 3-4 | O / FR-004 |
| `58280732-1507-551e-8ef8-a608b8c77792` / 2026-11-04 18:15:00 | fotmob:6054597 | Muharraq / `8aa24a6c-7de2-5b40-a8d0-cf01e42efe29` / 3-15 | Al-Jazira / `f672332d-5c49-5fb9-ae89-31b450942d99` / 3-4 | O / FR-004 |
| `1398c034-f813-501d-9e84-db86e8f3b396` / 2026-11-05 10:00:00 | fotmob:6054838 | Machida Zelvia / `a4a27bf1-06bf-585d-9264-cfb3655954b9` / 0-5 | Shanghai Shenhua / `22d18839-5505-5de9-810c-e7b480d39a81` / 0-4 | O / FR-002 |
| `a589bdf3-4401-5f42-a7fe-49c9b8744c48` / 2026-11-05 20:00:00 | fotmob:6112242 | Bayer Leverkusen / `a6c06480-b982-5377-bf61-de979a29b1bf` / 24-24 | Marseille / `ad2ed99a-0412-5051-b435-a65e35282e03` / 7-7 | O / FR-004 |
| `c0628407-07f1-522a-98eb-edf2fd1b9218` / 2026-11-06 16:00:00 | fotmob:5973002 | Sardarapat / `96bb48e5-4015-516f-b2cd-168971de6bd3` / 10-14 | Ararat / `bded9ee7-f354-58c9-b986-85792734ae2c` / 147-223 | O / DONE |
| `d91dfb10-fe75-5f8d-8118-5a9a0aea85f2` / 2026-11-06 20:00:00 | fotmob:5795508 | Everton / `5bd977a1-a09d-5736-bf7c-4f4c085bb3b2` / 368-532 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | O / DONE |
| `48c38317-2de9-56ca-a58f-2ccba6d28022` / 2026-11-07 13:00:00 | fotmob:5868125 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | Racing Santander / `af094f15-ddd5-53f7-a207-245889651717` / 15-16 | O / DONE |
| `a49bcd54-0272-53e6-86e7-287dc385c65c` / 2026-11-15 15:30:00 | fotmob:5975103 | Young Apostles / `54b9ed3b-35e5-53c0-99a6-0f20c5fbfe8d` / 58-98 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | O / FR-001 |
| `d69d315a-8197-5d0f-b24c-60f15475e68c` / 2026-11-21 15:00:00 | fotmob:5795519 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | Crystal Palace / `edd9a29a-13b2-5a98-835c-ae7510fdd86d` / 316-449 | O / DONE |
| `44397361-0610-5afd-bbc5-6f842756b7ce` / 2026-11-22 14:00:00 | fotmob:5868136 | Osasuna / `6f0c35ce-3661-5f04-b414-78a649a58f92` / 134-243 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | O / DONE |
| `1e25a517-7f96-5690-85dc-94e0244172b2` / 2026-11-22 15:30:00 | fotmob:5975110 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | Ashanti Gold / `6731d927-6bd0-5ca3-8ca1-f5eb53227b35` / 46-100 | O / FR-001 |
| `520d4181-d6ba-56d6-9e90-cd63ace2e21c` / 2026-11-22 15:30:00 | fotmob:5975111 | Port City / `eace79b0-415c-5d1e-92e1-f75568c227b0` / 0-6 | Heart of Lions / `0cefceda-3545-5128-942b-95cc50b54d9d` / 86-146 | O / FR-001 |
| `a68f87ee-44e7-514f-8b70-b3987538be4d` / 2026-11-25 12:15:00 | fotmob:1000021395 | Persib Bandung / `c0f025fa-15a9-5a47-8141-84004c9ab2ef` / 112-260 | FC Seoul / `47e56793-620f-555f-bb6d-be973b703d2f` / 3-4 | O / FR-004 |
| `09727dfd-4c2f-528a-8104-9f36ff571c20` / 2026-11-25 16:00:00 | fotmob:6054599 | Muharraq / `8aa24a6c-7de2-5b40-a8d0-cf01e42efe29` / 3-15 | Arkadag / `2c24e1bc-3c4d-5bac-a5f6-5e22fec6461d` / 3-12 | O / FR-003 |
| `133e5b66-da6c-508f-9b90-e01a81058b09` / 2026-11-25 16:00:00 | fotmob:6054598 | Al-Jazira / `f672332d-5c49-5fb9-ae89-31b450942d99` / 3-4 | Gol Gohar / `30120434-c005-5bae-8a3c-99a00211357e` / 3-4 | O / FR-004 |
| `cae1589e-967c-5e92-a017-53f033ca15cc` / 2026-11-27 08:30:00 | fotmob:6280607 | Dhaka Wanderers / `c42d4386-d73c-5ed3-b8b3-aee5c5b14384` / 2-9 | Arambagh / `e0212758-e8c3-572e-84e9-e3e00c534049` / 4-10 | O / FR-004 |
| `00d13a44-7186-555b-bbbf-c061cca47e46` / 2026-11-27 16:00:00 | fotmob:5973014 | Sardarapat / `96bb48e5-4015-516f-b2cd-168971de6bd3` / 10-14 | Ararat-Armenia / `35185df7-f3bb-578a-8c5e-3d6528b19b19` / 161-237 | O / DONE |
| `19f36866-3024-5ee5-9258-7f571df3a6f1` / 2026-11-28 11:00:00 | fotmob:6095781 | Bắc Ninh / `32ca94e2-5c56-5c31-b481-47003525e727` / 3-6 | Da Nang / `ce8e3f94-f838-5dab-a89d-c32128580c0d` / 5-73 | O / FR-004 |
| `3cbcc0ff-31fe-5a9a-bbfd-94851213efe6` / 2026-11-28 15:00:00 | fotmob:5795531 | Leeds / `e15d5f29-ee93-54cf-a6ce-c66ea52c1ffd` / 111-139 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | O / DONE |
| `d1bb34cd-6692-57a0-9d52-5afaee253c29` / 2026-11-29 14:00:00 | fotmob:5868147 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | Athletic Club / `692958c4-2052-5296-8b1f-8ae7c179cbe8` / 142-252 | O / DONE |
| `b02e7183-e8cb-5bd9-8342-4ab68e1d3915` / 2026-11-29 15:30:00 | fotmob:5975119 | Samartex / `6a1d3c79-8845-5076-aff7-2e7d6731b892` / 108-193 | Port City / `eace79b0-415c-5d1e-92e1-f75568c227b0` / 0-6 | O / FR-001 |
| `c9c23db5-c111-5881-8102-1278ef129629` / 2026-12-02 10:00:00 | fotmob:6054697 | FC Seoul / `47e56793-620f-555f-bb6d-be973b703d2f` / 3-4 | Melbourne Victory / `3a6421ae-c365-5b08-88f4-532746b85914` / 41-55 | O / FR-004 |
| `ae07b453-ad56-5560-a4b3-54f8c2aa2d0c` / 2026-12-02 20:00:00 | fotmob:5795539 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | Ipswich / `01274ff5-483d-51a6-aa3c-e5a72d81f8f6` / 37-41 | O / DONE |
| `0ca55ce7-6d96-5bf7-89ed-d46c66c63222` / 2026-12-03 19:45:00 | fotmob:5886593 | Caen / `774fb06f-210e-580c-a8d8-a253d0d89bb8` / 146-247 | Cannes / `25b4e16e-98ec-5190-9592-19c198a2fe44` / 4-11 | O / FR-003 |
| `42d6cd94-a116-5b00-bcad-91830ac1f2c8` / 2026-12-05 08:30:00 | fotmob:6280614 | Brothers Union / `1c4bec1f-6b47-5a0b-a064-6179283db575` / 11-35 | Arambagh / `e0212758-e8c3-572e-84e9-e3e00c534049` / 4-10 | O / FR-003 |
| `7d73cbf2-6405-5ab5-9e49-eeaee5ab1044` / 2026-12-05 08:30:00 | fotmob:6280615 | Fortis / `522abbc4-a922-5182-9e5c-9454822a87e8` / 10-47 | Dhaka Wanderers / `c42d4386-d73c-5ed3-b8b3-aee5c5b14384` / 2-9 | O / FR-004 |
| `fe88e16f-01d2-5ade-b04c-4c5c66ba0b9f` / 2026-12-05 08:30:00 | fotmob:6280617 | Rahmatgonj MFS / `eb0f448d-4e75-56a8-aac0-a8b3cd9c76d7` / 12-46 | City Club / `7c545aa8-34d3-5777-a57f-59aa43981ffb` / 4-4 | O / FR-004 |
| `d1da1346-f23d-598a-8bca-5ddb539e0df0` / 2026-12-05 11:00:00 | fotmob:6095788 | Bắc Ninh / `32ca94e2-5c56-5c31-b481-47003525e727` / 3-6 | Hồng Lĩnh Hà Tĩnh / `7cbbfcda-9b8d-5de7-b2c1-7410549a920e` / 14-101 | O / FR-004 |
| `36a27c8b-60a9-57be-a148-8a4dc86ac35f` / 2026-12-05 15:00:00 | fotmob:5795551 | Manchester United / `fcefd735-1779-555e-800f-e700d5b89abd` / 382-547 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | O / DONE |
| `3821252c-f534-5799-a761-ab18516f6490` / 2026-12-06 15:30:00 | fotmob:5975129 | Port City / `eace79b0-415c-5d1e-92e1-f75568c227b0` / 0-6 | Aduana Stars / `83967452-69c8-5883-9fec-e5959e5d5901` / 147-281 | O / FR-001 |
| `3ea0052e-8a16-525c-bd71-0de1aac8e6dd` / 2026-12-07 11:00:00 | fotmob:6095792 | Da Nang / `ce8e3f94-f838-5dab-a89d-c32128580c0d` / 5-73 | Viettel / `b5f883ec-6601-5844-9acc-e074c7008b61` / 17-107 | O / FR-003 |
| `7b6e9ad1-aeea-5b61-9735-7c619e3ccc48` / 2026-12-08 16:00:00 | fotmob:6054518 | Al Hussein / `b08eb992-4f9b-539f-91ac-19b7fe6c0a98` / 1-17 | Al Seeb / `6a7ea3da-abdd-5f51-84ef-7347f056c942` / 7-14 | O / FR-003 |
| `65f1cad7-d4f8-5e57-a192-e198fabcf524` / 2026-12-09 13:45:00 | fotmob:6054601 | Gol Gohar / `30120434-c005-5bae-8a3c-99a00211357e` / 3-4 | Muharraq / `8aa24a6c-7de2-5b40-a8d0-cf01e42efe29` / 3-15 | O / FR-004 |
| `a528b110-38dd-5031-a200-f1efe56478bc` / 2026-12-09 13:45:00 | fotmob:6054600 | Arkadag / `2c24e1bc-3c4d-5bac-a5f6-5e22fec6461d` / 3-12 | Al-Jazira / `f672332d-5c49-5fb9-ae89-31b450942d99` / 3-4 | O / FR-004 |
| `027a94e2-a117-5ccb-91e1-cfbeff74aae3` / 2026-12-09 16:00:00 | fotmob:6054503 | Al-Nahda / `895d40ca-fb27-5bd7-b1c3-b653bc31c848` / 2-11 | Al Faisaly / `916ffbf2-b8c4-56d3-9d70-5b2d324a3130` / 2-8 | O / FR-004 |
| `3316c946-aab0-5e95-9cf3-9033b3ceb194` / 2026-12-10 17:45:00 | fotmob:6112276 | Marseille / `ad2ed99a-0412-5051-b435-a65e35282e03` / 7-7 | Celta Vigo / `04e2160f-0800-56e5-879c-167ed4e10f2f` / 140-257 | O / FR-004 |
| `90e5b771-c4e8-5b48-b616-034cd5f18e7c` / 2026-12-12 08:30:00 | fotmob:6280621 | Arambagh / `e0212758-e8c3-572e-84e9-e3e00c534049` / 4-10 | Fortis / `522abbc4-a922-5182-9e5c-9454822a87e8` / 10-47 | O / FR-003 |
| `1afbe728-314c-5a94-977e-5d43853f9dba` / 2026-12-12 11:00:00 | fotmob:6095795 | Hai Phong / `8a80b9e9-9875-541f-9431-a2da66f10c6a` / 16-104 | Bắc Ninh / `32ca94e2-5c56-5c31-b481-47003525e727` / 3-6 | O / FR-004 |
| `dc68f7b7-deeb-5266-ac85-c23eebc98329` / 2026-12-12 11:00:00 | fotmob:6095796 | Hồng Lĩnh Hà Tĩnh / `7cbbfcda-9b8d-5de7-b2c1-7410549a920e` / 14-101 | Da Nang / `ce8e3f94-f838-5dab-a89d-c32128580c0d` / 5-73 | O / FR-003 |
| `9f8492ca-fa53-5e5a-b2fc-f4e7719af8d8` / 2026-12-12 15:00:00 | fotmob:5795557 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | Aston Villa / `9648865b-e6be-56cf-9c84-fefa3cb3f978` / 322-449 | O / DONE |
| `3ba7d48d-d530-52fe-b495-26db34008465` / 2026-12-13 12:00:00 | fotmob:6011949 | Garudayaksa / `b8c2ba83-f1d3-5b68-9b83-4a11ccd94462` / 5-9 | Dewa United / `cafe4c99-e6dd-50de-b2c2-e912d9ac8cfa` / 77-179 | O / FR-004 |
| `c23c65fd-751c-540b-9bcf-40312713c323` / 2026-12-13 14:00:00 | fotmob:5868167 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | Barcelona / `2ba95686-80aa-560a-8b9e-c46f6fdbf053` / 148-258 | O / DONE |
| `0c102cf7-dbff-5b9a-9c94-ee2d85ac9985` / 2026-12-13 15:30:00 | fotmob:5975136 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | Bibiani Gold Stars / `f2451bfd-22b2-531a-8eed-d87272b8cfc1` / 133-239 | O / FR-001 |
| `1cdf103c-8fc3-5413-9f28-cf1b4170b6db` / 2026-12-17 08:30:00 | fotmob:6011955 | PSM Makassar / `d8696dff-e8e3-5970-a552-ba68262b3990` / 115-254 | Garudayaksa / `b8c2ba83-f1d3-5b68-9b83-4a11ccd94462` / 5-9 | O / FR-004 |
| `cb9c89df-015d-5431-a18c-72c0dab50295` / 2026-12-19 08:30:00 | fotmob:6280628 | Arambagh / `e0212758-e8c3-572e-84e9-e3e00c534049` / 4-10 | Fakirerpool / `3fc48514-8c43-54bc-bd0a-b74872dc349d` / 3-16 | O / FR-003 |
| `e4365f34-6f7f-5ac9-90a7-0586a31954d5` / 2026-12-19 08:30:00 | fotmob:6280629 | City Club / `7c545aa8-34d3-5777-a57f-59aa43981ffb` / 4-4 | Dhaka Wanderers / `c42d4386-d73c-5ed3-b8b3-aee5c5b14384` / 2-9 | O / FR-004 |
| `23c63dbe-36e0-51c9-8285-d7f64388a5ef` / 2026-12-19 15:00:00 | fotmob:5795565 | Bournemouth / `e28e7533-6931-5361-9129-7c2a5bae2aaa` / 228-307 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | O / DONE |
| `d9f95eb6-9cf2-51c0-91a6-90cf9fcfcdbd` / 2026-12-19 16:00:00 | fotmob:5765982 | Rudes / `5d0e7079-5a62-5e61-9688-a256fd4ced36` / 9-50 | HNK Gorica / `a284e8f5-4c67-5703-84fa-7f655614efd4` / 40-261 | O / FR-003 |
| `0e0b2d66-9e79-51ee-ad11-dc67d2821cab` / 2026-12-20 13:00:00 | fotmob:5934588 | Mainz 05 W / `b2fe7f6a-e75a-56f1-9269-f78b2aaf9847` / 7-10 | Bayer Leverkusen W / `6c6ae2d5-37e3-513a-95d8-368d2caee99d` / 116-209 | O / FR-003 |
| `e21e72fb-2361-5d1d-ad87-e41b515ddd57` / 2026-12-20 14:00:00 | fotmob:5868178 | Rayo Vallecano / `6390f775-dda9-5bc5-ac14-fee4910a39c6` / 116-204 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | O / DONE |
| `c979ccf6-b620-5c2a-befe-8e5b93deae05` / 2026-12-20 15:30:00 | fotmob:5975140 | Bechem United / `6caa924c-7272-5c7b-a1c4-49b7b7e4a288` / 149-281 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | O / FR-001 |
| `69a39c45-dd9a-5fa9-b50e-44c73d94fa51` / 2026-12-21 11:00:00 | fotmob:6095807 | Bắc Ninh / `32ca94e2-5c56-5c31-b481-47003525e727` / 3-6 | Thanh Hóa / `cfd04f4f-d2d1-5ab6-b75b-1852201a630f` / 19-103 | O / FR-004 |
| `31c24637-1b55-5ba9-9e59-5774a1c7bde7` / 2026-12-25 08:30:00 | fotmob:6280630 | Dhaka Wanderers / `c42d4386-d73c-5ed3-b8b3-aee5c5b14384` / 2-9 | Bangladesh Police / `4ed6c12d-cf1b-5fcb-9fb3-1a7e4235ecaf` / 11-46 | O / FR-004 |
| `ec3bb831-1e79-58d4-b3dc-6254c36e477c` / 2026-12-26 08:30:00 | fotmob:6280633 | Fakirerpool / `3fc48514-8c43-54bc-bd0a-b74872dc349d` / 3-16 | Brothers Union / `1c4bec1f-6b47-5a0b-a064-6179283db575` / 11-35 | O / FR-003 |
| `cf3a7eb6-8f87-5bd9-a580-1b5fe2a09a15` / 2026-12-26 12:00:00 | fotmob:6011974 | Garudayaksa / `b8c2ba83-f1d3-5b68-9b83-4a11ccd94462` / 5-9 | Isenmulang Kalteng / `4cd979f6-e5f7-5329-8ae4-8e97891f8bd6` / 25-31 | O / FR-004 |
| `da0ac8ae-a0de-5636-a6e2-185509a5d3e1` / 2026-12-27 14:00:00 | fotmob:5795576 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | Chelsea / `5ca3d524-59e8-5122-bfe8-b1cafdbf224e` / 384-549 | O / DONE |
| `5de9dd76-2d3a-529f-b49d-06800dd0bde9` / 2026-12-27 15:30:00 | fotmob:5975154 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | Hearts of Oak / `69b1eff6-4bc6-5da8-9340-fb99e652e82d` / 147-282 | O / FR-001 |
| `7a21fc8e-4e01-5936-bf85-88b316b850e0` / 2026-12-27 15:30:00 | fotmob:5975157 | Young Apostles / `54b9ed3b-35e5-53c0-99a6-0f20c5fbfe8d` / 58-98 | Port City / `eace79b0-415c-5d1e-92e1-f75568c227b0` / 0-6 | O / FR-001 |
| `0e0f8f77-e4a4-5e27-9684-2978fd1dfd2c` / 2026-12-30 19:30:00 | fotmob:5795586 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | Brentford / `73f1706b-973b-54a6-aad7-c80ef9d55e73` / 168-175 | O / DONE |
| `17a76f17-8ca8-50bf-8591-84ecff0ff863` / 2027-01-02 08:30:00 | fotmob:6280641 | Dhaka Wanderers / `c42d4386-d73c-5ed3-b8b3-aee5c5b14384` / 2-9 | Rahmatgonj MFS / `eb0f448d-4e75-56a8-aac0-a8b3cd9c76d7` / 12-46 | O / FR-004 |
| `9465ac40-30f1-55e3-9e08-8a2cd2e79474` / 2027-01-02 15:00:00 | fotmob:5795601 | Liverpool / `a1885e25-3c5b-53da-885f-09ef2e2d01cb` / 412-539 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | O / DONE |
| `9062a9ea-5296-55b5-b6b6-9ae67ad54754` / 2027-01-03 14:00:00 | fotmob:5868185 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | Elche / `6f764036-fc28-535b-bf89-01e9d4a5c1dc` / 99-169 | O / DONE |
| `3a866e2f-1c41-5ac3-a5ce-8be68da6c667` / 2027-01-03 15:30:00 | fotmob:5975164 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | Dreams / `9d1e589e-0a30-5cb6-a392-d8e8bd34155f` / 149-282 | O / FR-001 |
| `cb09fc37-a457-5101-97c4-c7f63e380cae` / 2027-01-03 15:30:00 | fotmob:5975160 | Ashanti Gold / `6731d927-6bd0-5ca3-8ca1-f5eb53227b35` / 46-100 | Port City / `eace79b0-415c-5d1e-92e1-f75568c227b0` / 0-6 | O / FR-001 |
| `36c2a22b-a8fb-5870-b14c-49abdbaebb57` / 2027-01-06 19:30:00 | fotmob:5795610 | Ipswich / `01274ff5-483d-51a6-aa3c-e5a72d81f8f6` / 37-41 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | O / DONE |
| `9f3fdeac-300b-54fe-bfb3-0bfc141ecbbc` / 2027-01-08 08:30:00 | fotmob:6280642 | Brothers Union / `1c4bec1f-6b47-5a0b-a064-6179283db575` / 11-35 | Dhaka Wanderers / `c42d4386-d73c-5ed3-b8b3-aee5c5b14384` / 2-9 | O / FR-004 |
| `c3074d67-4219-500e-b8b7-18c2a5555c04` / 2027-01-08 11:30:00 | fotmob:6280643 | Bashundhara Kings / `c3b397ec-2551-5779-b7d4-953412ad1836` / 11-60 | Fakirerpool / `3fc48514-8c43-54bc-bd0a-b74872dc349d` / 3-16 | O / FR-003 |
| `af1ca66c-5a63-53cf-94be-dd770883962b` / 2027-01-09 08:30:00 | fotmob:6280645 | Bangladesh Police / `4ed6c12d-cf1b-5fcb-9fb3-1a7e4235ecaf` / 11-46 | City Club / `7c545aa8-34d3-5777-a57f-59aa43981ffb` / 4-4 | O / FR-004 |
| `baeeaa74-80bf-54be-b1d3-8c38891cf113` / 2027-01-10 14:00:00 | fotmob:5868200 | Valencia / `abc511a4-c4c4-550d-9591-edf4ee39b838` / 134-245 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | O / DONE |
| `b0cbb1f0-0425-5bff-ac61-b4fcfce8ae8a` / 2027-01-10 15:30:00 | fotmob:5975173 | Port City / `eace79b0-415c-5d1e-92e1-f75568c227b0` / 0-6 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | O / FR-001 |
| `2e18706e-f0f4-5ead-b754-a86cdf06239d` / 2027-01-16 08:30:00 | fotmob:6280651 | City Club / `7c545aa8-34d3-5777-a57f-59aa43981ffb` / 4-4 | Fakirerpool / `3fc48514-8c43-54bc-bd0a-b74872dc349d` / 3-16 | O / FR-004 |
| `20b2a449-0936-5038-9446-60f42d1e1bb6` / 2027-01-16 15:00:00 | fotmob:5795619 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | Everton / `5bd977a1-a09d-5736-bf7c-4f4c085bb3b2` / 368-532 | O / DONE |
| `18c5f1a6-535e-568a-b325-2b2beead0535` / 2027-01-17 13:00:00 | fotmob:5934596 | Werder Bremen W / `f2008d01-a911-5bf4-9bac-12047597b323` / 116-207 | Mainz 05 W / `b2fe7f6a-e75a-56f1-9269-f78b2aaf9847` / 7-10 | O / FR-003 |
| `058db7a8-cd12-5e83-9c87-e3a9842e0c7e` / 2027-01-17 14:00:00 | fotmob:5868207 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | Real Madrid / `43910c10-4f86-59ad-a5c2-00ad0c642441` / 146-258 | O / DONE |
| `10c0fd06-ef0b-5447-ae38-1d6e03a706a6` / 2027-01-17 15:30:00 | fotmob:5975182 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | Vision / `1b287e66-be79-5daa-8dc9-131a1c5ec223` / 57-95 | O / FR-001 |
| `f261b159-3dfc-535e-a267-1bea722aff2e` / 2027-01-22 08:30:00 | fotmob:6280654 | Fortis / `522abbc4-a922-5182-9e5c-9454822a87e8` / 10-47 | Fakirerpool / `3fc48514-8c43-54bc-bd0a-b74872dc349d` / 3-16 | O / FR-003 |
| `5bd0f3b0-30b3-52ac-959e-4c67a69c3b57` / 2027-01-23 15:00:00 | fotmob:5795634 | Sunderland / `fd513e15-8e14-5643-9689-a3eb609661b2` / 177-283 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | O / DONE |
| `0cb391b0-90fd-540f-ab63-b58e41693136` / 2027-01-24 15:30:00 | fotmob:5975191 | Port City / `eace79b0-415c-5d1e-92e1-f75568c227b0` / 0-6 | Bibiani Gold Stars / `f2451bfd-22b2-531a-8eed-d87272b8cfc1` / 133-239 | O / FR-001 |
| `9c8dc408-c2d4-57c9-8bbc-2fb263d5c53e` / 2027-01-28 20:00:00 | fotmob:6112275 | Marseille / `ad2ed99a-0412-5051-b435-a65e35282e03` / 7-7 | Anderlecht / `79f7a4ea-c6d7-57f5-a9de-52e44d6df422` / 14-15 | O / FR-004 |
| `64178e6e-427b-5f39-9394-f8296e3db3d8` / 2027-01-30 13:45:00 | fotmob:5886631 | Fleury 91 / `0945686a-c71b-5a8c-9661-e350b909f733` / 15-43 | Cannes / `25b4e16e-98ec-5190-9592-19c198a2fe44` / 4-11 | O / FR-003 |
| `11a877c4-b63f-554a-809c-c0c53d72f0b5` / 2027-01-30 15:00:00 | fotmob:5795639 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | Leeds / `e15d5f29-ee93-54cf-a6ce-c66ea52c1ffd` / 111-139 | O / DONE |
| `ce15f2c4-f406-555e-99a0-318ac5ba412e` / 2027-01-31 13:00:00 | fotmob:5934608 | FC Koln W / `c944da01-1cba-5e7a-8e4f-ad92e112175f` / 99-174 | Mainz 05 W / `b2fe7f6a-e75a-56f1-9269-f78b2aaf9847` / 7-10 | O / FR-003 |
| `77825ca8-faef-5e3f-bdbc-1450b1efb852` / 2027-01-31 15:30:00 | fotmob:5975195 | Bechem United / `6caa924c-7272-5c7b-a1c4-49b7b7e4a288` / 149-281 | Port City / `eace79b0-415c-5d1e-92e1-f75568c227b0` / 0-6 | O / FR-001 |
| `bc1306d0-4272-5a63-8231-c3b677e2dc30` / 2027-02-06 15:00:00 | fotmob:5795647 | Crystal Palace / `edd9a29a-13b2-5a98-835c-ae7510fdd86d` / 316-449 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | O / DONE |
| `439c55ee-d4e0-502f-b9f7-ab24e3abd1d8` / 2027-02-07 13:00:00 | fotmob:5934616 | Mainz 05 W / `b2fe7f6a-e75a-56f1-9269-f78b2aaf9847` / 7-10 | SC Freiburg W / `1fe446c3-7069-5aed-abd2-a879bfd359ee` / 118-209 | O / FR-003 |
| `9382a85c-a634-53ff-a87c-22b87ac67e9d` / 2027-02-07 15:30:00 | fotmob:5975207 | Heart of Lions / `0cefceda-3545-5128-942b-95cc50b54d9d` / 86-146 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | O / FR-001 |
| `d6cddf67-15ca-52ab-b989-2d9e5311b1d9` / 2027-02-07 15:30:00 | fotmob:5975209 | Port City / `eace79b0-415c-5d1e-92e1-f75568c227b0` / 0-6 | Hearts of Oak / `69b1eff6-4bc6-5da8-9340-fb99e652e82d` / 147-282 | O / FR-001 |
| `893a35c2-9d88-53fb-9a4a-83925c2acf02` / 2027-02-10 20:00:00 | fotmob:5795656 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | Liverpool / `a1885e25-3c5b-53da-885f-09ef2e2d01cb` / 412-539 | O / DONE |
| `5c26d7b2-7980-56e4-971c-f146ad06ed34` / 2027-02-14 15:30:00 | fotmob:5975219 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | Samartex / `6a1d3c79-8845-5076-aff7-2e7d6731b892` / 108-193 | O / FR-001 |
| `92f2b2db-7184-5e5a-a96e-9e4cfe3c436f` / 2027-02-14 15:30:00 | fotmob:5975216 | Dreams / `9d1e589e-0a30-5cb6-a392-d8e8bd34155f` / 149-282 | Port City / `eace79b0-415c-5d1e-92e1-f75568c227b0` / 0-6 | O / FR-001 |
| `73a81a17-2911-573b-afc5-0f642948eba1` / 2027-02-19 13:30:00 | fotmob:6012002 | Dewa United / `cafe4c99-e6dd-50de-b2c2-e912d9ac8cfa` / 77-179 | Garudayaksa / `b8c2ba83-f1d3-5b68-9b83-4a11ccd94462` / 5-9 | O / FR-004 |
| `8e8baf76-f72e-5351-848b-6cf4b79cdb3c` / 2027-02-20 13:45:00 | fotmob:5886657 | Cannes / `25b4e16e-98ec-5190-9592-19c198a2fe44` / 4-11 | Versailles / `64fb1f81-56db-50a0-b7cb-de33c41ac687` / 78-183 | O / FR-003 |
| `6c630562-cdb4-5eea-85ba-774abc0ec050` / 2027-02-20 15:00:00 | fotmob:5795667 | Brentford / `73f1706b-973b-54a6-aad7-c80ef9d55e73` / 168-175 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | O / DONE |
| `786fc70c-3e4d-55fb-8386-5ff01de19c73` / 2027-02-20 16:00:00 | fotmob:5973029 | Alashkert / `224cca8f-1a3d-599d-8d0d-3ebfbcbc078f` / 149-224 | Sardarapat / `96bb48e5-4015-516f-b2cd-168971de6bd3` / 10-14 | O / DONE |
| `6b335ee2-efbf-5eaa-aa7e-63520a9e1b96` / 2027-02-21 13:00:00 | fotmob:5934630 | Mainz 05 W / `b2fe7f6a-e75a-56f1-9269-f78b2aaf9847` / 7-10 | RB Leipzig W / `15b62852-73ea-5864-aa80-129b54e2809a` / 62-103 | O / FR-003 |
| `2e7f733e-85be-5630-958e-84b211368062` / 2027-02-21 14:00:00 | fotmob:5868257 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | Real Betis / `3a7f8fb1-b79b-52ef-a72b-02692ab5d0c3` / 151-262 | O / DONE |
| `18fbb65a-1f9f-58d6-b746-9a99f65f13d2` / 2027-02-21 15:30:00 | fotmob:5975221 | Aduana Stars / `83967452-69c8-5883-9fec-e5959e5d5901` / 147-281 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | O / FR-001 |
| `4b2f2df1-2ab4-50a5-9674-2847145b3d39` / 2027-02-23 13:30:00 | fotmob:6012009 | Garudayaksa / `b8c2ba83-f1d3-5b68-9b83-4a11ccd94462` / 5-9 | Persita / `3c57988d-ab8c-53fe-9922-660b6dfea18a` / 104-233 | O / FR-004 |
| `da5cb071-4036-5695-a96a-2b36eb6c3d64` / 2027-02-27 15:00:00 | fotmob:5795676 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | Bournemouth / `e28e7533-6931-5361-9129-7c2a5bae2aaa` / 228-307 | O / DONE |
| `700166bb-e7ec-5226-b592-e5d3fc1d2dce` / 2027-02-28 15:30:00 | fotmob:5975238 | Port City / `eace79b0-415c-5d1e-92e1-f75568c227b0` / 0-6 | Vision / `1b287e66-be79-5daa-8dc9-131a1c5ec223` / 57-95 | O / FR-001 |
| `136d0ecb-437d-53f8-949d-9d1e2dcadb80` / 2027-03-03 20:00:00 | fotmob:5795689 | Chelsea / `5ca3d524-59e8-5122-bfe8-b1cafdbf224e` / 384-549 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | O / DONE |
| `b4877745-4654-5d45-bbdf-873c8e1f263c` / 2027-03-05 16:00:00 | fotmob:5973045 | FC Noah / `4d0e19b9-11ea-5c8a-bfea-bdd32ff72dc7` / 167-245 | Sardarapat / `96bb48e5-4015-516f-b2cd-168971de6bd3` / 10-14 | O / DONE |
| `7414e20a-e2e9-57af-a548-04cff69b9963` / 2027-03-07 14:00:00 | fotmob:5868274 | Elche / `6f764036-fc28-535b-bf89-01e9d4a5c1dc` / 99-169 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | O / DONE |
| `270cfba7-be64-58b8-96c4-62152137c7f8` / 2027-03-11 16:00:00 | fotmob:5973049 | Sardarapat / `96bb48e5-4015-516f-b2cd-168971de6bd3` / 10-14 | Gandzasar / `58850c8a-be75-576b-9568-60244f126640` / 49-72 | O / DONE |
| `f6a54ff3-3482-5dca-8e3f-8fa196fec3ad` / 2027-03-13 15:00:00 | fotmob:5795698 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | Manchester City / `36b78199-4873-5fd7-b9a9-2eb0a9bd265a` / 377-542 | O / DONE |
| `cbadbd34-11af-5638-b9ba-74694f2935f2` / 2027-03-14 14:00:00 | fotmob:5868287 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | Rayo Vallecano / `6390f775-dda9-5bc5-ac14-fee4910a39c6` / 116-204 | O / DONE |
| `163e63bf-8f8b-5fc0-8f4d-dd1527a8de0b` / 2027-03-14 15:30:00 | fotmob:5975254 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | Young Apostles / `54b9ed3b-35e5-53c0-99a6-0f20c5fbfe8d` / 58-98 | O / FR-001 |
| `75fa0f14-2156-5f6e-ab4e-e471fa99e693` / 2027-03-19 16:00:00 | fotmob:5973058 | FC Urartu / `6f6e92d0-4ace-5939-b586-06caa8eb0442` / 155-230 | Sardarapat / `96bb48e5-4015-516f-b2cd-168971de6bd3` / 10-14 | O / DONE |
| `0071f536-b420-5d9f-9369-e14f5fdbda4a` / 2027-03-20 13:45:00 | fotmob:5886695 | Quevilly / `dda9832d-a43a-5cad-bb08-bce46b2df782` / 150-265 | Cannes / `25b4e16e-98ec-5190-9592-19c198a2fe44` / 4-11 | O / FR-003 |
| `6e5070e7-4a94-53d9-9090-656572d61bcc` / 2027-03-20 15:00:00 | fotmob:5795707 | Brighton / `dd7c8452-e0f0-5882-b702-6805e3c5a6d3` / 232-299 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | O / DONE |
| `331b415e-99ce-5c4e-93f7-385e61f47890` / 2027-03-20 16:00:00 | fotmob:5766025 | HNK Gorica / `a284e8f5-4c67-5703-84fa-7f655614efd4` / 40-261 | Rudes / `5d0e7079-5a62-5e61-9688-a256fd4ced36` / 9-50 | O / FR-003 |
| `63d8a8c2-bc3a-5d98-b969-8c68b57f61bf` / 2027-03-21 14:00:00 | fotmob:5868300 | Villarreal / `b5bc8a96-634c-56a0-b7eb-14a3b7f3fcde` / 132-244 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | O / DONE |
| `63bcfa26-66d6-5d06-8ff5-2f90e7343b81` / 2027-03-21 15:30:00 | fotmob:5975261 | Heart of Lions / `0cefceda-3545-5128-942b-95cc50b54d9d` / 86-146 | Port City / `eace79b0-415c-5d1e-92e1-f75568c227b0` / 0-6 | O / FR-001 |
| `b23c0761-115a-5b4f-bf01-93b552777de7` / 2027-03-21 15:30:00 | fotmob:5975259 | Ashanti Gold / `6731d927-6bd0-5ca3-8ca1-f5eb53227b35` / 46-100 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | O / FR-001 |
| `b5210fad-6987-58dc-8b32-ba9cf0c118ef` / 2027-03-28 15:30:00 | fotmob:5975273 | Port City / `eace79b0-415c-5d1e-92e1-f75568c227b0` / 0-6 | Samartex / `6a1d3c79-8845-5076-aff7-2e7d6731b892` / 108-193 | O / FR-001 |
| `039f6ead-2851-5fe0-91db-91265a8cbb81` / 2027-04-02 15:00:00 | fotmob:5973064 | Van / `8ac7c0fb-1ded-57ea-b136-c44422b6faa4` / 153-230 | Sardarapat / `96bb48e5-4015-516f-b2cd-168971de6bd3` / 10-14 | O / DONE |
| `2d82451c-ef21-58d4-8693-9320947edee1` / 2027-04-03 12:45:00 | fotmob:5886715 | Valenciennes / `5d4fc0e8-5b0b-5567-a552-409907afefb3` / 155-256 | Cannes / `25b4e16e-98ec-5190-9592-19c198a2fe44` / 4-11 | O / FR-003 |
| `286fcab5-190e-5a3e-ba40-3af15211fd75` / 2027-04-04 13:00:00 | fotmob:5868308 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | Osasuna / `6f0c35ce-3661-5f04-b414-78a649a58f92` / 134-243 | O / DONE |
| `97838bfd-38e5-5cec-9bc5-55762cb77a19` / 2027-04-04 15:30:00 | fotmob:5975275 | Aduana Stars / `83967452-69c8-5883-9fec-e5959e5d5901` / 147-281 | Port City / `eace79b0-415c-5d1e-92e1-f75568c227b0` / 0-6 | O / FR-001 |
| `cac0e260-fca6-583b-9007-fb20499a2e8f` / 2027-04-08 15:00:00 | fotmob:5973066 | Ararat / `bded9ee7-f354-58c9-b986-85792734ae2c` / 147-223 | Sardarapat / `96bb48e5-4015-516f-b2cd-168971de6bd3` / 10-14 | O / DONE |
| `844f68e6-e669-5c2f-946a-97ccb11135a0` / 2027-04-10 14:00:00 | fotmob:5795718 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | Arsenal / `a230dc08-aa98-5d93-a0fd-d5b072629d4a` / 382-549 | O / DONE |
| `bef48b24-2fc7-58b6-af1c-21aa5f9db710` / 2027-04-11 13:00:00 | fotmob:5868314 | Espanyol / `5a035417-0e1b-50f6-b744-406a69a5a2e4` / 96-166 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | O / DONE |
| `a847dbdb-484d-547b-856b-5ac38c522127` / 2027-04-11 15:30:00 | fotmob:5975285 | Bibiani Gold Stars / `f2451bfd-22b2-531a-8eed-d87272b8cfc1` / 133-239 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | O / FR-001 |
| `2656698a-f4ad-5257-bee1-3116972b1d8b` / 2027-04-16 12:00:00 | fotmob:6012055 | Garudayaksa / `b8c2ba83-f1d3-5b68-9b83-4a11ccd94462` / 5-9 | Persebaya Surabaya / `d3cbaef6-4dfd-5d06-b9ce-51ebf64e6693` / 104-233 | O / FR-004 |
| `ce9cb231-9365-58be-bac1-0a848c15036b` / 2027-04-17 14:00:00 | fotmob:5795730 | Hull City / `962cd542-ddf7-5747-b6e6-6f2636c1c057` / 70-110 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | O / DONE |
| `fc13afe8-3b9a-5255-8e47-0169fb1b5211` / 2027-04-18 13:00:00 | fotmob:5868329 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | Valencia / `abc511a4-c4c4-550d-9591-edf4ee39b838` / 134-245 | O / DONE |
| `c6391ca0-df34-5033-bf98-5f807641ffd5` / 2027-04-18 15:30:00 | fotmob:5975298 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | Bechem United / `6caa924c-7272-5c7b-a1c4-49b7b7e4a288` / 149-281 | O / FR-001 |
| `061df4ee-d112-509d-943f-d2f72f1acbd0` / 2027-04-21 13:00:00 | fotmob:5868336 | Racing Santander / `af094f15-ddd5-53f7-a207-245889651717` / 15-16 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | O / DONE |
| `cea9c767-4c24-57f5-b952-6c9167c76c19` / 2027-04-21 15:00:00 | fotmob:5973079 | Ararat-Armenia / `35185df7-f3bb-578a-8c5e-3d6528b19b19` / 161-237 | Sardarapat / `96bb48e5-4015-516f-b2cd-168971de6bd3` / 10-14 | O / DONE |
| `de6f5ec9-d773-5b38-a35f-a508de7e4b27` / 2027-04-24 08:30:00 | fotmob:6012067 | PSS Sleman / `2e7cca9b-5cf2-5cd5-9bd7-24f37b7cd4bd` / 98-199 | Garudayaksa / `b8c2ba83-f1d3-5b68-9b83-4a11ccd94462` / 5-9 | O / FR-004 |
| `966a19c9-f7f6-5720-857c-b01c88703abc` / 2027-04-24 12:45:00 | fotmob:5886737 | Cannes / `25b4e16e-98ec-5190-9592-19c198a2fe44` / 4-11 | Caen / `774fb06f-210e-580c-a8d8-a253d0d89bb8` / 146-247 | O / FR-003 |
| `d95f18eb-5016-5596-9948-c47efd62609e` / 2027-04-24 14:00:00 | fotmob:5795736 | Aston Villa / `9648865b-e6be-56cf-9c84-fefa3cb3f978` / 322-449 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | O / DONE |
| `55180f12-e3a9-5f0e-aad7-a5655f79aca1` / 2027-04-25 15:30:00 | fotmob:5975307 | Hearts of Oak / `69b1eff6-4bc6-5da8-9340-fb99e652e82d` / 147-282 | Medeama / `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` / 0-210 | O / FR-001 |
| `74fe2710-563e-5fa4-b4da-38053eb6f76b` / 2027-04-25 15:30:00 | fotmob:5975309 | Port City / `eace79b0-415c-5d1e-92e1-f75568c227b0` / 0-6 | Young Apostles / `54b9ed3b-35e5-53c0-99a6-0f20c5fbfe8d` / 58-98 | O / FR-001 |
| `b94d9c82-a8c9-545b-8aa6-e7ca7e24f697` / 2027-05-01 14:00:00 | fotmob:5795747 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | Manchester United / `fcefd735-1779-555e-800f-e700d5b89abd` / 382-547 | O / DONE |
| `e4863a2c-143e-5edf-898e-a54a797365b8` / 2027-05-02 13:00:00 | fotmob:5868348 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | Getafe / `0d2d1cbf-3c3d-5efa-9701-8f79fcf27855` / 136-245 | O / DONE |
| `1e9ed334-7feb-5df7-95de-6b1e5e0441b0` / 2027-05-04 12:00:00 | fotmob:6012087 | Persib Bandung / `c0f025fa-15a9-5a47-8141-84004c9ab2ef` / 112-260 | Garudayaksa / `b8c2ba83-f1d3-5b68-9b83-4a11ccd94462` / 5-9 | O / FR-004 |
| `d31bad0a-f037-58d1-b237-747474e8f1ec` / 2027-05-06 15:00:00 | fotmob:5973098 | Sardarapat / `96bb48e5-4015-516f-b2cd-168971de6bd3` / 10-14 | Alashkert / `224cca8f-1a3d-599d-8d0d-3ebfbcbc078f` / 149-224 | O / DONE |
| `a366d3e4-4000-5112-a6c7-192a62100df9` / 2027-05-08 14:00:00 | fotmob:5795775 | Newcastle United FC / `3770524c-2472-5209-b9a7-7b524a9cc78a` / 60-686 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | O / DONE |
| `78a9dada-5612-5afb-a47c-08c523f3404f` / 2027-05-09 13:00:00 | fotmob:5868352 | Athletic Club / `692958c4-2052-5296-8b1f-8ae7c179cbe8` / 142-252 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | O / DONE |
| `85d2155b-98bb-514b-91f3-3793c7e7439c` / 2027-05-15 12:00:00 | fotmob:6012107 | Isenmulang Kalteng / `4cd979f6-e5f7-5329-8ae4-8e97891f8bd6` / 25-31 | Garudayaksa / `b8c2ba83-f1d3-5b68-9b83-4a11ccd94462` / 5-9 | O / FR-004 |
| `860db880-9194-5397-a5f3-4a03e3d0e8d0` / 2027-05-15 14:00:00 | fotmob:5795781 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | Tottenham / `99bdab6f-afd6-5beb-bae4-b20dbaf611df` / 382-548 | O / DONE |
| `7c6450f4-33f9-50ee-af45-116c31c57973` / 2027-05-16 13:00:00 | fotmob:5868366 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | Celta Vigo / `04e2160f-0800-56e5-879c-167ed4e10f2f` / 140-257 | O / DONE |
| `0f3324ba-a46e-5de2-a65c-854a070b0f92` / 2027-05-18 15:00:00 | fotmob:5973109 | Sardarapat / `96bb48e5-4015-516f-b2cd-168971de6bd3` / 10-14 | FC Noah / `4d0e19b9-11ea-5c8a-bfea-bdd32ff72dc7` / 167-245 | O / DONE |
| `9264f046-f29e-5582-928f-bd28671722f0` / 2027-05-22 12:00:00 | fotmob:6012112 | Garudayaksa / `b8c2ba83-f1d3-5b68-9b83-4a11ccd94462` / 5-9 | PSM Makassar / `d8696dff-e8e3-5970-a552-ba68262b3990` / 115-254 | O / FR-004 |
| `d34449e4-d8c4-5217-bfd3-63e2262f4f41` / 2027-05-22 15:00:00 | fotmob:5766073 | Rudes / `5d0e7079-5a62-5e61-9688-a256fd4ced36` / 9-50 | HNK Gorica / `a284e8f5-4c67-5703-84fa-7f655614efd4` / 40-261 | O / FR-003 |
| `7ca27d51-20ac-5721-a490-708f56c1e7ed` / 2027-05-23 12:00:00 | fotmob:5934675 | Bayer Leverkusen W / `6c6ae2d5-37e3-513a-95d8-368d2caee99d` / 116-209 | Mainz 05 W / `b2fe7f6a-e75a-56f1-9269-f78b2aaf9847` / 7-10 | O / FR-003 |
| `c6ccc91c-2067-5091-b7f2-9de15c51dbdc` / 2027-05-23 13:00:00 | fotmob:5868375 | Barcelona / `2ba95686-80aa-560a-8b9e-c46f6fdbf053` / 148-258 | Malaga / `f89ad343-fd17-59b7-b4fe-4536e58e7f8f` / 32-50 | O / DONE |
| `531d6e01-c52b-50d0-9214-afa71a5c43bf` / 2027-05-23 14:00:00 | fotmob:5795792 | Fulham / `77411915-21c9-5eae-9c1d-0633f76e075e` / 248-340 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | O / DONE |
| `e990d33c-c70b-50b1-b3da-0fcff8d5c2c5` / 2027-05-23 15:00:00 | fotmob:5973116 | Gandzasar / `58850c8a-be75-576b-9568-60244f126640` / 49-72 | Sardarapat / `96bb48e5-4015-516f-b2cd-168971de6bd3` / 10-14 | O / DONE |
| `8d30924c-a64e-5a96-ad69-fd54db62a5a1` / 2027-05-28 15:00:00 | fotmob:5973121 | Sardarapat / `96bb48e5-4015-516f-b2cd-168971de6bd3` / 10-14 | FC Urartu / `6f6e92d0-4ace-5939-b586-06caa8eb0442` / 155-230 | O / DONE |
| `62b5ad98-ec43-5555-93a9-3c0ffbcc1490` / 2027-05-30 15:00:00 | fotmob:5795801 | Coventry City FC / `21c6f977-cea1-5551-bb07-8ff204ddbf26` / 45-49 | Nottingham Forest / `b183150a-bcef-5b34-b406-bd8b55f8e005` / 129-147 | O / DONE |

## Appendix B. Mapping, source and integrity inventories

### Scottish current World mappings

All 41 current rows below retain stored ORIGIN_ANCHOR but fresh corrected-parser verification returns UNRESOLVED. This is the expanded current set; 30 labels occur in the pinned 2000/01 archive. Native IDs are labels in this provider, so country/period evidence remains essential.

| Provider team ID | Mapping ID | MatchForge team ID |
| --- | --- | --- |
| Airdrie | `01a0f3bd-b29a-76a5-8c98-dfd623ce81f9` | `5b2de215-0535-528e-8e9b-5d4de5adf466` |
| Airdrie Utd | `01a0f3bf-1d72-7f86-9ba4-4f8f6d47072e` | `4dcd62b3-e174-5ea0-add6-5d6cf6202a6e` |
| Albion Rvs | `01a0f3bd-b649-76e7-a092-86f00886f5c4` | `08d8b042-e740-5d24-b06d-bc83aad6d8d3` |
| Alloa | `01a0f3bd-b2a3-73a9-bba4-7f21eb68d9a1` | `38dbf69f-513c-5b4f-99b3-c5b8d56acf43` |
| Annan Athletic | `01a0f3c4-2797-7b3f-add1-99b79ffe2fb0` | `ef113d64-ce47-5ce6-aa6b-8eea1d754916` |
| Arbroath | `01a0f3bd-b46e-7450-94f8-b1e45da31ee5` | `1dc83978-1241-53a0-a771-16e546f6a567` |
| Ayr | `01a0f3bd-b290-7dfd-90a7-b13948cb1bbe` | `2b566a39-ec5d-538b-ae2d-b565fcc5dd3b` |
| Berwick | `01a0f3bd-b474-7daa-b448-13a235f60990` | `5ed26603-823b-5189-9d22-2c8c67dff1b8` |
| Bonnyrigg Rose | `01a0f3d2-1359-7063-9aa9-16befc275b2a` | `50f4c343-046b-5481-8318-ab736cc3b094` |
| Brechin | `01a0f3bd-b64e-7de2-be42-5ab5f4a0226b` | `e543ae09-78ce-5827-b5d1-c6840a8a88f7` |
| Clyde | `01a0f3bd-b295-7541-9909-c509133293c6` | `dfac365d-03e2-51f1-9aad-799b56c69fc3` |
| Clydebank | `01a0f3bd-b47d-7805-9235-24fe27526e62` | `13cd2a72-6d1d-5ce9-838c-3c1f32206b49` |
| Cove Rangers | `01a0f3ce-dfd4-7f4d-8b74-1813b20ee01e` | `5cb8bc44-705e-58e2-8e9d-b1ddb8201a2c` |
| Cowdenbeath | `01a0f3bd-b655-763a-80f8-90705c1f2dc5` | `16c3ac53-0171-5e62-b2d7-70758698eff7` |
| Dumbarton | `01a0f3bd-b65a-7f56-866e-de824e320a66` | `9ddd3806-9033-5ccc-8c2c-e5d02e8bafaa` |
| East Fife | `01a0f3bd-b64a-7f3b-a13f-80f12e3b0743` | `7b47eae4-2404-510e-89b6-44bfc65e12dc` |
| East Kilbride | `01a0f3d5-6285-791a-add0-535ece8a8368` | `be08b654-fd29-57c8-bc85-de9470ddbfcf` |
| East Stirling | `01a0f3bd-b653-7d70-b7ae-55cf311c7ed8` | `7fd73d77-82d6-5416-a030-4f452a057b10` |
| Edinburgh City | `01a0f3cb-dc49-7071-b73e-76997003d7f9` | `3cf98ddc-bab5-5c3d-b7b9-61cb30a21074` |
| Elgin | `01a0f3bd-b650-770f-a724-d5cf92296171` | `20193503-8d8b-5a21-bc05-a2dfca78627c` |
| Falkirk | `01a0f3bd-b296-7542-9d2f-b5d19abe02eb` | `f2c099cf-2e1e-5548-93bf-d95a2496e5c2` |
| FC Edinburgh | `01a0f3d2-101e-7b17-b781-1466d862bb64` | `7a2579f6-aef9-573e-8693-ded028bb422e` |
| Forfar | `01a0f3bd-b481-7a22-8ae1-698685044e8f` | `d3bb2f86-9d6a-5850-b4c4-d550015716c6` |
| Gretna | `01a0f3bf-2020-7092-a97f-3c3785c1a1af` | `8f3ad23b-8033-53e0-8077-c6131360bba0` |
| Hamilton | `01a0f3bd-b659-7310-9540-8fcd283d40f5` | `bf3c185b-9bee-510b-9e86-5f49bc5808c5` |
| Inverness C | `01a0f3bd-b299-72b6-ac75-bed29e30504d` | `b71255ec-d72c-5eba-b7de-31b9f3aaeccc` |
| Kelty Hearts | `01a0f3d0-fb16-71fe-81ec-ab7151403155` | `27e06111-4681-5f39-aaec-34333ce2508b` |
| Livingston | `01a0f3bd-b29e-7880-9a82-69908828d9c7` | `f814b078-0308-5996-8819-8428d988123c` |
| Montrose | `01a0f3bd-b660-758d-a875-4c0932a8cfda` | `fb646e41-d479-5a06-9ec4-58379f07dba0` |
| Morton | `01a0f3bd-b29d-742c-a300-c321f3ae56e6` | `df5014b6-1362-57fe-891e-c66b3fa702e3` |
| Partick | `01a0f3bd-b46f-7d68-9df2-b171dd98404c` | `fba5be4d-a1d8-5704-b30e-c12d9b3d22f1` |
| Peterhead | `01a0f3bd-b65e-7c33-89e9-d82e1a4491a9` | `9929afdf-3391-53b1-b6bd-729f6bdd3b87` |
| Queen of Sth | `01a0f3bd-b479-74f9-b7ce-1e7f0dfe1710` | `28eeee93-2556-59bb-ae6d-92e2f969a815` |
| Queens Park | `01a0f3bd-b473-7884-9114-49fb50979939` | `1ab37fda-7f51-5a3d-ba80-31ca40695113` |
| Raith | `01a0f3c0-af45-777c-a7ea-0216922ff01b` | `9f8b6db1-d3b3-5db9-97be-2150506af8ba` |
| Raith Rvs | `01a0f3bd-b2a1-7bfb-b286-5cb4a2561724` | `283f88d4-462a-56d8-a91e-2c37672e39a2` |
| Ross County | `01a0f3bd-b292-71fa-b683-e5d70ce704e8` | `f43e0dbd-0d1c-527e-894c-1bb4240ef8a8` |
| Spartans | `01a0f3d3-3389-7578-9590-f8dc0b9c0451` | `29c98c66-6d9c-5c10-a971-2dbbeb8abc7c` |
| Stenhousemuir | `01a0f3bd-b478-740b-9fa9-a944e414ea75` | `b04f9521-625f-5127-bf31-c3c04e51a30a` |
| Stirling | `01a0f3bd-b47c-7735-be50-c1e02cfabee7` | `5b428309-48ee-5e99-85ca-0de329242bc6` |
| Stranraer | `01a0f3bd-b480-7656-9887-6550221bbf57` | `3788030d-951e-5f58-87b3-8bdb73328490` |

### Ghana mapping generations

Closed and current mapping records are retained separately. Current four source-backed admissions verify as two ORIGIN_ANCHOR and two CROSSWALK in the final read.

| Team / provider / native ID | Mapping ID | MatchForge team ID | State |
| --- | --- | --- | --- |
| Medeama / api_football / 12255 | `01a1422c-9686-7f50-9dae-616b6d13b26b` | `95464491-fd01-54e3-b2bf-4994571d86d2` | CURRENT ORIGIN_ANCHOR |
| Medeama / api_football / 12255 | `01a0eef4-a758-78c5-a351-24f566d97061` | `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` | CLOSED 2026-10-16 00:46:20.757404+00:00 |
| Medeama / fotmob / 106975 | `01a14230-cade-7a4a-b79e-6d53984decf4` | `95464491-fd01-54e3-b2bf-4994571d86d2` | CURRENT CROSSWALK |
| Medeama / fotmob / 106975 | `01a12ac1-490f-7548-8e0f-4c3df7a839a5` | `a2c3853c-e62b-5e64-8260-1ddf9a3899d2` | CLOSED 2026-10-16 00:50:56.222825+00:00 |
| Port City / api_football / 26805 | `01a1422c-9940-7940-ba67-b8d00b29aebd` | `6bcd1a34-f170-56a4-8901-32bb82e88847` | CURRENT ORIGIN_ANCHOR |
| Port City / api_football / 26805 | `01a0eef4-a759-7b02-ba59-96426365c4b9` | `eace79b0-415c-5d1e-92e1-f75568c227b0` | CLOSED 2026-10-16 00:46:21.460775+00:00 |
| Port City / fotmob / 2103806 | `01a14230-cd0a-76d8-bfe0-0c088e6cbdf7` | `6bcd1a34-f170-56a4-8901-32bb82e88847` | CURRENT CROSSWALK |
| Port City / fotmob / 2103806 | `01a12ac1-4903-79bc-a5a7-8353dc4edd48` | `eace79b0-415c-5d1e-92e1-f75568c227b0` | CLOSED 2026-10-16 00:50:56.875162+00:00 |

### Rejected native recovery inputs

The existing `.local/provider-wide-acquisition/target-recovery-operating.json` receipt binds these source responses. No new acquisition occurred here.

| Provider | Source snapshot | Resource SHA-256 | Remaining qualification |
| --- | --- | --- | --- |
| football_data_org | `080c9e2f-037a-57b0-b3f9-49ab726125f8` | `1127cc75acd1a7c78dc4948865597a85ef967f58ced2ed4370ac424b294b446a` | 46 selected Coventry rows not imported; earlier retained history recovered separately |
| api_football | `6e172d9e-5343-5c9a-9eb6-3287c44c5152` | `9c6841462d0b4697c90085227d9b5e78ccf7f1741dea5a833163a1d26a74ad42` | Two rejected native rows 1217677 / 1217899 |

### Suspect registered source resources

The legacy-aware resource check returns BLOCKED for the following 33 resource IDs. The exact registered path/hash and provider are in `integrity-followup.json`. Repeated c/f hashes are a warning about registration provenance, not a replacement payload.

| Resource ID | Source snapshot ID | Registered checksum pattern |
| --- | --- | --- |
| `01a06fc4-d5b5-7386-bd19-1c972e3df61d` | `01a06fc4-d5b1-78b7-b24d-ec4d69c4543d` | `f` repeated 64 times |
| `01a06fc4-d5ed-740f-abb0-ced7684f41c1` | `01a06fc4-d5ec-79a3-b558-d9e35361856b` | `c` repeated 64 times |
| `01a06fc4-d5fd-7e1f-97e6-e64caa810ac5` | `01a06fc4-d5fd-73de-98ba-6cd18fa1d803` | `c` repeated 64 times |
| `01a06fc4-d67b-7663-b440-26ad852f6c56` | `01a06fc4-d67a-7b30-8cdb-f9efb84b36fc` | `c` repeated 64 times |
| `01a04db4-fb6d-719e-8ecc-5c8411bdd3bc` | `01a04db4-fb6b-7e5e-a613-bc19191e4e5a` | `c` repeated 64 times |
| `01a051c0-2b85-7eda-8826-6118450cedeb` | `01a051c0-2b80-7394-ac08-fb1132a56fe6` | `c` repeated 64 times |
| `01a051c4-88dc-742c-9c9d-5e416bffa63b` | `01a051c4-88da-7a9f-a852-c64e3a1ff459` | `c` repeated 64 times |
| `01a06fc4-d554-7482-900b-c671252fddb5` | `01a06fc4-d550-78c4-8296-a38a0833b0d8` | `c` repeated 64 times |
| `01a06fc4-d584-7f0e-be0b-9d67f1f4c7f1` | `01a06fc4-d584-7902-b70c-f60250ac661a` | `f` repeated 64 times |
| `01a06fc4-d5b8-74c5-be3d-bd8d81361eb8` | `01a06fc4-d5b7-7e9b-83d7-c0c58ff2a5e7` | `f` repeated 64 times |
| `01a06fc4-d623-7d0d-98fa-5507c99deb1a` | `01a06fc4-d622-75d9-bb9d-04a47154256c` | `c` repeated 64 times |
| `01a06fc4-d649-75fd-aecf-3902bbb0542d` | `01a06fc4-d648-7d42-aaf2-b3ca5621e5a3` | `c` repeated 64 times |
| `01a05718-f3e5-709d-8b73-96ac7b2e7a63` | `01a05718-f3d0-799b-8499-77bdc422010d` | `c` repeated 64 times |
| `01a04fc0-1018-774c-89b1-fa3285959dc7` | `01a04fc0-1015-75d2-995a-307f74431133` | `c` repeated 64 times |
| `01a04db8-2440-76a7-87bb-bacd660f7e38` | `01a04db8-243e-728d-824e-4cbaa7be65e1` | `c` repeated 64 times |
| `01a051c0-2bba-79ad-bce2-e8e4ac91fcbb` | `01a051c0-2bb9-7246-9cf9-a73e91f7305a` | `c` repeated 64 times |
| `01a051c4-88aa-7535-b639-b2d79100cc42` | `01a051c4-88a8-706c-9322-e6db27b554f6` | `c` repeated 64 times |
| `01a051c4-8905-7609-885a-63bbf6c1e5c1` | `01a051c4-8903-7e88-b132-81fa7c75063d` | `c` repeated 64 times |
| `01a06fc4-d746-7342-9f1a-59d48d423e0d` | `01a06fc4-d742-7c0b-a213-e6187c1741f6` | `c` repeated 64 times |
| `01a06fc4-d7e5-7138-8611-f031e2d83326` | `01a06fc4-d7e4-74c1-92d8-5cab0c8536fe` | `c` repeated 64 times |
| `01a06fc4-d64a-71f0-8e93-ed297ced8c56` | `01a06fc4-d649-7dd3-a2f7-a4ed3cebc2b8` | `c` repeated 64 times |
| `01a06fc4-d6af-747f-abbd-132e26237aae` | `01a06fc4-d6ae-7975-a116-ef1cadc75d4f` | `c` repeated 64 times |
| `01a04db8-2442-78d8-8e17-2a06e5e00cde` | `01a04db8-2441-7dea-9789-8b8d5c59cd28` | `c` repeated 64 times |
| `01a04fc8-d210-7af0-bdab-f51b0a6a2d2b` | `01a04fc8-d20e-74aa-a6ec-8717935dde9d` | `c` repeated 64 times |
| `01a051c0-2be1-7ffe-abf8-509643d03ee0` | `01a051c0-2be1-758d-9532-1fefd53ecf0f` | `c` repeated 64 times |
| `01a06fc4-d801-71c9-b388-0d26a491e9e2` | `01a06fc4-d800-74d2-bf1d-ab33a5868825` | `c` repeated 64 times |
| `01a06fc4-d7e6-7356-bf4c-cdf19d9838ba` | `01a06fc4-d7e5-7e2a-b469-e05a06717951` | `c` repeated 64 times |
| `01a06fc4-d583-7c57-a31b-a6c09db2e8d5` | `01a06fc4-d582-7e87-aeb3-b593f68fe209` | `c` repeated 64 times |
| `01a06fc4-d5a7-7e0f-ac42-65ff4b9c883b` | `01a06fc4-d5a4-780c-a6dd-0c8b6e3fa49b` | `c` repeated 64 times |
| `01a06fc4-d65c-7d59-87b5-942f9b2c01ec` | `01a06fc4-d65c-7320-bd55-e0ebd755613b` | `c` repeated 64 times |
| `01a04db4-fb69-7f6d-921b-4ee6615ca179` | `01a04db4-fb68-71d8-b6e1-c790ee3a5aa3` | `c` repeated 64 times |
| `01a04fc8-2e55-7896-8e30-96d893fa2879` | `01a04fc8-2e52-7ff5-a7d5-9ae77ebf9605` | `c` repeated 64 times |
| `01a04fd2-a0a2-7f5b-955d-094aa6b85041` | `01a04fd2-a09f-746a-ad99-4f7252900ae2` | `c` repeated 64 times |

### Dataset/model missing-manifest registrations

Dataset results use the existing full dataset verifier; model checks here establish manifest absence and exact forecast dependency links, without rerunning any fit or all other model logical verifications. The thirteen dependent forecast IDs follow the table.

| Kind | Registration ID | Registered manifest path |
| --- | --- | --- |
| Dataset | `01a04fc0-101b-7125-a6a3-82e611bb0ef8` | `manifests/01a04fc0-101b-7125-a6a3-82e611bb0ef8.json` |
| Dataset | `01a04fc8-2e57-732a-8cfe-a14064909ca9` | `manifests/01a04fc8-2e57-732a-8cfe-a14064909ca9.json` |
| Dataset | `01a04fc8-d211-7bf3-91f8-2abe9fed2866` | `manifests/01a04fc8-d211-7bf3-91f8-2abe9fed2866.json` |
| Dataset | `01a04fd2-a0a9-7b46-a1ab-5321a5bc0f8c` | `manifests/01a04fd2-a0a9-7b46-a1ab-5321a5bc0f8c.json` |
| Dataset | `01a051c0-2b89-773f-b7dc-6be22a8290fd` | `manifests/01a051c0-2b89-773f-b7dc-6be22a8290fd.json` |
| Dataset | `01a051c0-2bbb-7439-92c5-dd16c24e7910` | `manifests/01a051c0-2bbb-7439-92c5-dd16c24e7910.json` |
| Dataset | `01a051c0-2be2-75c7-8155-be1a640bb2c5` | `manifests/01a051c0-2be2-75c7-8155-be1a640bb2c5.json` |
| Dataset | `01a051c4-88ab-7952-ab2e-6c2b6b437e6a` | `manifests/01a051c4-88ab-7952-ab2e-6c2b6b437e6a.json` |
| Dataset | `01a051c4-88de-7049-9bf2-9c0a27fd5226` | `manifests/01a051c4-88de-7049-9bf2-9c0a27fd5226.json` |
| Dataset | `01a051c4-8906-7261-867c-2f585016229a` | `manifests/01a051c4-8906-7261-867c-2f585016229a.json` |
| Dataset | `01a05718-f3ee-7378-9eef-12c8b9e1ae62` | `manifests/01a05718-f3ee-7378-9eef-12c8b9e1ae62.json` |
| Dataset | `01a06fc4-d65d-7437-9f0f-35d0556b599d` | `manifests/01a06fc4-d65d-7437-9f0f-35d0556b599d.json` |
| Dataset | `01a06fc4-d67b-7cb8-9121-15339add482e` | `manifests/01a06fc4-d67b-7cb8-9121-15339add482e.json` |
| Dataset | `01a06fc4-d6af-7ba3-b019-86779522f26e` | `manifests/01a06fc4-d6af-7ba3-b019-86779522f26e.json` |
| Dataset | `01a06fc4-d748-718a-8c90-5346138ab6b5` | `manifests/01a06fc4-d748-718a-8c90-5346138ab6b5.json` |
| Dataset | `04841642-3bf2-49ff-8bca-4d8285d31296` | `manifests/04841642-3bf2-49ff-8bca-4d8285d31296.json` |
| Dataset | `258ebad5-e836-43b8-aa56-fc5d2fa16adc` | `manifests/258ebad5-e836-43b8-aa56-fc5d2fa16adc.json` |
| Dataset | `55607513-725b-4a4f-86a8-6460248c62f5` | `manifests/55607513-725b-4a4f-86a8-6460248c62f5.json` |
| Dataset | `81e98fea-26cd-4e3c-849b-ae5a189baf98` | `manifests/dataset.json` |
| Dataset | `8865f579-de5b-495c-aa0e-f64c1ef8068a` | `manifests/8865f579-de5b-495c-aa0e-f64c1ef8068a.json` |
| Dataset | `af194735-3881-4d8e-ad4d-1f7b234950f6` | `manifests/af194735-3881-4d8e-ad4d-1f7b234950f6.json` |
| Dataset | `ca6ad090-c918-4544-90a1-e09299e243a4` | `manifests/ca6ad090-c918-4544-90a1-e09299e243a4.json` |
| Model | `01a04fc0-101b-7b71-b680-9428aae28320` | `models/family=dixon_coles_goals/artifact=01a04fc0-101b-7b71-b680-9428aae28320/model-artifact-manifest-v1.json` |
| Model | `01a04fc8-2e57-73a5-a24b-8e40a014694e` | `models/family=dixon_coles_goals/artifact=01a04fc8-2e57-73a5-a24b-8e40a014694e/model-artifact-manifest-v1.json` |
| Model | `01a04fc8-2e57-73ae-acd4-3018d63d7dce` | `models/family=team_elo/artifact=01a04fc8-2e57-73ae-acd4-3018d63d7dce/model-artifact-manifest-v1.json` |
| Model | `01a04fc8-d211-7c27-8e6a-afbcb633bf37` | `models/family=dixon_coles_goals/artifact=01a04fc8-d211-7c27-8e6a-afbcb633bf37/model-artifact-manifest-v1.json` |
| Model | `01a04fc8-d211-7c30-a894-204cedcb8db3` | `models/family=team_elo/artifact=01a04fc8-d211-7c30-a894-204cedcb8db3/model-artifact-manifest-v1.json` |
| Model | `01a04fd2-a0a9-7b7c-8b30-e2e9831b4fdd` | `models/family=dixon_coles_goals/artifact=01a04fd2-a0a9-7b7c-8b30-e2e9831b4fdd/model-artifact-manifest-v1.json` |
| Model | `01a051c0-2b89-7cb6-a303-a26761b684a9` | `models/family=dixon_coles_goals/artifact=01a051c0-2b89-7cb6-a303-a26761b684a9/model-artifact-manifest-v1.json` |
| Model | `01a051c0-2bbb-745a-bd73-c1ec042c4960` | `models/family=dixon_coles_goals/artifact=01a051c0-2bbb-745a-bd73-c1ec042c4960/model-artifact-manifest-v1.json` |
| Model | `01a051c0-2bbb-7463-9b85-92bf63d36b84` | `models/family=team_elo/artifact=01a051c0-2bbb-7463-9b85-92bf63d36b84/model-artifact-manifest-v1.json` |
| Model | `01a051c0-2be2-75d4-baa4-ba5888709c42` | `models/family=dixon_coles_goals/artifact=01a051c0-2be2-75d4-baa4-ba5888709c42/model-artifact-manifest-v1.json` |
| Model | `01a051c4-88ac-7172-b3f0-1020d84ac909` | `models/family=dixon_coles_goals/artifact=01a051c4-88ac-7172-b3f0-1020d84ac909/model-artifact-manifest-v1.json` |
| Model | `01a051c4-88de-70fb-b68e-11e749a0e119` | `models/family=dixon_coles_goals/artifact=01a051c4-88de-70fb-b68e-11e749a0e119/model-artifact-manifest-v1.json` |
| Model | `01a051c4-88de-7104-8e3c-c2710a90a838` | `models/family=team_elo/artifact=01a051c4-88de-7104-8e3c-c2710a90a838/model-artifact-manifest-v1.json` |
| Model | `01a051c4-8906-729e-af90-d8d8105f0dee` | `models/family=dixon_coles_goals/artifact=01a051c4-8906-729e-af90-d8d8105f0dee/model-artifact-manifest-v1.json` |
| Model | `01a06fc4-d65d-76aa-bdd0-3d13d527cf44` | `models/family=dixon_coles_goals/artifact=01a06fc4-d65d-76aa-bdd0-3d13d527cf44/model-artifact-manifest-v1.json` |
| Model | `01a06fc4-d67b-7cc8-97d2-420766e4f372` | `models/family=dixon_coles_goals/artifact=01a06fc4-d67b-7cc8-97d2-420766e4f372/model-artifact-manifest-v1.json` |
| Model | `01a06fc4-d67b-7ccc-9379-16bfb6b9ca50` | `models/family=team_elo/artifact=01a06fc4-d67b-7ccc-9379-16bfb6b9ca50/model-artifact-manifest-v1.json` |
| Model | `01a06fc4-d748-725e-853e-359f4b651cbb` | `models/family=dixon_coles_goals/artifact=01a06fc4-d748-725e-853e-359f4b651cbb/model-artifact-manifest-v1.json` |
| Model | `08422434-1e03-5281-abd9-57b120492225` | `models/family=team_elo/artifact=08422434-1e03-5281-abd9-57b120492225/model-artifact-manifest-v1.json` |
| Model | `0c62e7a4-db73-5b56-bf09-1e8fadb68424` | `models/family=dixon_coles_goals/artifact=0c62e7a4-db73-5b56-bf09-1e8fadb68424/model-artifact-manifest-v1.json` |
| Model | `12d07754-24e3-54f9-b573-43a3e91704a2` | `models/family=corner_poisson/artifact=12d07754-24e3-54f9-b573-43a3e91704a2/model-artifact-manifest-v1.json` |
| Model | `55cbd422-014c-551f-9b59-7b5fd5c57d7f` | `models/family=corner_negative_binomial/artifact=55cbd422-014c-551f-9b59-7b5fd5c57d7f/model-artifact-manifest-v1.json` |
| Model | `760c4a72-35f6-5607-99a0-11d8e9da8992` | `models/family=corner_negative_binomial/artifact=760c4a72-35f6-5607-99a0-11d8e9da8992/model-artifact-manifest-v1.json` |
| Model | `80780dca-38f1-53b3-b4c6-514355935223` | `models/family=team_elo/artifact=80780dca-38f1-53b3-b4c6-514355935223/model-artifact-manifest-v1.json` |
| Model | `9b156570-143d-5b91-99ea-8f72b30a1d05` | `models/family=corner_poisson/artifact=9b156570-143d-5b91-99ea-8f72b30a1d05/model-artifact-manifest-v1.json` |
| Model | `e944a1a5-ec59-5d5a-859b-32a551151393` | `models/family=dixon_coles_goals/artifact=e944a1a5-ec59-5d5a-859b-32a551151393/model-artifact-manifest-v1.json` |

Dependent baseline forecast IDs: `01a04fc8-2e57-73b6-93e3-fada57fc8e48`, `01a04fc8-d211-7c37-904c-0a039563d937`, `01a051c0-2bbb-746a-bf55-49204667e289`, `01a051c4-88de-710d-accd-73caca66ccfe`, `01a06fc4-d67b-7ccf-a4f7-b4985e895ee8`, `0eae5c6a-ba99-549c-a95c-763fa7eeaf77`, `0ffb6be5-3dfc-5a82-b941-de7d9cc01bc6`, `390d365d-055e-5f98-a29f-5c7409c798cc`, `412ad71a-5b7d-5434-9d16-63c83b94fad6`, `42716031-6b19-5fad-8b45-18dfb85238c1`, `4cb447db-7edd-5ee0-ad61-cce81cd5ad1f`, `9d1a91df-e26c-5fe2-ad67-27d4ac359269`, `ac4e45c2-bdb6-573b-91f1-a773d350726f`.


## Appendix C. Read-only reproduction recipes

Use a read-only connection with `default_transaction_read_only=on`, begin the
transaction below, retain its cutoff/snapshot and finish with ROLLBACK. Do not
substitute an application clock or use mutation/recovery entry points.

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT transaction_timestamp() AS knowledge_cutoff, pg_current_snapshot(),
       current_database(), current_setting('transaction_read_only');

SELECT identity_status, forecast_availability, count(*)
FROM football.product_fixtures
WHERE status='SCHEDULED' AND kickoff_at>transaction_timestamp()
GROUP BY identity_status, forecast_availability;

-- Inspect actual applied versions; max(version_id) is insufficient.
SELECT version_id FROM public.goose_db_version
WHERE is_applied ORDER BY version_id;

-- Execution status and domain outcome are separate.
SELECT p.work_id,p.request_id,w.state,p.inputs,
       p.outcome->'report'->>'status' AS parity_status,
       p.outcome->>'report_sha256' AS report_sha256
FROM football.resolution_parity_work p
JOIN football.work_items w USING(work_id)
ORDER BY w.requested_at,p.work_id;

SELECT provider_code,status,last_error,count(*)
FROM football.product_provider_history_scopes
GROUP BY provider_code,status,last_error;

SELECT provider_code,conflict_reason,count(*),
       count(DISTINCT source_snapshot_id)
FROM football.fixture_identity_ingestion_conflicts
GROUP BY provider_code,conflict_reason;

-- One latest decision per fixture, explicitly dated.
WITH latest AS (
  SELECT DISTINCT ON(fixture_id) fixture_id,eligible,reason
  FROM football.product_match_history_decisions
  WHERE decided_at<=transaction_timestamp()
  ORDER BY fixture_id,decided_at DESC,decision_id DESC
)
SELECT eligible,reason,count(*) FROM latest GROUP BY eligible,reason;
ROLLBACK;
```

For target-side counts, materialize
`product_eligible_history_at(transaction_timestamp())` once. Select the explicit
fixture UUIDs from Appendix A, resolve both participants with
`product_fixture_team_at(fixture_id, source_team_id, transaction_timestamp())`,
and count history involving that effective UUID with
`known_at<=transaction_timestamp()`. Require `kickoff_at<target.kickoff_at` for
EXACT and strictly earlier UTC calendar date for DATE_ONLY, as the current
production caller does. Count retained rows separately from
`product_team_match_history`; do not call them eligible. The exact executed
SQL/parameters are retained in `details.json`. Call the existing
`fixture_identity_blockers` and `classify_mapping` on the same read-only
transaction; do not use `admit_provider_mappings`, `refresh_forecasts` or an Admin
apply operation as a diagnostic.

For unmatched work, first select latest observation per
`(provider_code,provider_match_id)` ordered by `observed_at,observation_id`, then
inspect its canonical fixture and latest dated mapping decision. Include native
source snapshots and scope completion metadata in any proposed replay. The
aggregate historical unmatched query is a different population and must retain
that label.

Private receipt hashes below bind executed queries and results. Exact football
payloads, credentials, `.env`, backups and local task status are not committed.
The report carries the actionable ID inventory so future implementation can
refresh operating facts rather than depend on an expired PostgreSQL snapshot.


### Private receipt checksums

All paths below are under `.local/forecast-readiness-investigation/`.

| Receipt | SHA-256 |
| --- | --- |
| `baseline.json` | `34a43b55a708cd385d06260ca5ca71cd7336eeb932a06a9df7eea11f14fa3aae` |
| `details.json` | `1ce6e5e0f19b404e94c64b8cb8767fca69fd8782aa90e0d5d7c921b896c19c65` |
| `followup.json` | `0bfcf1ccbae6ad74e467f4411b39810e24edc2c08a01fcbf10267d481ec29552` |
| `verification.json` | `36b4a71691c57e6090a90031212b233b024bfb4c7575d9345ab8c31336e4b218` |
| `scottish-bytes.json` | `0b65afdb0bb84d99cee6323ff9bf2839223095caa3176358afe1591a38202e31` |
| `extra.json` | `520f669784f3504acbb2b9f1c8c9a29f8fd8afdaaedd7da562933515a1329ae6` |
| `integrity-followup.json` | `059a9156d7b6c2cdea7b4cb9dda9f483192bd020ee526125ee0e63f2dc46e9e3` |
| `models.json` | `7a2891a065261ef86b1b74a98c58a28c99301ff4c0fece739277aa61162d4272` |
| `final-read.json` | `0e7ca66f577f8f775521f98bc46886eccc133a401cd521db8a8863c6b568837d` |
| `freshness.json` | `31ef30ed0595a78236233d2c467870e2533a4647e8343a11ddf7a6ba6af87f10` |
| `pr178.json` | `2837039b52aebb85ec0b3d172619695ee390881302728bab88be8e69a9e3073f` |
| `pr179.json` | `ea7515940518ac4d2836b24f748a127cb417639d83089f46e948ef5db1916ad3` |
| `pr178-identity-report.md` | `0fb8ef06adeed5cad843c313ec40e4593a8d6be3cf946bb04ee585a377e52891` |
