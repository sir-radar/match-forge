# V4 Issue 2 — historical and player qualification

Status: **BLOCKED_WITH_EVIDENCE**. The retained population has been audited and
the independent qualification checks executed. No selected population passes the
complete identity, time and target-meaning requirements. Issue 2's qualification
objective and the broader V4 programme remain incomplete.

Starting branch: `ft/v4-execution-programme`; starting SHA:
`5716261f4efafdfb670d6ec830fcc6977e0f5613`. Existing identity owners, Resolution
Center, immutable source readers, coverage registries, market diagnostics and
experimental-database guard were reused. No source bytes, identity decisions,
forecasts, champion, scientific criteria or production routes were changed.

## Population and result

The census checksum-verified **96,920 registered normalized observations** from
**1,552 source resources**: 12,310 observations/28 resources in operating
`football`, and 84,610 observations/1,524 resources in the retained Phase 14
shadow. Raw-only operating registrations were inventoried separately; their
registration alone is not a claim of physical byte retention or qualification.
The operating census contained 62,521 source registrations. Concurrent normal
sync additions are excluded from this task's qualification improvement.

The selected pilot is **StatsBomb competition 2, season 27, EPL 2015/16**:
380 distinct native fixtures, 761 retained match-index/event/lineup resources,
41,729 normalized observations and 644 distinct native players. Its exact match
index is `01a051db-5a13-7417-b9b5-247d08f3b82f`, SHA256
`e07d6d360b30e0cd17f9aeea0db1502d2a5666d298f1b44b83a2d2f21ba3d21b`.
The full source-resource matrix and exact immutable input references are linked
by checksum in the [baseline evidence](evidence/v4-issue-02-baseline.json).
The final verification also retains a matrix with exact native resource families,
all 1,524 StatsBomb competition/season relationships linked to their retained
match indexes, and CSV division/native season keys. These source relationships
do not grant canonical identity or historical eligibility.

EPL and La Liga each have 380 retained match/event/lineup sets. EPL was selected
because ten existing independent Football-Data UK fixture resolutions supplied
specific proof candidates to inspect. Those decisions bind exact CSV record keys;
they do not admit StatsBomb native references. The 2026/27 CSV archive has many
labels but anonymous source-record bindings and no player history. Larger raw
counts did not determine pilot selection.

The table describes the required **complete qualification chain for this pilot**,
not all legacy history or player records elsewhere in MatchForge. Baselines are
the first read-only measurements in R02-A through R02-D; no qualification writes
occurred between those measurements. Native occurrences are separate below.

| Metric | First measured baseline | After isolated projection/retry |
| --- | ---: | ---: |
| Retained normalized observations, full audited population | 96,920 | 96,920 |
| Identity-qualified pilot fixtures | 0 | 0 |
| Historically eligible pilot fixtures through the required chain | 0 | 0 |
| Time-qualified canonical outcomes | 0 | 0 |
| Semantic-qualified canonical target labels | 0 | 0 |
| Admitted canonical player identities in the pilot chain | 0 | 0 |
| Qualified continuous memberships / transfer dates | 0 / 0 | 0 / 0 |
| Qualified canonical appearances | 0 | 0 |
| Verified minute exposures | 0 | 0 |
| Qualified canonical player market labels | 0 | 0 |
| Market families requiring data | 53 | 53 |
| Market families requiring player data | 14 | 14 |
| Research-ready market families | 0 | 0 |

Zero qualified units does not mean an absent native value, zero minutes, a player
nonappearance, or an empty legacy history. Earlier-feature eligibility and
continuous membership outside the established pilot chain remain unmeasured.

## Identity, time and target findings

All 380 pilot fixtures have existing mapping claims. The 20 team and one
competition checks return `RETAINED_SOURCE_EVIDENCE_REQUIRED`; none supplies an
admitted R2 proof. No accepted StatsBomb fixture or player resolution is recorded.
Retained native relationships verify source identity but do not independently
establish the claimed MatchForge UUIDs. No new origin rule or permissive approval
path was introduced. See [identity evidence](evidence/v4-issue-02-identity.json).

The six earlier Resolution Center cases were previewed again without mutation.
Three OpenFootball teams still fail `ORIGIN_UUID_MISMATCH`; three PitchAPI
competitions still fail `UNSUPPORTED_ORIGIN_ALGORITHM`. Corrections still need
the existing exact target proof and required review. No contradiction was
resolved, identity admitted, resource unlocked or historical eligibility gained.

The pilot contains **1,313,773 native events**, **9,908 native Shot occurrences**
and **380 paired source scores**. Native event periods are 1 and 2. All 380 local
kickoff clocks lack verified timezone proof; none becomes an exact UTC kickoff.
Provider update strings also lack verified timezones. Relative event clocks,
provider update time, source publication time, MatchForge acquisition time,
canonical admission and forecast knowledge cutoff remain distinct. No event
minute, added time, absolute timestamp or score basis was invented.

FT/HT score basis, shot/SOT inclusion, second-yellow/red treatment, corner
completeness and player settlement meanings remain unqualified. In particular,
`Saved Off Target` cannot establish SOT settlement equivalence. Four content hashes
are shared by Flashscore and Soccerway; each represents one source confirmation.
Missing measurements stay missing; a source's observed zero remains a value.
Corrections require new retained bytes and append-only decisions. Later-acquired
labels never become previously known features for their own fixture. See
[time and target evidence](evidence/v4-issue-02-time-targets.json).

## Player findings

The original **1,240 StatsBomb native-player mapping claims** were remeasured.
The pilot has 644 native players with 644 recorded canonical claims and **zero
new admissions**. Across **13,678 native lineup entries**, source reasons support
8,350 starts and 2,099 substitution appearances; 3,229 roles remain unknown.
These are source occurrences, not unique admitted players or canonical labels.

There are 4,353 closed position-stint occurrences, with no qualified minute
exposure. A starter never defaults to 90 minutes; missing positions or an absent
statistics row never establishes nonappearance or an unused substitute. The
source relationship checks found no contradictory pilot lineup entries.

Fifteen native players have multiple team associations. Their exact IDs and team
sets are transfer-review candidates in the [player evidence](evidence/v4-issue-02-players.json).
Appearances do not establish continuous membership, loans or exact transfer
dates. Goals, assists, shots, SOT, passes, tackles, fouls, cards and goalkeeper
saves all remain at zero qualified canonical player labels. No player model was
trained and no pre-match lineup knowledge was backdated.

## Isolated coverage and repeatability

The new target is `football_v4_qualification_r02_20261101`, PostgreSQL system
identifier `7679328148388241450`, database OID `50918750`. Its persistent
experimental marker and physical separation from operating were verified before
publication. Provisioning used maintenance `postgres`; only the new target was
migrated, through `202610310800`. Its artifact root is
`.local/shadow-v4/qualification-r02`; prior experimental evidence was preserved.

Existing `ProviderCoverage`/`CoverageRegistry` owners registered four native
reports: results, events, lineups and shots, each with 380 observed pilot fixture
units and zero qualified units. No unqualified observations or historical rows
were copied into canonical storage. Existing market diagnostics were rerun for
all 67 families using a scope explicitly identified as recorded mapping claims.
No family became `SUPPORTED`, and no history sufficiency or publication grant
was invented.

Two successful executions with identical frozen inputs produced the same four
coverage IDs, file hashes, counts and blocker classifications. The target still
has four provider coverage rows, zero canonical coverage/resolutions and zero
observation artifacts. The initial diagnostic-summary field-name error occurred
after valid negative coverage registration; corrected retries converged without
duplicates. See [coverage evidence](evidence/v4-issue-02-coverage.json).

## Preservation and verification

The read-only before/after row-hash audit retains all 13,550 baseline forecasts,
22,090 identity admissions, 2,300,146 mapping decisions, 5,230 model artifacts,
62,496 source resources, 60,688 snapshots, four promotion events and 17 retirement
events. No baseline row changed or disappeared. Concurrent sync additions are
reported separately: the final snapshot has 13,850 forecasts, 2,320,392 mapping
decisions, 63,164 resources and 61,356 snapshots. This task performed zero
operating writes.

All original 12,310 observation and 26 capability registrations/bytes match the
baseline. All 84,610 retained Phase 14 observation files passed a final checksum
scan. Champion reload and file hash remain
`e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4`.
Operating routing remains `LEGACY`, stage controls remain uninstalled and the
operating experimental marker remains absent. Protected evaluation/configuration
files and Architecture V2 cutover were untouched.

Focused phase checks passed: R02-A 3 audit tests; R02-B 7 Resolution Center and
12 identity-owner tests; R02-C 58 normalization/audit cases and 4 final clock
boundary cases; R02-D 36 audit/observation cases; R02-E 36 audit/market cases.
Ruff lint/format/complexity and strict mypy checks on the changed scripts passed.
`env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATABASE_URL -u FOOTBALL_DATA_ROOT make check integration`
passed (exit 0): 2,023 Python tests, strict mypy on 487 files, 16 Rust tests,
126 web tests, 865 disposable storage cases, builds and Go/PostgreSQL/Redis/API
integration. Architecture and project-status checks are included in that
aggregate. The final documentation/status update also passed
`make project-status-check` (exit 0). Seven existing Python dependency warnings
and one existing ESLint warning remain. Exact focused commands, exit codes, log
hashes, preservation receipts and the final resource matrix are in the
[R02-F verification evidence](evidence/v4-issue-02-final-verification.json).
No standalone frontend E2E or protected scientific evaluation was run.

The reproducible repository entry points are
[`audit_v4_qualification.py`](../scripts/audit_v4_qualification.py),
[`inspect_v4_pilot.py`](../scripts/inspect_v4_pilot.py) (`identity`, `time`,
`players` sections), and
[`project_v4_qualification.py`](../scripts/project_v4_qualification.py).
Each requires explicit database/root arguments. The census and inspector always
connect read-only. Projection verifies the marked target against the explicit
operating reference and consumes checksum-pinned frozen reports. Original full
receipts, row-hash exports and analysis scripts remain under ignored local
storage, referenced by checksum in the tracked evidence.

## Remaining proof and Issue 3 handoff

No owner approval was requested for an unqualified preview. The next owner action
is to establish independently verifiable exact anchors and use the existing
Resolution Center approval workflow. Source bytes alone do not authorize an
unsupported UUID origin or override a contradiction.

The following are evidence requirements, not new model-history thresholds or an
authorization to collect data. Reuse retained proof first. Current access to
additional historical resources has not been established by this issue.

| Provider / scope | Missing resource or proof | Minimum proof for intended use | Route and expected benefit |
| --- | --- | --- | --- |
| StatsBomb, EPL 2/27 | Exact source/canonical fixture, competition, team and player anchors | Accepted source-backed identity decisions for intended fixture/player references | Existing Resolution Center and original source/mapping evidence first; independently verified anchors if still missing. Enables later historical qualification. |
| StatsBomb, EPL 2/27 | Verified kickoff timezone/UTC and publication/update meaning | Exact clock meaning for each of the 380 intended fixtures; preserve unknown publication times | Provider field documentation or exact independently matched retained fixture proof; additional access unverified. Enables chronological labels without backdating features. |
| StatsBomb, EPL 2/27 | Membership/registration and transfer evidence | Native player/team IDs with explicit intervals or documented unknown bounds; resolve 15 multi-team candidates | Retained roster/transfer proof first; permitted independent route to be selected in Issue 3. Enables participation-aware player history. |
| StatsBomb, EPL 2/27 | Observed exposure and complete participation | Source-backed minutes or complete playing-period/substitution evidence; explicit missingness and nonappearance/void meaning | Supplement retained lineup/events only where required; historical acquisition access unverified. Enables valid player exposure and settlement labels. |
| StatsBomb, EPL 2/27; other native samples | Target definitions, periods, completeness and correction/settlement evidence | Exact FT/HT, shots/SOT, corners/cards and player-stat meanings bound to native fields and periods | Provider definitions and independently verified target rules, then narrowly scoped missing observations. Enables measured target-specific coverage. |
| OpenFootball/PitchAPI, six existing R3 cases | Original origin/target and correction proof | Exact existing origin algorithm/UUID and qualified target evidence, with required owner review | Existing Resolution Center cases; more generic match rows cannot resolve a UUID contradiction. Keeps affected history blocked until proof passes. |

Issue 3 provider expansion, access fixes, new market models, protected evaluation,
champion changes, production cutover and scheduler retirement were not started.
Issue 2 remains **BLOCKED_WITH_EVIDENCE** until a useful population passes the
complete qualification path.

## Phase commits

| Phase | Commit | Result |
| --- | --- | --- |
| R02-A | `11d3217f94f9e1beb6d4067e60aae35a3f4cf311` | PASS: census and bounded pilot identified |
| R02-B | `59cd60cb7b45f992188e3292624c3c6ae6bedef7` | BLOCKED_WITH_EVIDENCE: exact identity admission |
| R02-C | `1482c88c641825b6dd09f39a63d53a0dc6d4d13c` | BLOCKED_WITH_EVIDENCE: time and target meaning |
| R02-D | `0c3917ccc57f8688669bb1c8c42de117d5440675` | BLOCKED_WITH_EVIDENCE: player identity/membership/exposure |
| R02-E | `6666464be00e50213ba6374e205fe22ab91b5a68` | BLOCKED_WITH_EVIDENCE: isolated negative coverage verified |
| R02-F | Commit containing this report; exact SHA in `CURRENT_TASK_STATUS.md` and final handoff | Verification and blocked-result handoff |
