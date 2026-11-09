# Forecast readiness remediation execution

Branch: `ft/data-status-remediation`; PR: [#179](https://github.com/sir-radar/match-forge/pull/179).
Requirements: [remediation plan](forecast-readiness-remediation-plan.md) and the
current owner task. This execution does not authorize Architecture V2 cutover,
legacy retirement, model promotion or reopening scientific release gates.

## Baseline checkpoint

Starting code: `6120f1c752a95ed95a65c270895f762c82ee082a`. Fetch confirms
`main` at `e4ea615ca5464403df4d0377ad03a2c6f1df2213` is already included.
PR #179 is open; PR #178 remains draft, open and unmerged. No Wayfinder map
is assigned. Model routing is L3 because this work affects historical identity,
transactional invalidation and readiness gates.

Fresh operating snapshot: **2026-11-03 15:43:07.735134 UTC** (16:43:07 Lagos),
`17975766:17975766:`, database `football`, enforced `REPEATABLE READ READ ONLY`.
All applied migration records were read individually: `202611020200` is applied;
`202611020100` is absent. No operating migration or restart was performed.

| Measurement | Fresh baseline |
| --- | ---: |
| Upcoming verified forecast-available fixtures | 2,362 |
| Upcoming verified history blockers | 141 |
| Upcoming verified source blockers | 48 |
| Eligible history rows | 301,307 |
| Forecast-available competition rows | 226 |
| Pending context reports | 146,765 |
| Pending forecast refresh work | 0 |
| Published product forecast rows | 14,773 |

These are fresh populations, not remediation gains. Background workers remain
active and elapsed kickoffs change upcoming counts. The investigation's 196
blocked fixture IDs remain the comparison cohort; the separate older 153-ID
cohort is retained only for preservation checks. Previously recovered Coventry,
Málaga and Armenian fixtures cannot count as new gains.

Private executed queries and results are under
`.local/forecast-readiness-execution/baseline.json`; raw football payloads,
credentials and local status are not committed. The existing approved populated
backup is pinned by SHA256
`a5ed6d94a583070a1b51641f466f1ef44cabeaba01da10c8a730a194faba7bb7`.
Profiling and mutation experiments use a new disposable database, with operating
and shadow identities checked independently.

## Execution inventory

| Issue | Status | Next required evidence or work |
| --- | --- | --- |
| FR-001 | VERIFIED | 30 identities repaired; 15 verified forecasts; 15 history gaps remain FR-004 |
| FR-002 | IN_PROGRESS | 15 reviews/4 public forecasts verified; 8 identity and 6 history holds; scoped follow-up running |
| FR-003 | BLOCKED_DEPENDENCY | All 41 target predicates inventoried; FR-001/008/016 and exact FotMob counterparts required |
| FR-004 | IN_PROGRESS | Native catalogue acquired; exact lower-division requests deferred under existing guards |
| FR-005 | BLOCKED_EVIDENCE | All 41 already revalidated; 33 archive seasons checked; dated counterpart/correction proof remains |
| FR-006 | VERIFIED | Batched context invalidation; authorized operating migration verified |
| FR-007 | BLOCKED_DEPENDENCY | 455 verified operating aliases/retries; 275 held occurrences require FR-005/008 |
| FR-008 | IN_PROGRESS | Two Málaga holds reproduced; all 46 Coventry rows characterized in rollback; exact identities/season fix pending |
| FR-009 | IN_PROGRESS | Source-season bug fixed/verified; current native inventory and 58 source-backed shadow replays recorded |
| FR-010 | IN_PROGRESS | Approved operating hold policy/sample verified; source-dependent scopes remain |
| FR-011 | BLOCKED_EXTERNAL | Approved retirement verified; exact originals remain absent from searched copies |
| FR-012 | NOT_STARTED | Full-scope comparison evidence and Phase 35 readiness gate |
| FR-013 | IN_PROGRESS | Frozen 196 context/14 performance generations verified; global backlog frozen for continued bounded work |
| FR-014 | NOT_STARTED | Independent StatsBomb native-target proof; account for PR #178 |
| FR-015 | NOT_STARTED | Source/player/settlement gaps without release-gate changes |
| FR-016 | NOT_STARTED | Exact quarantine and schedule evidence |

Execution order follows dependencies: shared defects, qualified forecast recovery,
remaining integrity/recovery work, then parity. Every verified implementation
task is committed before proceeding. Blocked evidence is recorded separately;
it does not prevent independent work.

## Research and verification

The PostgreSQL 18 [trigger documentation](https://www.postgresql.org/docs/18/trigger-definition.html)
and [trigger-function examples](https://www.postgresql.org/docs/18/plpgsql-trigger.html)
support statement-level transition relations. Whether these remove the measured
admission bottleneck must be established by populated profiling and comparison;
documentation alone is not performance evidence.

Baseline checkpoint: **PASS_WITH_WARNINGS**. Operating acquisition is read-only;
implementation acceptance remains pending. Text review and `git diff --check`
are the applicable checks for this prose-only checkpoint.

## Phase A: FR-006 admission fanout

**Result: PASS_WITH_WARNINGS.** The code defect is verified in disposable
databases. No operating migration, admission or new forecast is claimed.

The deployed row trigger repeatedly resolves every possible target's effective
participants for each inserted history decision. Read-only `EXPLAIN ANALYZE`
finds the expensive node is the `product_fixtures` bitmap heap scan and its
participant-resolution filter: 6,315 rejected targets and approximately 200,000
shared buffer hits for one source row, even when the final target set is empty.
Single-row query times are 1,185.754 ms for DED, 337.631 ms for PD and 259.416 ms
for BSA; these are separate plan probes, not full admission timings.
An actual nested `auto_explain` trace of the optimized DED trigger processes all
711 transition rows in one 1,037.911 ms query. Its materialized target scan
resolves 6,135 targets once and touches 192,625 shared buffers in total, rather
than repeating that scan for every history row. Trace instrumentation is separate
from the admission timings below; the complete nested plans are retained in
`profile-after-plans.json`.

New migration `202611030100` replaces only the context history trigger with an
`AFTER INSERT` statement trigger and transition relation. It materializes
effective participants once per possible target, selects each affected fixture
once and calls the existing queue writer in UUID order. Existing decision
qualification, forecast invalidation, knowledge/kickoff predicates, transaction
boundaries, queue completion and publication fencing remain in place. Eligible
and revoked history both invalidate context. Accepted migrations are unchanged.

The checksum-verified approved restore contains 479,199 retained history rows.
All experiments use `football_fr_execution_20261103`, with database name and
PostgreSQL system identifier checked before mutation, and roll back every trial.
The existing source-backed mapping writer and reviewed admission workflow are
used for DED/PD/BSA; the backup predates those native mapping registrations.

| Scope | Old admission, 20-second deadline | Batched admission | Appended decisions | Required/actual context keys |
| --- | --- | ---: | ---: | ---: |
| DED | Timeout, 20.306 s including collection | 4.118 s | 711 | 0 / 0 |
| PD | Timeout, 20.275 s including collection | 3.944 s | 488 | 0 / 0 |
| BSA | Timeout, 20.331 s including collection | 3.274 s | 1,014 | 0 / 0 |

The 20-second statement timeout comes from the existing Resolution Center.
After timings cover the admission call, including retained-proof verification;
surrounding preservation queries are measured separately in private receipts.
Reference trials disable only the context trigger inside a rolled-back shadow
transaction to capture unchanged qualification outputs. The resulting decision
facts (excluding generated IDs and decision clocks) match the batched writer
exactly for all three scopes. Earlier-cutoff eligible history digests match
before/after each admission. Expected context keys are computed independently
from effective target participants and each appended decision. Empty real-world
key sets are reported honestly; synthetic positive, revocation and concurrency
tests establish nonempty fanout behavior. **Verified new forecast availability: 0.**

Verification completed:

- The initial regression fails for both eligibility states: a 40-row statement
  produces generation 41 instead of 2. The nine new batch, time-boundary,
  rollback and concurrent-generation cases subsequently pass.
- The populated upgrade test preserves complete decision, forecast and queue
  rows, accepts migration retry and produces no invalidation on an empty insert.
- The five related admission, context-report, identity-upgrade, worker-fencing
  and lock-order integration suites pass in a fresh disposable driver database,
  including existing historical-cutoff and revocation coverage.
- Ruff and strict mypy pass (446 source files); Goose migration validation,
  project-status validation and `git diff --check` pass.
- Final `env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATA_ROOT make check integration`
  exits **0**: 1,818 Python unit tests, 16 Rust tests, Go checks, 107 web tests,
  builds, architecture checks, fresh storage migrations and all storage/API
  integration checks pass. Seven existing Python dependency warnings and one
  existing ESLint warning remain. No frontend behavior changed; no browser E2E
  or scientific evaluation was run.

Reproduction uses the existing disposable storage harness and the added cases
in `tests/integration/test_public_reports.py`. Private profiling scripts, plans,
executed queries and logs are retained under `.local/forecast-readiness-execution/`.
The approved source dump and original registrations are preserved.

| Private receipt | SHA256 |
| --- | --- |
| `baseline.json` | `465310ee76f9f186e5580dd811dbb29123ed09c0783656f2fb9c665a094ce670` |
| `frozen-cohort.json` | `8330c00abaac1b1d3ca14af259ae906afb347ed819d0041db86eab6c4ff62089` |
| `profile-before.json` | `23d8b4b3db5cd8cb31853348d9dc2746e931ab4b299c597323f4dfe43870e513` |
| `profile-reference.json` | `df9f6cd99cb42fce4101f4c5a8fa736c433a9a9edfa8652335d33d086ceb4749` |
| `profile-after.json` | `190047e6cfede7ed0c2e0eb73a438d3fc47cc35ae10059fd44362488a6082380` |
| `profile-select.json` | `969ca75001f8f15d6d67b7a5d853c33c3d3fdbd999fa1417097f433a12296243` |
| `profile-after-plans.json` | `17136e9f72070e2d45fe3cd66e828e43363449ee79d2f92401bf2cec739ef106` |
| `fr006-integration.log` | `530db5cda446467b69e6a47daebfb0784039f943a8eafe0418b8568b1509203e` |

## Phase A: FR-007 rolling CSV occurrences

**Implementation: PASS_WITH_WARNINGS, verified in shadow. Remaining conflict
recovery: BLOCKED_DEPENDENCY on FR-005/008.** The product parser now emits
`<source_path>#<row>@sha256:<raw_byte_sha256>` for `Latest_Results.csv` only.
The source path before `#` remains compatible with the existing fixture-lineage
reader. Seasonal CSV and ZIP-member identifiers retain their original format;
existing mapping rows and previously published identifiers are never reassigned.
New registrations identify the product parser as `football-data-uk-product-v2`;
the frozen Phase 1B native reader is unchanged.

This identifies a source occurrence, not a real match by itself. The existing
historical importer still requires exact competition, participant and kickoff
relationships before reusing a canonical fixture. Score disagreements, reversed
participants, impossible schedules and unsupported cross-provider relationships
retain the existing conflict/review paths. No new registry, migration, dependency,
fuzzy matching or confidence-based admission was added.

The provider [describes its latest file as combined recent results](https://football-data.co.uk/all_new_data.php).
Two retained-style responses reproduce row reuse; the regression fails before
the change. Parser tests pass afterward. Disposable integration also verifies
legacy mapping preservation, unchanged earlier-cutoff eligible history, source
checksum/path lookup, row insertion/reordering, identical-byte retry, corrected
scores and orientation/schedule rejection. Both the original source version and a
reordered version resolve the same real fixture without rewriting the legacy ID.

All **730** frozen `PROVIDER_MATCH_ID_REUSED` records over ten snapshots have
byte-verified source occurrence dispositions in the machine-readable
[inventory](forecast-readiness-fr007-dispositions.json). No raw football payload
is included in that file.

| Final shadow disposition | Records | Remaining dependency |
| --- | ---: | --- |
| Exact occurrence reconciled to a canonical fixture | 455 | None for occurrence matching |
| Scottish archive row-key reuse | 171 | FR-005 and FR-008 |
| Other archive row-key reuse | 85 | FR-008 |
| Scottish normalized kickoff differs by one hour | 9 | FR-005 and FR-008 |
| Team/timestamp collision | 8 | FR-008 |
| Unreviewed cross-provider fixture relationship | 2 | FR-008 |

The 455 reconciled occurrences resolve **455 distinct canonical fixtures**:
275 already exist and 180 add authentic retained results in the disposable
restore. Identical retries return `existing` for all 455; the other ten rolling
records hit the same guards on retry. The 256 archive occurrences are held
without changing archive keys, and the nine time discrepancies are not silently
coerced. **Operating history recovery and verified forecast gain: 0.** No shadow
retained-row count is represented as eligible history or forecast availability.

The approved restore predates one source registration. The first rehearsal
explicitly holds its 180 rows. Existing immutable-manifest registration restores
that source to shadow with exactly the operating snapshot/resource IDs
`a2bc6000-1bdf-540e-afd5-69b11c0643dd` /
`caa82b7a-51a5-527e-896b-2cfedbbd34b6` and its verified original checksum. The
complete rerun then succeeds; no registration or football bytes are fabricated.
All replay mutations roll back. Source registrations, prior mapping rows,
historical decisions, model/forecast/artifact registrations, promotions,
retirements, prior history rows and earlier-cutoff eligible history retain their
before/after digests. Full failure and successful receipts remain private.

Final `env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATA_ROOT make check integration`
exits **0** after the final parser/test changes: 1,819 Python unit tests, 16 Rust
tests, 107 web tests, static/type/architecture checks, builds and the complete
disposable storage/API integration pass. The metadata inventory validates all
730 unique conflict IDs, 455 successful retry bindings, every remaining dependency
and the exact parser file checksum. Existing dependency and ESLint warnings
remain. No browser E2E, scientific evaluation or operating rollout was performed.

**Phase A checkpoint: PASS_WITH_WARNINGS.** Shared-defect implementations are
verified. Operating rollout and the explicitly held source/identity conflicts
remain separate from code acceptance. Phase B may proceed with independently
qualified evidence; no held record is forced through a guard.

| Private receipt | SHA256 |
| --- | --- |
| `csv-reuse-inventory.json` | `560c2fbcd6ee3f175a948b77fb046a0da8b2a2d9a1c4341adb39ef078c6aa7f6` |
| `csv-reuse-source-audit.json` | `3a1be748318fd531f42eb55ceb21b5f2c87db4bb958851e400e130f1f8abfc6b` |
| `rolling-shadow.json` | `4b391ac4f99e0902108fc28b39b013b38f098cd6adedc5a354a10c10ddaccadb` |
| `rolling-held-guards.json` | `3feede311570cafdcf7b06d1b125b64602eee90b856288606b3e7ea61dcfe300` |
| `csv-reuse-dispositions.json` | `e086a0bfcf64cebc9a37daf2fb0abe879dff420b492a16301badeb4e053e4fbb` |

## Phase A: authorized operating rollout

The owner explicitly authorized migration `202611030100` and bounded use of the
committed rolling parser, conditional on backup recovery, migration compatibility,
a small initial batch and integrity monitoring. The authorization also permits
subsequent independently executable remediation. Architecture V2 cutover, route
changes and model promotion remain outside that authorization.

A fresh exported operating snapshot was captured at **2026-11-03 17:26:17.463926
UTC**. The custom-format backup is 1,514,478,207 bytes, SHA256
`e1e0177406cf545e5a438283e3eb25942db313f77dc159a56f2be34ea80ec8f2`.
The PostgreSQL 18 client restored it completely into an owned isolated database.
All nine captured source/admission/model/forecast/artifact registration digests
match. The approved migration changes no captured rows, queue contents or stage
settings. An isolated Goose forward-repair rehearsal restores the exact captured
original function and row trigger while preserving those same digests. That
schema-only repair is an emergency procedure; it was not applied to operating
state. Restoring the full backup over later operating writes is not a recovery
step for this additive change.

PR #178's exact pending migration, Git blob
`266bea6efefb4770f5b5bc83046cbb36cb9e85ab`, and the current branch apply in
version order in a fresh disposable database; repeated `up` succeeds. Its six
mapping-method constraints coexist with the statement transition trigger and all
13 `LEGACY` routes. Operating state already had `202611020200` without pending
`202611020100` before this task. The new trigger migration has no dependency on
those pending constraint changes. It applies through ordinary Goose using the
current branch's migrations. No missing-version override, applied-version
renumbering or unmerged migration was used. The older gap remains a separate
PR #178 rollout prerequisite under the existing
[Goose ordering rule](https://github.com/pressly/goose/blob/v3.27.1/README.md#hybrid-versioning);
this compatibility check does not declare that pending rollout ready.

Migration `202611030100` applied **once**, with the existing 20-second statement
deadline and a five-second lock deadline. Readback verifies its sole new Goose
record and statement transition trigger. All 13 stage settings remain identical
and `LEGACY`. API health and readiness return HTTP 200. The running API still
reports `dev` with unknown code/lock metadata; no restart or runtime-deployment
claim is made. The manual recovery imports code directly from committed
`941594f`, verifies its parser bytes and version, and does not use the uncommitted
Phase B crosswalks.

The initial three occurrences pass exact checksum/parser/canonical-ID checks,
identical retries, conflict guards, preservation of original checked rows and an
unchanged earlier-cutoff eligible-history hash. All three already exist in the
operating database. Only the remaining 452 previously successful shadow
occurrences proceed in five-record transactions. All 275 held occurrences remain
excluded. The original failed composite-key preflight stopped before any football
mutation; its receipt is preserved, and the corrected check includes composite
primary keys without changing the data contract.

The completed operating replay verifies **455 of 455** expected canonical bindings
and identical retries, with no new conflicts or changed original checked rows.
All results already existed: retained history remains **479,461**, eligible
history **301,307**, published product forecasts **14,773**, and verified new
forecast availability **0**. This differs from the older shadow's 180 additions;
that restore predates operating acquisition. No shadow count is credited as an
operating recovery. The earlier-cutoff history count and digest remain identical
through both batches.

The **17:52:09.874108 UTC** read-only monitor finds 142,641 pending context reports
and zero recorded context errors. Since migration, existing workers completed
224 projections and 13 provider-acquisition work items without a recorded failure;
these background completions are not attributed to this replay. Health, readiness
and a public forecast-history read return HTTP 200. All 13 routes remain `LEGACY`.
The 275 held occurrences, pending PR #178 ordering and unknown running-build
metadata remain explicit limitations. Phase A operating checkpoint:
**PASS_WITH_WARNINGS**. Continue the independently authorized remediation.

Private receipts include the fresh backup manifest and restore verification,
`phase-a-migration-compatibility/result.json`, `phase-a-operating-migration.json`,
`phase-a-operating-small.json`, `phase-a-operating-expand.json` and
`phase-a-post-rollout.json`. They retain exact state, hashes, executed results and
per-occurrence bindings without publishing raw data or credentials.


## Phase B: FR-002 qualified native identities

**Code and shadow checkpoint: PASS_WITH_WARNINGS. Operating review remains in
progress.** Four of the five history-sufficient targets have exact source-backed
native relationships: Rochdale–Doncaster, Huddersfield–Luton, Northampton–Oldham
and Wigan–Mansfield. The fifth, Pamplona–Eibar, remains held: native/archive
kickoffs disagree, and no crosswalk is inferred from the club name.

The existing operational crosswalk table now explicitly links 14 API-Football
native IDs to their already accepted English archive origins, plus the CSV
Rochdale identifier to its accepted OpenFootball origin. Existing UUIDs,
historical mappings and source facts are not changed. These links use the
operational table, whose existing qualification resolves the country-qualified
archive origin; placing them in the historical importer table would derive the
wrong UUID. No new qualification rule or general name matcher was added.

The [machine-readable evidence](forecast-readiness-fr002-identities.json) records
all 14 native IDs, canonical roots, exact resource checksums, representative
native match/league/season IDs, source row keys and all 18 target dispositions.
Each relationship has 24–38 exact retained 2024 fixture matches, preserving both
participants, roles, country, competition, date, available exact time and final
score. Rochdale's older accepted OpenFootball origin also has 20 exact 2015
fixture bridges to the CSV identifier. Name normalization locates candidates;
these exact source/context comparisons establish the relationship.

Existing retained native resources cover leagues 40, 41 and 141. Two missing
2024 resources (leagues 42 and 43) were acquired through the existing client,
quota owner and immutable response registration. Requests used move 12→14 and
remaining allowance 88→86. Acquisition itself imports no history or admissions.
Legacy archive registrations are verified against their original raw checksums;
this does not retroactively claim a modern immutable manifest where none exists.
The provider's [native-ID documentation](https://www.api-football.com/news/post/how-to-find-ids)
and official fixture announcements support the research; they do not replace
retained native relationship proof.

The existing Resolution Center qualifies all 15 proposed cases. In the fresh
populated restore, separate case transactions append prospective approvals and
replay the same UUID requests without additional events. Earlier-cutoff history
hashes remain identical. The unchanged champion preview covers all **18** frozen
targets: **4 forecastable, 6 still short of eligible history, 8 identity-blocked**.
The older restore has stale schedules and is not used to infer availability.
The initial disposable request-ID and multi-case transaction attempts fail their
existing UUID/lock-order guards and roll back; successful execution uses the
existing per-case transaction contract. No check or lock rule was weakened.

Remaining identity causes are explicit in the inventory: Eibar timing;
Hornchurch/Scunthorpe/Worthing missing exact counterpart evidence; Tamworth and
three native IDs with mismatched canonical origins requiring reconstruction;
and two FotMob identifiers lacking qualified cross-provider context. Those cases
remain research/dependency work, not approved relationships.

Four focused regressions cover both archive providers, wrong country, an
unproved native ID with the same name, and tampered original bytes. The two
positive cases fail before the explicit links and pass afterward. Final
`env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATA_ROOT make check integration`
exits **0**: 1,819 Python unit tests, 16 Rust tests, 107 web tests, static/type/
complexity/architecture checks, builds and complete disposable storage/API
integration. Existing seven Python warnings and one ESLint warning remain.
Private proof, acquisition and fresh-shadow receipts stay under the existing
execution directory. No operating forecast gain is claimed at this checkpoint.


### FR-002 operating checkpoint

Committed policy `0dff481` passes the same 15 fresh qualified previews against
operating state. Separate Resolution Center transactions append prospective
reviews; exact UUID request retries return the original events. No historical
mapping, original history row or prior decision is edited. All 13 checked groups
of original source, mapping, history, admission, model and forecast registrations
retain their row hashes; the earlier-cutoff eligible-history digest is unchanged.

The reviews qualify **1,150 existing retained results** (not new raw imports).
Each new eligible fixture resolves its exact source and a prospective eligible
decision. All **38** contributing original resources, totaling **16,508,336
bytes**, are re-read and match their registered SHA256 checksums. The private
verification receipt contains every new fixture/source/decision relationship.

The unchanged champion publishes **four new forecasts** at **2026-11-03
17:58:24.720046 UTC**, before their 19:00/19:45 UTC kickoffs:

| Frozen target | Fixture ID | New forecast ID |
| --- | --- | --- |
| Rochdale–Doncaster | `ae988ae0-adc1-5335-9fc4-ff02bc44c51a` | `93469cdf-7d4e-5284-be6f-6e76c83edab5` |
| Huddersfield–Luton | `073b77c4-a7e6-5fbc-8957-2caffbc8e391` | `2830fc03-08c7-5ce9-87d4-b2da0276e022` |
| Northampton–Oldham | `8e72c406-288c-5dcf-ac8a-b3ae4f2f09eb` | `ac814b39-caaf-5a18-93fd-4284f0937a19` |
| Wigan–Mansfield | `993b50d0-3c38-52b7-8f62-bdee6cf6d637` | `183bfeee-fad1-5c09-8eba-b19685d2662e` |

All four public forecast-history and forecast-detail reads return HTTP 200.
Independent recomputation at each stored knowledge cutoff reproduces the exact
artifact, predictive-input and payload hashes, with target outcomes excluded.
The repeated bounded refresh creates **zero** additional forecasts. Champion
bytes remain `e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4`.
These four frozen-cohort gains exclude all earlier Coventry, Málaga and Armenian
recoveries. Their kickoffs elapsed before the later owner resume; the gains are
verified pre-match publications, not a claim that they remain upcoming.

The remaining 18-target dispositions are unchanged: six require eligible history
and eight retain specific identity proof/reconstruction blockers. Follow-up work
freezes 4,184 fixture-target and 14 observation-target records over 15 requests;
these overlap and are not 4,198 unique football fixtures. Scoped canonical pages
use the existing 32-target owner, source rechecks, ordered locks, leases and
receipts. Parity children remain for Phase D. Full FR-002 completion is not claimed
while those dependencies and follow-up remain. Operating checkpoint:
**PASS_WITH_WARNINGS**. Context errors remain zero and all 13 routes `LEGACY`.

Executed operating receipts: `fr002-operating-admissions.json` and
`fr002-operating-verification.json`; the tracked identity inventory binds the
verification receipt checksum. The initial verification assertion used a wrong
availability label; corrected verification uses the actual
`FORECAST_AVAILABLE` contract and passes. No production enum or check changed.


## Phase B: FR-003 retained-history predicates

The **2026-11-03 21:18:33.759267 UTC**, read-only repeatable-read inventory covers
all **41** frozen targets: 26 history-only cases and 15 Ghana-dependent cases.
It exports 4,606 distinct retained fixtures with source/decision IDs and examines
434 current mapping rows. The [predicate inventory](forecast-readiness-fr003-predicates.json)
records every target and binds the complete private row exports by SHA256.
It reports existing decision inputs, not a replacement eligibility engine.

Current exclusions overlap: 2,483 retained fixtures have unverified fixture
identity, 1,055 are excluded by fixture resolution, 1,072 home and 1,066 away
inputs lack a current source-provider mapping, 399 home and 408 away inputs have
untrusted mappings, and four lack trusted competition mapping. These counts are
not added into a match total. No excluded row has all current inputs passing;
there is no stale-decision-only recovery to perform. Dated history remains the
sole authority; no eligibility flag or frozen threshold is edited.

All 81 implicated current mappings pass retained-byte lookup but the existing
identity owner returns `UNSUPPORTED_ORIGIN_ALGORITHM` for their FotMob
`deterministic` method. None qualifies for an ordinary approval. An explicit
counterpart must be demonstrated through original native/context evidence;
adding FotMob to a generic origin allowlist would not establish that relationship.
Replaced Ghana participant mappings require FR-001 linked reconstruction;
quarantined/resolution-excluded rows require FR-008/016 source review. These are
exact upstream blockers, not missing-history claims or permission requests.

**Checkpoint: BLOCKED_DEPENDENCY; no operating change or new forecast gain.**
The 15 Ghana dependencies proceed next. The other counterpart and quarantine
cases remain tracked for their own source-qualified recovery. Counts use the
stated current knowledge cutoff and prior football; elapsed fixture records are
not presented as retrospective forecast recovery. JSON inventory checks,
project-status validation and `git diff --check` pass. No production code changed
in this checkpoint; the prior successful code aggregate is not rerun.

## Phase B: FR-001 replaced Ghana participant mappings

All 30 frozen targets retain their original participant facts. The two closed
FotMob mappings (`106975` Medeama and `2103806` Port City) have adjacent current
versions pointing to independently admitted API-Football identities. The
[exact relationship inventory](forecast-readiness-fr001-identities.json) binds
all eight original mapping versions, 12 prior admissions and checksummed native
resources. One common native fixture per participant agrees on both opaque team
IDs, orientation, aware UTC kickoff, country and competition. The registered
2026/27 season agrees with the current native season resource. The older Medeama
target resource remains explicitly labelled 2024/25; it is not represented as
current-season evidence.

The [Ghana FA's 2026/27 club announcement](https://www.ghanafa.org/index.php/eighteen-clubs-confirmed-for-2026-27-ghana-premier-league-season)
identifies Medeama as returning champion and Port City as a promoted debutant.
This supports the competition/history classification; it does not establish a
MatchForge UUID relationship or supply missing match records.

Migration `202611030200` extends the existing linked correction guard and history
qualification function. A closed deterministic FotMob version requires its
original mapping-change revocation, adjacent same-native current version,
independently admitted target and a real retained resolver contradiction. The
existing Resolution Center reviews the closed case through `CORRECT`; ordinary
`APPROVE` remains blocked. Source bytes, registered fixture/season context and
participant labels are checked for contradictions. Labels do not prove identity.
All original mapping rows stay closed and unchanged. No generic FotMob origin
permission is added.

The fresh operating backup at **2026-11-03 22:20:40.531141 UTC** is
1,529,811,963 bytes, SHA256
`62898d0989e23fc196ca82e993534acbe422f6cca1f71e5d84259a1baa0bf40a`.
Its owned restore reproduces all nine protected registration digests, original
function definitions and stage settings. Normal Goose upgrade/retry preserves
those digests and all 13 `LEGACY` routes. The two real reviewed corrections and
retries complete in **4.172 s** and **1.883 s** within existing deadlines. All
13 checked original table populations, all 30 physical fixture rows and the
earlier eligible-history digest remain unchanged. The corrections add no
eligible history: old duplicate/quarantine exclusions remain effective.

The initial full preview exposed one additional compatibility defect: forecast
admission still required open mappings, even after a qualified closed-version
reconstruction. All 30 remained blocked. Three failing regression cases reproduce
that forecast check and missing/tampered closed-source rechecks. The existing
forecast and recovery checks now include only active linked reconstructions;
all three focused regressions pass. Withdrawal removes current permission, and
fresh recovery checks reverify the closed source bytes. The completed shadow
publication verifies all 30 source qualifications and removes every identity
blocker. Exactly **15** targets satisfy the unchanged champion history rule.
All 15 shadow forecasts reproduce their exact artifact/input/payload hashes at
original cutoffs, exclude the target outcome and predate kickoff. Repeated
refresh creates zero forecasts; prior forecast rows remain unchanged. The other
15 targets retain insufficient eligible history and proceed through FR-004.
These are shadow results, not operating forecast gains.

Recovery also passes: prospectively withdraw the two new linked decisions, keep
their original rows and earlier history intact, and restore the captured prior
function definitions through an ordinary forward Goose migration/retry. Do not
restore a dump over concurrent operating data. Scoped publication must stop
before withdrawal or schema recovery. The exact pending PR #178 migration and
all branch migrations pass ordered upgrade/retry in a separate empty database;
its existing operating ordering gap remains a separate prerequisite.

The changed shared history function also passes the original populated DED, PD
and BSA deadline trials with admission times **7.265 / 6.047 / 3.746 s** under
the existing 20 s limit. Exact reference decision facts, refresh-key parity and
earlier-cutoff history all match. Each trial rolls back in the owned earlier
restore; these measurements are not additional operating admissions.

**Implementation checkpoint: PASS_WITH_WARNINGS.** Final
`env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATA_ROOT make check integration`
exits 0 after the final consumer changes: 1,819 Python unit tests, 16 Rust tests,
107 web tests, strict types/static/complexity checks, builds, all disposable
storage/migration tests and PostgreSQL/Redis/Go API integration. Seven existing
Python dependency warnings and the existing ESLint warning remain. The initial
private rehearsal script field-name error was corrected before any shadow review;
protected digests were rechecked on restart. No test or guard was weakened.
Operating migration/corrections and operating forecast gains remain zero at
this code checkpoint; the owner-authorized bounded rollout follows separately.

### FR-001 operating verification — 9 November 2026

**PASS_WITH_WARNINGS.** Both proven FotMob replacements now have prospective
linked corrections. All 30 frozen Ghana targets pass identity qualification.
Fifteen have new public forecasts; the other 15 report `NOT_ENOUGH_HISTORY`, with
Port City still at six eligible results against the unchanged ten-match minimum.
No historical result was added or newly qualified by this reconstruction.

Execution used unchanged, pushed commit `5cb3a1a`. After the interruption, a new
consistent backup at **2026-11-09 11:31:13.794193 UTC** captured 1,632,319,418 bytes,
SHA256 `14e1c00d674f4bbe408166c79119ecfd8860ec698ba6ba080a20019295cc88d7`.
Exact restore, source bridges, populated forecast publication, prospective
withdrawal/forward repair and pending PR #178 compatibility were reverified.
The prior full aggregate remains the verified code result; no application code
or lockfile changed during this data-only execution.

Goose applied `202611030200` once. The first source-checked forecast was issued at
**12:11:39.689444 UTC**. Execution then stopped when a whole-row check detected
changed freshness metadata on a different, finished 8 November fixture. Exact
backup comparison found only `last_fetched_at`, `cache_expires_at` and
`stale_after` advancing through normal background fetches. Original observation
time, source registration, identifiers, scores and other football facts matched.
These cache fields are explicitly mutable in the existing freshness migration
and writer; they were not rolled back or treated as new football knowledge.

The private checker now verifies original facts separately from those documented
cache fields. Rolled-back probes reject changed/deleted facts, clock rewinds,
future fetch clocks and cache edits without a newer fetch. A pristine backup
reference rechecked all 13 global prior populations and three affected
observation/decision populations before continuation, and again afterwards.
Whole-table verification reads use bounded cursor/key batches; application
statement and lock deadlines remain 20 s / 5 s.

The Port City correction and retry then passed. Fourteen further forecasts were
issued by **12:56:16.259450 UTC**, making **15 actual new forecasts**, all before
kickoff. Every forecast passes public history/detail reads, exact original-cutoff
artifact/input/payload reproduction, target exclusion and byte verification of
its historical inputs. Twelve original resources qualify those windows.
Publication uses database-stamped, frozen knowledge cutoffs; repeated refresh
creates zero forecasts. History-short availability updates use the existing
forecast owner and cannot publish an unexpected forecast outside the verified set.

Final checks find zero changed original football facts, zero lost eligible
history, unchanged earlier-cutoff history and zero regressions among **2,250**
previously available controls. One valid background cache advance is recorded
separately. All 13 routes remain `LEGACY`; context errors remain zero. Physical
fixture IDs, participants, competition, kickoff and identity status are retained.
No API deployment, model promotion, cutover or historical identity rewrite occurred.

These same 15 targets fulfil the 15 Ghana dependencies in FR-003; they are counted
once. Its remaining 26 targets retain their exact source/identity/resolution
blockers. Cumulative new availability within the frozen cohort is **19**: four
English forecasts issued before kickoff on 3 November and these 15 Ghana
forecasts on 9 November. The four English kickoffs have elapsed; they are not
currently upcoming gains. Earlier Coventry, Málaga and Armenian recoveries and
unrelated background additions remain excluded.

The existing [FR-001 inventory](forecast-readiness-fr001-identities.json) records
all 30 before/after results, forecast lineage, source hashes and private receipt
checksums. Local execution and forensic receipts remain under
`resume-20261109`. FR-004 proceeds for the legitimate remaining history gaps.

## Phase B: FR-004 native-history checkpoint — 9 November 2026

**IN_PROGRESS; no new history or forecast gain.** A read-only snapshot at
13:32:09 UTC preserves all 150 original raw-deficient target IDs, including
122 history-only and 28 identity-dependent targets. Of these, 104 kickoffs have
elapsed and 46 remain future. Sixteen now have ten eligible results per team;
15 are elapsed and the one future target already reports forecast availability.
These current counts include independent background changes and are not recovery
attribution. No retrospective forecasts are published.

The existing importers parse all 28 retained FotMob league resources after exact
SHA256 checks; one API-Football resource in the native-scope inventory is also
byte-verified. The five priority teams still have six eligible results for Port
City, five for Garudayaksa, three for Bắc Ninh, two for Dhaka Wanderers and four
for City Club. Prior top-flight seasons contain no native Port City, Garudayaksa
or Bắc Ninh participant rows. Lower-division coverage requires further native
catalogue evidence. The [GFA promotion report](https://www.ghanafa.org/index.php/port-city-fc-clinch-ghana-premier-league-qualification-with-four-games-to-spare)
confirms Port City's earlier senior participation, without supplying importable
native match records.

Dhaka's retained FotMob 2024/2025 resource contains 18 exact finished native
match IDs: six provisional fixture/history rows and 12 unmatched observations.
The current importer rejects the missing reviewed season correspondence;
opponent identities also need qualification. The retained API-Football
`history-398-2024` source was independently byte-verified: its 90 results cover
December 2023 to May 2024 and exclude Dhaka's native team ID. It is not a
replacement for the following season. The configured 2024 API season cap is
preserved; neither season labels nor club links are inferred from dates/names.

One supported-client FotMob `all_leagues` acquisition attempt deferred with
`LIVE_SYNC_HAS_PRIORITY`, before any HTTP request or source registration. Its
receipt records 14:36:29 UTC as the next attempt time. No quota, live-priority
guard, admission or source constraint was changed. Remaining team/season slices
and lower-division discovery remain open; this is not an exhaustion claim.

The [150-target evidence](forecast-readiness-fr004-history.json) records original
and current counts, all 18 Dhaka native IDs, source hashes, exact dependencies
and private receipt hashes. Application code and dependencies are unchanged.
Validation: evidence inventory/hash assertions, project-status validation and
`git diff --check`.

## Phase C: FR-005 Scottish revalidation checkpoint — 9 November 2026

**BLOCKED_EVIDENCE.** All 41 affected current `World` mappings already have dated
`UNRESOLVED: RETAINED_SOURCE_EVIDENCE_REQUIRED` admissions, appended between
21:20:48 and 21:24:40 UTC on 3 November. Fresh verification agrees. This differs
from the older investigation's stored `ORIGIN_ANCHOR` snapshot. This checkpoint
adds no operating decision and does not re-admit a competition or merge clubs.

The source census verifies 45 Scottish archive/CSV resources through the existing
bounded ZIP/CSV readers. They contain 129 member occurrences over 33 seasons,
1994/95 through 2026/27, and 50 exact labels. The 17,922 parsed occurrences overlap
across resources and are neither distinct recovered fixtures nor forecast gains.
All parsed Scottish rows retain the corrected country, source identifier and
recorded kickoff precision. The existing 2000/01 cohort remains 180 rows per code.

The full period inventory keeps Airdrie (1994/95–2001/02), Airdrie Utd (2002/03
onward), historical Clydebank (through 2001/02), Gretna (2002/03–2006/07),
Edinburgh City/FC Edinburgh and Raith/Raith Rvs as separate labels. These source
periods are evidence to investigate, not an automatic club-continuity decision.

Rollback-only revalidation in the owned populated restore processes each exact
mapping twice and appends zero admissions: the existing decisions are already
current. Both historical and current SC2 fingerprints remain exact. At the frozen
3 November 15:43:07 cutoff SC2 still reconstructs 5,137 Football-Data.co.uk rows
plus 186 API-Football rows. At the new cutoff only the 186 API rows are eligible,
reflecting the already-dated exclusions. The historical 5,137 rows are preserved;
this checkpoint claims no new exclusion or recovery.

The remaining correction needs an independently qualified dated target for each
legacy origin. The current linked-correction implementation supports proven FDO
and replaced FotMob cases, not an unproved Scottish namespace/continuity merge.
No generic origin allowlist, source-country rewrite or unsupported correction is
introduced. The [41-mapping census](forecast-readiness-fr005-scottish.json) records
all periods, exact source hashes and rollback/preservation receipts.

Validation: source/resource and 41-mapping inventory assertions, rollback/retry
and historical/current fingerprint checks, project-status validation and
`git diff --check`. Application code and dependencies are unchanged.

## Phase C: FR-008 original-input replay checkpoint

**IN_PROGRESS; operating imports and new forecast gain remain zero.** Both exact
Málaga inputs reproduce the canonical team/timestamp rejection in the owned
restore. Each has an OpenFootball history neighbor at the same instant and a
Football-Data.co.uk neighbor one hour earlier. Exact score agreement does not
qualify the different participant/competition roots or repair timing claims.
The originals and all active resolutions remain unchanged.

All 46 retained Coventry inputs were replayed separately with rollback. Four
native IDs (`540714`, `540933`, `540989`, `541195`) hit the canonical guard.
A combined shadow batch of the other 42 rows binds every native ID to its exact
registered source, timestamp and score; 36 are eligible and six remain held.
Retry inserts zero, and the pre-import knowledge-cutoff history hash is exact.
This is an importer characterization, not authorization to treat the rows as
unique real fixtures or claim operating recovery. Exact duplicate/identity
qualification and the broader CSV conflict inventory remain open.

Inspection also finds that `_store_fallback_fixtures` uses the current competition
season instead of the explicit older source season. Coventry's retained rows
carry season ID 2416 and `startDate=2025-08-08`; materializing these against the
current competition label would produce a different season/fixture identity
from the history importer. FR-009 will characterize and fix that current source
metadata defect before any such operational recovery.

[Exact input dispositions](forecast-readiness-fr008-conflicts.json) include the
complete 46-ID list, two Málaga neighborhoods, shadow eligibility and private
receipt hashes. Validation: source checksums, per-row rollback, combined native
lineage/retry/cutoff assertions, project-status validation and `git diff --check`.

## Phase C: FR-009 source-season implementation

**Source-season fix VERIFIED; FR-009 remains IN_PROGRESS.** FDO fixture
materialization now uses each returned `season.startDate`, rather than the current
competition label. The parser requires a real canonical `YYYY-MM-DD` date.
Missing/malformed metadata and a source season that contradicts an existing
native registration fail explicitly. Existing registered IDs are preserved.
No migration, dependency, configuration, forecast mathematics or origin policy
changes. The existing competition-existence helper is reused.

Seven integration cases failed on the old behavior. Nine final regression cases
cover historical/current seasons, malformed/missing dates, stable replay after
a competition label changes, fixture/history identity agreement and rejection
of a changed season for an existing native ID. All 29 fixture-reconciliation
cases pass, including the prior mismatch and quarantine safeguards.

In the populated owned restore, all 46 authentic Coventry inputs materialize
with their explicit 2025 source season, matching the 42 previously characterized
history IDs. Retry adds zero history; the earlier knowledge-cutoff history
fingerprint remains exact. These transactions roll back. Coventry operating
imports remain withheld pending the FR-008 identity/unique-representative proof.

The read-only 14:11:41 UTC native inventory examines 95,402 provider/native keys.
It separates historical unmatched revisions from 13,292 latest null observations,
then separates 57 current accepted fixture bindings. The remaining diagnostic
population is 10,975 FotMob and 2,260 PitchAPI observations, including 10,779 and
2,083 finished observations respectively. These are diagnostic populations, not
new canonical matches or forecast promises. The historical diagnostics API
contract and immutable observations are unchanged. Two initial unbounded
diagnostic joins time out at the existing 20-second limit; indexed 256-key
queries complete the census without raising that limit or changing product SQL.

All three source resources behind 58 old missing-function failures verify
exactly. The function now exists. A combined rollback-only replay through the
existing owner reconciles all 58 associations and retries to the same fixtures.
All remain provisional: 25 retain ineligible history, and 33 with unknown score
basis correctly withhold history. Global eligible history and earlier-cutoff
fingerprints remain exact. The first private receipt check incorrectly assumed
every replay should create history; it stopped and rolled back. The corrected
check records withheld history separately and still requires every fixture to
remain provisional and never eligible. No production guard was weakened.

Final validation after the last code change:
`env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATA_ROOT make check integration`
**exits 0**: 1,819 Python unit tests, 16 Rust tests, 107 web tests, configured
format/lint/type/complexity/architecture checks, builds, fresh migrations and
complete storage/API integration. The [FR-009 evidence](forecast-readiness-fr009-source-seasons.json)
pins source/test hashes, the native census and all verification receipts.
Operating replay and remaining exact season/identity/canonical proof are still
open; no additional operating history or forecast gain is claimed.

## Phase C: FR-010 native scope qualification holds

**IN_PROGRESS; approved policy rollout verified, scope dependencies remain.** The
17:57:18 UTC inventory binds all 1,224 native scopes and 656 legacy queue rows to
their work records. Native results include 238 typed identity failures, 96 mixed
error results and 17 live-priority deferrals. Both completed scopes still have
full qualified expected-ID coverage: 179/179 and 132/132. The expired French
scope has 306 source-verified results and zero currently qualified; an expired
lease does not qualify its history. Live-sync heartbeats are fresh. Queue age
alone does not establish continuous deferral or justify a scheduling change.

The shared driver previously retried every failure. Additive migration
`202611090100` holds the four exact typed qualification failures only when the
summary agrees with the error. Transient failures, empty advertised seasons,
mixed results and live-priority deferrals keep their retry deadlines. Claims
skip held scopes so ready siblings can proceed. The existing explicit refresh
releases only selected due scopes, preserving attempts and advancing the shared
generation. Existing failed scopes are not rewritten retrospectively.

Six regression cases fail on the old behavior; eleven final policy cases pass.
The two focused history integration modules pass all 41 cases. Tests cover
cooldowns, selected refresh, sibling progress, attempt history and old-worker
fencing. PostgreSQL's [queue-locking documentation](https://www.postgresql.org/docs/18/sql-select.html)
supports retaining the existing `FOR UPDATE SKIP LOCKED` claim. No new scheduler,
quota bypass, entitlement change or completion shortcut is introduced.

A fresh exported-snapshot backup at 18:20:39 UTC contains 1,655,858,955 bytes,
SHA256 `8b3467c627554feda99e5c01e38c6460403e8bfe2903d0c9198f13a82d12159d`.
The new isolated restore matches all nine protected registration fingerprints
and the captured prior function. Normal Goose upgrade/retry, all eleven policy
cases in that populated restore, and captured-function forward repair/retry
pass. All nine fingerprints and thirteen LEGACY routes remain exact after each
stage. The exact pending PR #178 migration also passes normal ordered upgrade
and retry in a separate empty database, preserving its constraints and the
statement trigger. No missing-migration override or applied-version rewrite is
used; the operating migration-order prerequisite remains unchanged.

Final `env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATA_ROOT make check integration`
exits **0**, including configured static checks, 1,819 Python unit tests,
16 Rust tests, 107 web tests, builds, fresh migrations and complete storage/API
integration. The [FR-010 evidence](forecast-readiness-fr010-scope-policy.json)
pins the source, test and receipt hashes.

The owner approved bounded rollout under remediation-plan acceptance step 7.
At 18:43 UTC the operating
preconditions passed, migration `202611090100` applied once through normal Goose,
and repeat upgrade was a no-op. The exact closed FotMob `10186/2021` sample was
first rehearsed in the populated restore, then replayed through the same owner
in operating. Native IDs `3747099` and `3747100` reuse their authentic retained
source: two rows skipped, zero HTTP requests, zero new history or eligible
results, and zero new forecasts. The typed identity result enters shared
`BLOCKED`; retry returns no claim and adds no attempt.

All nine original populations, both fixtures' football facts, original
observation facts and the earlier-cutoff history fingerprint remain exact.
The migration record occurs once, context errors remain zero, all thirteen
routes stay LEGACY, and health/readiness return HTTP 200. No runtime restart was
required. This operational checkpoint is **PASS_WITH_WARNINGS**: the hold policy
works, while the missing identity/source qualifications and expired/partial
scope recovery remain open. No forecast gain is attributed to queue handling.

## Phase C: FR-011 authentic originals and governance

**BLOCKED_EXTERNAL.** Fresh read-only checks cover all frozen
33 raw registrations, 22 datasets and 26 models. All 84 registered file paths
are missing. A bounded search checks registered basenames, checksum filenames
and three retained backup archives: 10,449 candidate files and five archive
members are hashed, with zero exact originals found. Tool caches are excluded;
arbitrarily renamed files are not exhaustively scanned. The Scottish legacy ZIP
passes and remains outside the missing-original cohort. No bytes, manifests,
registrations or historical facts are changed.

The initial registered dependency checks confirm 18 model links across thirteen
forecasts and all thirteen existing retirement events. One missing model,
`01a06fc4-d748-725e-853e-359f4b651cbb`, had the latest `BASELINE_APPROVED`
event for `match_result/baseline`. Forecast retirement does not retire this role
or restore its model manifest. The product forecast preparer reads its explicit
artifact file; this audit changes neither that file nor the serving champion.

An append-only `RETIRED` event uses the existing promotion
registry. Its rollback-only populated rehearsal publishes once, verifies retry,
preserves every prior promotion and the original 26 model/thirteen forecast rows,
then rolls back completely. Retirement leaves that role without an
approved model. [Model governance](../model-governance.md#promotion) requires an
explicit retirement event. No replacement
model or changed evaluation is proposed. Missing source/dataset/model originals
continue to block integrity and parity independently of this decision.

The [81-case evidence](forecast-readiness-fr011-originals.json) records every
registered path/hash, dependency, existing retirement, search scope and proposed
event. Verification uses the existing resource/dataset/model verifiers, exact
file hashes, read-only dependency queries, rollback/retry assertions,
project-status validation and `git diff --check`. Production code is unchanged;
its complete FR-010 aggregate remains valid.

The owner approved the exact retirement. Event
`e20cd209-d4f9-5e65-8d60-789345577327` is appended through the existing registry
after locking and rechecking the latest role event. Retry verifies the same
event. All four prior promotions and every original row in the six checked
model/file/forecast/retirement populations remain exact. The serving champion
file hash is unchanged, health/readiness return HTTP 200 and all thirteen routes
remain LEGACY. A fresh latest-role query finds zero approved missing models.
No replacement artifact or new lifecycle policy is introduced. This disposition
is **PASS**; FR-011 remains blocked on the 84 exact original files.

## FR-004 native catalogue follow-up

The guarded retry acquires and registers a genuine 86,027-byte FotMob catalogue
at 18:57:54 UTC, SHA256
`6cfddd007ca90c78bf412c885b06241167eda01dbcf4fa1b8459fe799cdf3067`.
Its four relevant country entries advertise Indonesia Liga 2 `10056`, Vietnam
qualification `9628` and cup `10161`; Ghana's Division One and Bangladesh's
second tier are not advertised in this response. These are acquisition leads,
not approved competition or club relationships.

The first targeted catalogue request defers under `LIVE_SYNC_HAS_PRIORITY` until
20:01:07 UTC. No retained response is registered under these three catalogue
keys. The retained PitchAPI catalogue has 77 leagues and no entries for these four countries, using
its actual `country_code` field. No further provider absence is inferred.
The [FR-004 evidence](forecast-readiness-fr004-history.json) retains exact native
IDs, country entries and receipt hashes. History imports, identity admissions and
forecast gains remain zero for this acquisition checkpoint. Status validation,
exact source/receipt assertions and `git diff --check` pass; code is unchanged.

## Phase C: FR-013 report projections

**Target cohort PASS; global backlog IN_PROGRESS.** The frozen 196 context scopes
and fourteen performance scope/horizons all reach their requested generations.
Seven bounded batches select 181 scopes, publish 174 new context reports and
reuse seven existing performance inputs, with zero failed projections or lost
leases. New requests remain protected by the existing generation and source-hash
checks. No completion counter is set outside the existing report owner.

All 174 new input/body hashes verify and every context body reproduces from its
stored input. Checks cover 24,022 prior history rows and 100 already-known future
schedule rows: target outcomes are absent, knowledge cutoffs hold, and same-day
date-only results stay excluded. Six public context responses, three fixture
list/detail/history groups and all fourteen public performance horizons agree
with their stored records, fingerprints and probabilities. Original model and
forecast rows and the serving champion hash remain exact; thirteen routes remain
LEGACY. Report processing creates no forecast gain.

During the 16.210-second operator window, the global pending context count moves
from 136,150 to 135,949. Requested generations advance by two and completed
generations by 606; these include background work and collapsed requests, so they
are not report or forecast counts. An initial private selector rejected the
native `-infinity` timestamp before any projection. Using the database's existing
due-time comparison resolves that operator error without a production change.

At 19:44:34 UTC the remaining 135,612 context scopes are frozen for continued
processing through the existing bounded worker. The existing 149,467 reports
occupy 612,720,640 bytes; local PostgreSQL storage has sufficient available
capacity. The [report evidence](forecast-readiness-fr013-reports.json) pins the
complete private scope/generation inventory, receipt hashes, temporal checks,
public checks and measured counters. No throughput optimization is justified by
the completed cohort. Validation: full byte/source/cutoff/generation assertions,
project-status validation and `git diff --check`; production code is unchanged.

## FR-013 global backlog and context indexes

**Index change PASS_WITH_WARNINGS; operating rollout pending.** The existing
worker stops cleanly after 207 bounded batches: 6,243 reports published, 380
already complete or busy, one statement deadline and zero lost leases. Of the
135,612 frozen generations, 128,641 remain; the global pending count is 128,728.
Background completions and new requests are recorded separately. All original
model/forecast rows and serving champion bytes remain exact. The failed fixture
is retained with its ordinary retry deadline; no completion counter is forced.

Profiling the next-fixture lookup finds 225,957 unrelated fixture rows scanned
per team. Migration `202611090200` adds two B-tree indexes on participant and
kickoff. PostgreSQL can [combine the two indexes for the existing OR predicate](https://www.postgresql.org/docs/18/indexes-bitmap-scans.html).
The wider candidate's included timestamp was unused by the bitmap heap scan, so
the change retains only the two lookup columns. The function and its ordering,
football/knowledge cutoffs, history eligibility and generation checks are unchanged.

A fresh 1,668,627,121-byte consistent backup restores with all nine protected
registration fingerprints and thirteen LEGACY routes intact. All 196 original
contexts, sixteen frozen backlog contexts and two profiled/failing fixtures
retain identical inputs before index creation, after creation and after removal.
Each comparison shares one statement timestamp, preserving future-fixture
knowledge cutoffs exactly. Normal Goose upgrade/retry, down to the preceding
version and re-upgrade/retry pass. Exact pending PR #178 migration ordering also
passes in a separate disposable database.

For one elapsed fixture, six uninstrumented queries per state give warm medians
of 82.278 ms before and 2.145 ms after, excluding each first query. This is a
38.36-fold improvement for that query, not an estimate for the entire backlog.
Its source fingerprint is identical and the final nested plan uses both indexes.
The [evidence](forecast-readiness-fr013-reports.json) pins the full parity,
backup, lifecycle, plan and timing receipts.

The aggregate passes static checks, 1,819 Python unit tests, sixteen Rust tests,
107 web tests and all but two storage checks. The browser check initially fails
to launch Chromium; the operational fixture check fails its mapping clock-order
constraint. Both pass in a fresh disposable retry with unchanged code and tests;
the subsequent PostgreSQL/Redis/API integration checks also pass. No operating
index migration has been applied. Acceptance step 7 requires separate rollout
authorization before the bounded operating sample and backlog continuation.

The owner approved the exact index rollout, 32-report sample and bounded
continuation of the original frozen backlog. Health/readiness, available disk,
the restored backup hash and migration source pin pass before application. No
fixture writer holds a conflicting lock at the check; Goose uses a 500 ms lock
wait limit and the existing 20-second statement deadline. Normal upgrade takes
0.512 seconds and retry is a no-op. Both indexes are ready/valid; the context
function is unchanged.

All 32 selected frozen contexts publish in 0.756 seconds. Every input/body hash,
reproduced body and completion generation verifies. Three public context
responses agree, including the previously timed-out fixture. All original rows
in nine registration populations remain exact after migration and after the
sample, including 18,106 existing product forecasts. Serving champion bytes and
thirteen LEGACY routes are preserved. Disk space remains above 252 GiB during
temporary verification; health/readiness return HTTP 200. The elapsed-fixture
source hash also stays identical in six operating queries per state. The sample
is **PASS**. Continued projection is limited to the original frozen fixture IDs,
with bounded batches and automatic stops on failures or integrity/resource issues.
