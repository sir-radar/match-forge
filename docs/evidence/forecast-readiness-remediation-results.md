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
| FR-001 | NOT_STARTED | Exact Ghana participant continuity and Port City history |
| FR-002 | IN_PROGRESS | 15 reviews/4 public forecasts verified; 8 identity and 6 history holds; scoped follow-up running |
| FR-003 | BLOCKED_DEPENDENCY | All 41 target predicates inventoried; FR-001/008/016 and exact FotMob counterparts required |
| FR-004 | NOT_STARTED | Authentic missing team/season slices |
| FR-005 | NOT_STARTED | Scottish historical namespace relationships |
| FR-006 | VERIFIED | Batched context invalidation; authorized operating migration verified |
| FR-007 | BLOCKED_DEPENDENCY | 455 verified operating aliases/retries; 275 held occurrences require FR-005/008 |
| FR-008 | NOT_STARTED | Original-row canonical conflict evidence |
| FR-009 | NOT_STARTED | Current unmatched revisions and exact season metadata |
| FR-010 | NOT_STARTED | Scope-specific failure/retry classification |
| FR-011 | NOT_STARTED | Exact missing originals/manifests or lifecycle blockers |
| FR-012 | NOT_STARTED | Full-scope comparison evidence and Phase 35 readiness gate |
| FR-013 | NOT_STARTED | Bounded backlog processing and measured throughput |
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
