# V4 Issue 3 — provider expansion and qualification impact

Status: **PASS_WITH_WARNINGS for acquisition; qualification remains BLOCKED_WITH_EVIDENCE**.
All eight phases have been executed within Issue 3. The five providers were
re-evaluated, useful historical data was acquired and retained, and both pilot
qualification chains were checked. Neither pilot gained a qualified canonical
fixture, player, minute exposure or market label. Issue 2 cannot yet be reopened
for final qualification. The V4 programme remains incomplete.

Branch: `ft/v4-execution-programme`; base: `main`. Starting SHA:
`55583a380dce23e4a14bae077b1407341caf2b08`. The ending SHA is the R03-H commit
containing this report; its exact value is recorded in `CURRENT_TASK_STATUS.md`
and the final handoff. Owner commit
`3bb5d0193cde6328955e499ac716082787cd0018` arrived during R03-G and was preserved.
No Issue 1/2 report, original observation, identity admission or model artifact
was rewritten.

## Acquisition and useful coverage

These are distinct **provider-native IDs in checksum-verified normalized data**,
including the preserved baseline. They are not independent football matches or
canonical identities. Shared Flashscore/Soccerway IDs must not be added together
as independent confirmations. Seasons mean verified source samples, with full
coverage stated separately.

| Provider | Native fixtures before → after | New normalized fixture IDs | Native players before → after | Native seasons before → after |
| --- | ---: | ---: | ---: | --- |
| Understat | 380 → 1,140 | 760 | 32 → 85 | 2024 → 2015, 2016, 2024 |
| ESPN | 2 → 38 | 36 | 40 → 361 | 2024, 2026 → 2015, 2024, 2026 |
| WhoScored | 10 → 38 | 28 | 0 → 0 | 2026/27 → 2015/16, 2026/27 |
| Flashscore | 304 → 514 | 210 | 40 → 115 | 2024/25, 2026/27 → add 2015/16, 2023/24 |
| Soccerway | 304 → 522 | 218 | 40 → 110 | 2024/25, 2026/27 → add 2015/16, 2016/17 |

Understat supplied complete 380-fixture EPL indexes for 2015 and 2016, with 760
result pairs, 1,520 team xG values and 53 shots from two selected matches. Its
naive kickoff strings remain date-only. The retained roster JSON and rendered
player-time text agree for 53 reported time values. These are source claims,
not canonical minute exposures, confirmed nonappearances or membership intervals.

ESPN daily scoreboards covered 12 selected 2015/16 dates and one 2024 alternative
date, with 14 match summaries. The acquired population has 37 distinct native
fixtures, 361 native players, 508 player-statistic observation occurrences and
390 explicit native appearance occurrences. One fixture was already in the
baseline, so the new fixture-ID delta is 36. Source kickoff timestamps carry `Z`
and explicit `timeValid`; no minutes field was present in the inspected rosters.
Two-element score arrays were retained without inventing period IDs or HT rules.

WhoScored exposed 28 season links. Its verified EPL 2015/16 season 5826 and stage
12496 fixtures page supplied 28 May fixtures. The adapter now supports those
native season/stage routes and rejects a payload whose season or stage differs
from the request. The region is 252, established by retained source links; the
speculative region 206 candidate in R03-A was never used as identity proof.
The selected month is not represented as a complete 380-fixture season.

Flashscore supplied 107 normalized EPL 2015/16 fixtures and 103 from 2023/24,
plus statistics, incidents, lineups and direct period summaries for one match in
each season. Its ordinary browser control traversed the complete 2015/16 list:
107 → 200 → 300 → 380 native fixture IDs, with no remaining “Show more” control.
The exact 380-ID text is retained, with matching browser/file CRC32 `5aced062`
and SHA256 `2b6a3248877a1e3238d3bd4c03b8a7752d97ed17077756bc0ed2812c41051258`.
That census is additional raw identity coverage; the 273 extra browser IDs are
not counted as normalized result/statistic rows or UTC-qualified source rows.

Soccerway supplied 107 fixtures from 2015/16 and 111 from 2016/17, plus the same
four rich resource families for selected matches. The first 107 IDs overlap
Flashscore's census. The other 111 add coverage within the shared upstream
namespace. Four newly compared rich-resource hashes are byte-identical across
providers. All overlapping fixture facts agree; different HTML hashes and website
domains do not establish independent football evidence. No additional independent
confirmation source is claimed for Soccerway.

The new shadow contains 72 registered resources and 9,704 observation artifacts.
Of those artifacts, 1,183 replay the retained Flashscore baseline; **8,521** come
from new acquisitions, including separate provider records for shared upstream
content and re-observations of existing fixtures. This is not a count of new
independent football facts. The original 96,920-observation audited population
remains preserved.

The following qualified metrics cover the two pilot chains, not unrelated legacy
history. Counts stay zero where a mandatory identity/meaning step is absent.

| Qualification/readiness metric | Baseline | After |
| --- | ---: | ---: |
| Verified completed-season provider samples, including partial samples | 4 | 12 |
| Canonical identity-qualified fixtures | 0 | 0 |
| UTC-qualified fixtures through canonical identity | 0 | 0 |
| Complete qualified HT/FT outcomes | 0 | 0 |
| Qualified shots/SOT labels | 0 | 0 |
| Qualified corners/cards labels | 0 | 0 |
| Verified canonical player identities | 0 | 0 |
| Qualified canonical appearances / minutes | 0 / 0 | 0 / 0 |
| Market-ready outcomes / research-ready families | 0 / 0 | 0 / 0 |
| Original missing owner proofs / kickoff timezones / multi-team reviews | 21 / 380 / 15 | 21 / 380 / 15 |

The independent count of real cross-provider fixtures remains unqualified. Native
ID deltas and shared-upstream coverage are measured above; they are not substituted
for an unmeasured independent canonical population.

## Requests, limitations and source use

| Provider | Guarded HTTP attempts | Observed failures or limitations |
| --- | ---: | --- |
| Understat | 8 | Match 81, match 82 and EPL 2023 requests raised `ProviderFetchError`; no repeated fetch of those failed keys |
| ESPN | 34 | Four range-query variants returned HTTP 400; daily requests worked; three extra transport attempts occurred during successful bounded retries |
| WhoScored | 3 | League, historical season and linked monthly fixtures pages succeeded; the previously recorded detail-page HTTP 403 was not retried |
| Flashscore | 18 | Four direct pagination probes returned HTTP 200 with the single byte `0`; no useful football rows or working direct-pagination API was claimed |
| Soccerway | 12 | Selected historical and rich feeds succeeded; complete-season coverage was not claimed |

There were 75 guarded HTTP attempts. Separately, Flashscore used one browser
navigation and three native pagination clicks, and StatsBomb's public definition
PDF was fetched once. Browser subresource traffic, terms-page lookups and the
intermediate status of successful transport retries were not fully metered;
75 is not presented as a total of every browser/metadata network request.
Five cached provider replays subsequently made **zero additional guarded
requests** and left source, observation, coverage and capability counts unchanged.

The [R03 owner decision](evidence/owner-decision-flashscore-soccerway-research-exception-2026-11-01.json)
and newer standing policy in [source acquisition](source-acquisition.md) authorize
bounded local experimental work. Provider permission remains unestablished.
[Flashscore's terms](https://www.flashscore.com/terms-of-use/) and
[Soccerway's terms](https://www.soccerway.com/terms-of-use/) impose automated-acquisition restrictions, which remain a
compliance limitation, recorded with their source routes. This internal exception
is not provider consent. All outputs from this work are **EXPERIMENTAL_ONLY**.
No authentication, CAPTCHA, paywall, access-control or anti-bot protection was
bypassed. No third-party raw bytes or the bulk browser-ID capture are committed
or publicly published; tracked receipts contain provenance, counts and hashes.

## Identity, time, target and player recheck

| Required stage, fixture units | Track A: StatsBomb EPL 2/27 | Track B: ESPN 700/2024, fixture 704279 |
| --- | ---: | ---: |
| Raw | 380 | 1 |
| Normalized | 380 | 1 |
| Identity-qualified | 0 | 0 |
| Time-qualified through the identity chain | 0 | 0 |
| Semantically qualified through the identity chain | 0 | 0 |
| Historically eligible | 0 | 0 |
| Market-label-qualified | 0 | 0 |

Track A's 21 team/competition owner checks still have no admitted exact proof.
Its 380 existing match claims have no accepted fixture resolution. Independent
native UTC fields have been acquired, but no accepted exact binding permits
applying them to the StatsBomb clocks. Coincident dates, names and scores do not
supply that binding.

Track B has an exact native UTC timestamp and normalized result/player evidence.
The existing identity owner finds no ESPN competition-700 or team-360/team-370
mapping/admission chain and no accepted match/player resolution for the selected
fixture. No canonical competition/season UUID was invented to run a misleading
Track B market report. The identity failure prevents the later stages from
qualifying even though native source fields exist.

StatsBomb's retained 45-page Open Data Specification v1.1 was extracted and its
match/shot tables visually checked on pages 6 and 31. Its inspected kickoff
definition does not state a timezone. Its off-target saved-shot definition gives
useful native shot meaning, but does not establish sportsbook settlement
compatibility. FT/regulation/ET, target completeness, correction, card treatment
and void rules remain unqualified. Direct Flashscore/Soccerway period counts keep
`score_basis=UNKNOWN` and unknown completeness; absent values never become zero.

Three Flashscore match pages agree exactly with their league rows on native
fixture and home/away team IDs. These are useful source-side relationships, not
canonical mappings. Rich-statistic/event/player references still need explicit
qualified bindings through the existing workflow.

All 15 original StatsBomb multi-team candidates remain transfer-review cases.
Neither isolated appearances nor a displayed minute count proves continuous
membership, exact transfer dates, full participation, nonappearance or a void
rule. Qualified canonical player identities, memberships, appearances, minutes
and player market labels all remain at zero for the required pilot chains.

The original six Resolution Center previews remain blocked: three
`ORIGIN_UUID_MISMATCH` cases and three `UNSUPPORTED_ORIGIN_ALGORITHM` cases.
Their exact case keys and evidence versions are in the recheck receipt. No case
is newly ready for safe approval; no approval or contradiction override was
applied. Obtain independently accepted exact source/canonical anchors and target
proof before asking the owner to approve an admission.

Existing owners registered 36 scoped native coverage/capability reports and two
pilot coverage reports. All qualified counts are zero. Twenty-four append-only
capability clarifications distinguish detail-resource clocks from linked fixture
kickoffs; 60 capability decision rows represent 36 scopes, not 60 new capabilities.
Identical-input publication repeats preserve report bytes, hashes, IDs and counts.
There are zero canonical coverage rows, canonical resolutions or identity decisions
in the R03 shadow. Operating and isolated diagnostics remain **53
DATA_COLLECTION_REQUIRED + 14 INSUFFICIENT_PLAYER_DATA**, with zero research-ready
families or publication grants.

## Isolation, preservation and verification

The isolated target is `football_v4_expansion_r03_20261101`, PostgreSQL system
identifier `7679328148388241450`, OID `52291857`, with a persistent experimental
marker. Its physical identity was checked against a read-only operating reference
before requests/publication. Only this new target was migrated through
`202610310800`. Raw files, observation publication and work fencing reuse existing
owners. All 72 source resources passed checksums; all 9,704 observation artifacts
reloaded successfully; all 60 normalization work IDs are succeeded.

Read-only preservation checks retain all baseline 13,881 forecasts, 22,090 identity
admissions, 2,333,927 mapping decisions, 5,230 model artifacts, 63,741 resources and
61,933 snapshots. Concurrent normal activity produced 23 additional forecasts,
20,842 mapping decisions and 334 resources/snapshots; no baseline row changed or
disappeared. All original 12,310 observation artifacts and 26 capability files
remain identical. All 84,610 prior Phase 14 observation files passed checksums and
their sorted-ID/hash digest still equals
`d5db74038f9f4e5bd56c036aa94200ca0139ae4d95cad12d3916bc8ee2502da4`.

Champion reload and file checksum remain
`e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4`.
Operating access was read-only; operating migrations and task writes were zero.
Routing remains `LEGACY`; stage controls remain uninstalled and the operating
experimental marker remains absent. No protected evaluation, model training,
promotion, champion, production cutover or scheduler retirement was changed.

Focused tests passed with exit 0: R03-B 32, R03-C 34, R03-D 14, R03-E 49,
R03-F 21 and R03-G 110. The three new WhoScored regression cases cover historical
route/guard behavior and exact native season/stage checks. Changed production and
test files passed Ruff format/lint/complexity and strict mypy. The existing
architecture/status targets passed at each checkpoint.

`env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATABASE_URL -u FOOTBALL_DATA_ROOT make check integration`
passed with **exit 0**: 2,026 Python tests, strict mypy on 487 files, 16 Rust tests,
126 web tests/build, Go lint/tests/build, 865 disposable storage cases and
PostgreSQL/Redis/Go API integration. Format, lint, complexity, architecture and
status checks passed. Seven existing Python dependency warnings and one existing
ESLint warning remain. No operating migrations ran.

Full command receipts, exact exit codes and log hashes are linked from the
[R03-H verification evidence](evidence/v4-issue-03-final-verification.json).
No frontend changed; no separate browser E2E or protected scientific evaluation
was run. The Makefile's aggregate already includes architecture and project-status
checks; a final status validation follows the final machine-readable status edit.

## Phase commits and remaining work

| Phase | Status | Commit |
| --- | --- | --- |
| R03-A | PASS: targeted proof matrix and both tracks | `d48a75212c240ffe5057e611ba06056629e97121` |
| R03-B | PASS_WITH_WARNINGS: Understat history and shots | `18bbc028fa8c36c85fde6251bcf9235d85818574` |
| R03-C | PASS_WITH_WARNINGS: ESPN daily history and players | `d589e4afda256bf7e33c649dba276786949bde6a` |
| R03-D | PASS_WITH_WARNINGS: WhoScored historical routes and month | `238a0f013449ede83d84ed85971e4a38d707ec35` |
| R03-E | PASS_WITH_WARNINGS: Flashscore history, rich data and ID traversal | `f1185291bcefe4173e058d65dccd6dcc283fa562` |
| R03-F | PASS_WITH_WARNINGS: Soccerway history and upstream comparison | `011e9c4b43e5eea432de25f2420cd42b4e3daaf5` |
| R03-G | BLOCKED_WITH_EVIDENCE: both canonical qualification chains | `84e4013356dc0fcad02103bca3c270fc84224a2d` |
| R03-H | PASS_WITH_WARNINGS: final verification and acquisition handoff | Commit containing this report; exact SHA in task status and final handoff |

Issue 3's remaining limitations are exact identity anchors; original kickoff
timezone; settlement-compatible targets; canonical player membership/exposure;
partial normalized histories outside Understat; and unverified direct Flashscore
pagination. These are disclosed, not converted into canonical eligibility or a
claim that every provider resource is inaccessible. Issue 2 remains blocked.

Issue 4 handoff: use the standing experimental acquisition policy for the existing
ClubElo, Sofascore and FBref access-recovery tasks, while distinguishing technical
failures from terms status. Their blocked routes were not retried in Issue 3.
Reuse the verified isolation guard, immutable sources and existing adapters;
retain actual responses and keep access-control/anti-bot restrictions intact.
No Issue 4 implementation, new phase or further acquisition is started by this
handoff.
