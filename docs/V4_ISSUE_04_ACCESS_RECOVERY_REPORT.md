# Issue 4 provider access recovery

Issue 4 is **PASS_WITH_WARNINGS**. ClubElo, Sofascore and FBref are each **PARTIAL_FUNCTIONAL** through real retained source data. Current direct access remains blocked. Both historical qualification pilots remain **BLOCKED_WITH_EVIDENCE**. All new data is `EXPERIMENTAL_ONLY`.

This closes R04-A through R04-G only. Issues 1 and 3 remain closed; Issue 2 is not reopened. No model fitting, protected evaluation, promotion, cutover, legacy retirement or Issue 5 work was performed.

## Delivery and source revisions

Work continued on `ft/v4-execution-programme` from `61f1c95f0d46bedf598a96b9bea1a13978d013ee`. The ending implementation SHA verified by the full suite is `6567b62b501d1fa511adbbd1ace9f43f1cdbcf81`. The final delivery commit is the commit containing this report and [final evidence](evidence/v4-issue-04-final-verification.json); its exact SHA is recorded after commit in `CURRENT_TASK_STATUS.md`, the PR and the final handoff. The report cannot contain its own commit hash.

| Phase | Independently committed revision |
| --- | --- |
| R04-A implementation research | `acb175a946782b46d3e672e71c7e4ada609fb808` |
| R04-B Reep bridge evidence | `53df8df43c616ef2b5762a1fa00706b1bac2f11c` |
| R04-C ClubElo snapshot | `967d1fcc589c9a0d039373119f9464b36ee04c8a` |
| R04-D Sofascore retained resources | `c3be2f4854aba5b850b0fb07d1a359ea379c6659` |
| R04-E FBref original archive | `9690bb5c8bf87e5dc80534bf56bf228edb1b2ab5` |
| R04-F qualification audit | `b07f8f8f2a6b6ccf102d552013d3452ff153559c` |
| R04-G period-score correction | `6ec940122c562a1da81bf65c8f0d419c1727e3cd` |
| R04-G installed-Polars compatibility | `297f3f524936a7633e8c00289d5e5cf47614fd2d` |
| R04-G unverified archive seasons | `6567b62b501d1fa511adbbd1ace9f43f1cdbcf81` |
| R04-G final verification/report | Commit containing this report |

Each phase was committed and pushed before the next. The three G corrections retain earlier immutable artifacts and frozen phase receipts. G expands the original E checkpoint from 380 to all 3,250 already-retained HTML pages. It also corrects Sofascore's selected count from 115 to 113. The final counts below supersede those earlier checkpoints without rewriting them.

## Implementations investigated

The [research receipt](evidence/v4-issue-04-open-source-research.json) records the inspected files, endpoints, schemas, hashes and licences.

| Project | Pinned revision | Result |
| --- | --- | --- |
| [soccerdata](https://github.com/probberechts/soccerdata) | `b507432742119ba3897533895c92ac3a4f2b9259` | CSV implementation inspected; issue 977 supplied the public website/Vega lead. Website chart data could not be acquired. |
| [sofascore_scraper](https://github.com/tunjayoff/sofascore_scraper) | `dd9f061be2c64f01a6d3a50fb34d55a102d7107b` | Actual football endpoints and retained envelopes inspected; challenge-solving transport neither copied nor executed. |
| [FBRef_DB](https://github.com/ChrisMusson/FBRef_DB) | `a09f314d8f88602ef233ae4d3ae1cf46628538f8` | Archived January 21, 2026; public original-HTML ZIP and separately derived SQLite retained. Unlicensed upstream code inspected, not copied or run. |
| [Reep](https://github.com/withqwerty/reep) | `0ec59faa5d81615b7a8200ae6121023a3bc14ce3` | Current release and v1 data contract verified; exact namespaces and conflict rejection implemented. |
| [football-docs](https://github.com/withqwerty/football-docs) | `b1fb1c175226b9726ac31524bf232d54cf960745` | Source discovery and limitations cross-checked. |
| [theopenmodel](https://github.com/Hicruben/theopenmodel) | `a4f1239a2bc8d0550408a5f8ee1cebb2f1815138` | Original-format retained ClubElo CSV and its fetch script inspected; script appends missing clubs rather than calculating new ratings. |

Seven selected research/source/licence blobs were independently matched to their pinned Git tree blob hashes. No new dependency, migration, environment variable or competing storage/identity registry was introduced. Python normalizers reuse existing observation contracts, source registration, immutable storage and fenced work publication. Reep has a CLI that produces evidence only.

## Provider outcomes

| Provider | Resources registered | Selected observations | Useful recovered scope | Remaining access and meaning limits |
| --- | ---: | ---: | --- | --- |
| ClubElo | 1 | 1,188 | 594 ratings plus 594 source-label records, all dated August 31, 2026 | One snapshot; no verified native club slugs, 2015/16 history or original acquisition time. Website and old API requests blocked; no genuine Vega payload available. |
| Sofascore | 12 | 113 | Retained event, statistics, lineup and incident envelopes; 33 native player references and 16 reported minute occurrences | Eight envelopes trimmed. Event snapshots cover two distinct fixtures; two revisions describe the same completed event. Direct event request returned 403. No complete season, fresh feed or canonical player membership claimed. |
| FBref | 3,252 | 202,404 | 3,250 original match HTML pages plus two retained containers: HTML ZIP and derived SQLite | Current basic schedule returned 403. January 20, 2026 advanced-feed removal was confirmed from the official announcement. Source status and score settlement remain unknown. |
| Total | 3,265 | 203,705 | 3,263 normalized member resources; 3,262 have observations | Observation counts are not independent matches or qualified labels. |

FBref archive directories contain 380 pages each for 2017/18 through 2024/25 and 210 for partial 2025/26. All 3,250 pages normalized without quarantine, retaining 32 native team IDs, 1,734 player IDs, 93,077 player rows and 93,076 non-null minute occurrences. All pages contain explicit native UTC kickoff claims; these do not establish MatchForge fixture identity. One minute value remains missing. For 1,154 pages the actual competition URL omits the season: observations retain null and a warning. Directory labels and calendar dates are not substituted for that missing source relationship.

The 221,143,040-byte SQLite file has 17,551 match rows and 521,261 player-summary rows across six leagues. It passed read-only `quick_check`, but was not normalized as original or current provider data. Team-name fields and the upstream starting-player parsing heuristic are insufficient identity/lineup proof. The 261,573,633-byte ZIP passed every member CRC; listed sizes and locally computed SHA-256 values match the retained receipts. No upstream signed checksum was found. Original HTML and derived SQLite remain separate source classifications.

ClubElo labels remain anonymous references. Sofascore lineup `teamId` can describe a player's current club rather than the match team, so no match membership is inferred from it. Only verified `period1` becomes first-half scoring; `period2` is retained as an unverified source warning. Partial xG, unknown statistics, trimmed lists, missing values and unsupported event types stay visible. FBref footer totals never become player match rows; final/extra-time settlement is not inferred from a scorebox.

### Source and reuse permissions

Reep declares CC0. The inspected soccerdata code uses Apache/MIT terms, theopenmodel declares MIT, and the Sofascore research project uses PolyForm Noncommercial. Those code licences do not establish provider data permission. FBRef_DB declares no code licence; its code was not copied. Provider and archive reuse/redistribution permissions remain unresolved, including the FBref data-use page blocked by 403.

The standing owner policy in [source acquisition](source-acquisition.md) authorizes bounded private local experimental research while keeping these limits visible. Public availability is not treated as provider consent or permission to redistribute. No authentication, challenge, CAPTCHA, paywall or anti-bot restriction was bypassed. Raw HTML, JSON, CSV, databases, bulk IDs, DSNs and `.env` remain outside Git.

## Identity and qualification impact

Reep release **2026-10-31.1** was used, rather than the stale website pointer. Its packaging is `reep-public-release/v4`, implementing the v1 data contract. Release SHA-256 is `1c381cc73e35be1230e695fd403d3b9a8fd14b43829f821f0ce0866a49c11333`. The complete bridge and redirect gzip files, their manifest and release were checksum-verified and published immutably. The bridge has 15,879,646 rows; redirects have 12,917. The release's own quality gate is false.

The original inventory matched 16,669 exact native keys, produced 11,771 candidate entities and rejected 343 conflicting records. The full recovered-source inventory contains 6,796 keys, matches 3,820, produces 3,815 candidate entities and rejects four conflicting/type-mismatched records. Rejected records include conflicting competition/player peers and a player key resolving to a coach. No FBref eight-character native team ID matched; Reep club-name aliases were not converted by name.

| Incremental R04 measure | Before | Final |
| --- | ---: | ---: |
| Registered raw resources | 0 | 3,265 |
| Selected normalized observations | 0 | 203,705 |
| Unique target-provider bridge rows | 0 | 66,494 |
| Unique source identity candidate entities | 0 | 14,971 |
| Existing canonical mapping cases with candidate evidence | 0 | 13,715 |
| Accepted canonical identities | 0 | 0 |
| UTC-qualified canonical fixtures | 0 | 0 |
| Qualified statistical labels | 0 | 0 |
| Verified canonical player appearances | 0 | 0 |
| Verified canonical minute exposure | 0 | 0 |
| Qualified market outcomes | 0 | 0 |

The bridge count spans nine requested provider namespaces across the original and recovered inventories. Candidate entities and mapping cases are distinct counts. Entity/match/edge Parquet schemas and bounded entity/edge rows were inspected; no full Parquet checksum or downloaded match-row sample is claimed. The inspected match schema has a date field and generic metadata, no explicit UTC kickoff column. The manifest reports zero appearances; no verified historical membership intervals were obtained.

The frozen [qualification audit](evidence/v4-issue-04-qualification-impact.json) rechecked the existing owners. Original StatsBomb competition 2 / season 27 still has 380 native fixtures, 21 unresolved team/competition checks, 380 unknown original kickoff timezone interpretations and 15 multi-team player review cases. Twenty exact Resolution Center evidence proposals were prepared; none was applied. External identity candidates exist for 344 original fixtures and 601 players, but do not prove the original UUID algorithm or source/canonical anchors.

Alternative ESPN competition 700 / season 2024 / fixture 704279 retains its explicit native UTC time and a Reep candidate, but lacks a complete admitted competition/team/fixture chain. No canonical competition UUID was invented. Both pilots still qualify zero fixtures or targets. FBref's recovered history begins in 2017, so it does not fill original 2015/16 proof gaps. HT/FT completeness, regulation versus extra time, corner/card/shot settlement and canonical membership/exposure remain required. The 67 market families remain 53 `DATA_COLLECTION_REQUIRED` and 14 `INSUFFICIENT_PLAYER_DATA`.

Issue 3's provider evidence and Issue 2's review inputs are richer. Their qualification decisions and scientific gates are unchanged.

## Isolation, immutable replay and preservation

All task publication used `football.storage.experimental.experimental_connection` into `football_v4_access_r04_20261102`, PostgreSQL system identifier `7679328148388241450`, database OID `53668853`, with a persistent experimental role marker and physical distinction from operating `football`. Operating access was read-only; operating writes and migrations were **zero**.

Cold verification checked all 3,265 registered resource checksums and reloaded all 203,721 physical observation artifacts. Of those, 16 are immutable diagnostic artifacts outside the selected reports. All 3,263 current normalization reports reproduced offline with HTTP disabled, all final work IDs were `SUCCEEDED`, and registry counts stayed identical. Publication retries used the same work IDs; full-archive coverage registration also reproduced the same ID, with 3,250 observed and zero qualified fixtures. The original Reep report reproduced the exact original checksum from immutable inputs using the installed Polars API.

The read-only preservation audit retained every baseline forecast, identity admission, mapping decision, model artifact, resource and snapshot row hash. It verified the original 12,310 operating observation files and 26 capability files. Baseline/current counts were 13,957/14,054 forecasts, 22,090/22,515 admissions, 2,405,839/2,442,239 mapping decisions, 5,230/5,230 models, 65,736/66,237 resources and 63,928/64,429 snapshots. These are concurrent operating additions, not task writes. No globally unchanged database is claimed. Promotions stayed 4 and retirements 17. Champion reload and file checksum remained `e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4`. Serving remains LEGACY, stage controls absent and cutover disabled.

## Verification

- `env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATABASE_URL -u FOOTBALL_DATA_ROOT make check integration`: **exit 0**, source SHA `6567b62b501d1fa511adbbd1ace9f43f1cdbcf81`. This passed 2,054 Python tests, strict mypy on 495 files, Ruff formatting/lint/complexity (limit 10), 16 Rust tests, Go checks/tests/build, architecture/status checks, 126 web tests/build, 865 disposable storage cases and PostgreSQL/Redis/API integration. Integration migrations ran only against disposable test databases.
- Focused phase tests and regression red/green commands, counts and exit codes are in the independently committed A–F receipts. G additionally passed eight Reep cases with exact immutable replay, 14 focused period-score cases and 56 focused FBref/normalization cases. The aggregate includes all 28 introduced unit tests.
- Full original archive preflight, isolated publication, retry checks, source hashes, artifact reload, worker completion, coverage replay and offline normalization reproduction: **exit 0 / PASS**. Existing integration cases cover database isolation, immutable publication, worker fencing, temporal rules and market contracts.
- Two earlier aggregate runs were intentionally interrupted after discovering source-schema problems, both **exit -15**. Their receipts remain historical; the final complete run passed after corrections.
- Final `make project-status-check` and `git diff --check`: **exit 0** after generating the report/evidence. The final delivery SHA is recorded after commit in `CURRENT_TASK_STATUS.md` and the final handoff.
- Seven existing Python dependency warnings and one existing ESLint warning remain. No genuine ClubElo website chart payload was accessible, so Vega parsing is explicitly unverified. No protected scientific evaluation, model fitting or standalone frontend E2E was run.

The [final machine-readable evidence](evidence/v4-issue-04-final-verification.json) binds local receipts and indexes by SHA-256 and records the G corrections. Earlier phase evidence remains historical. New production symbols have current pipeline/CLI consumers, and the final review followed `docs/review-checklist.md`. Concurrent owner changes to `AGENTS.md`, `docs/backend-engineering.md` and `docs/frontend-engineering.md` were preserved outside this task's commits.

## Owner handoff

Issue 4's authorized technical work is complete with warnings. The V4 programme remains blocked. The next action is owner review of the exact Resolution Center proposals and source/reuse limits, followed by independent original UUID/source/canonical anchors, original timezone and settlement proof, and canonical player membership/exposure. Keep Issue 2 blocked until its complete qualification chain passes. No later issue or phase starts from this handoff.
