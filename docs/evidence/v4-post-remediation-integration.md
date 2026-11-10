# PR #178 integration after PR #179

Status: PASS_WITH_WARNINGS. Code integration is verified and ready for review; operating rollout and merge remain separately authorized.

The integration starts at `5ab0569b910c12aa45dd49e1917ba8528f8990e1`, the
PR #179 merge, and merges PR #178 head
`463ec15a8a0720fb48e842af5a009cf140545f90`. Their merge base is
`8b82dd637449a18ea6086853344e8bc7b0e0f2e2`. Git fetch confirmed these heads.
The existing main checkout and separate fixture-filter task were preserved.
The integration branch is `ft/v4-post-remediation-integration`.

The accompanying JSON records every one of PR #178's 226 changed files and all
18 overlapping paths. Textual conflicts occurred in `AGENTS.md`,
`docs/project-status.json`, `docs/source-acquisition.md`, and the three
`resolution_files.py`, `resolution_parity.py`, `resolution_recovery.py` modules.
Other overlapping changes were reviewed even though Git combined them cleanly.

## Implementation decisions

| Area | PR #178 approach | Main / PR #179 approach | Selected approach | Evidence and justification |
| --- | --- | --- | --- | --- |
| Retained identity verification | Shared checksum/manifest reader, strict StatsBomb and ESPN native indexes; unchanged canonical trust rules | Exact rolling CSV source occurrences, source-season and country qualification, historical correction guards | Consolidation through the existing verifier and shared registration reader | Incoming changes extend provider dispatch; main's CSV/geography and linked correction logic stays intact. Existing native-proof, negative-origin, Ghana, English and correction regressions run together. No source-native proof becomes canonical admission. |
| Operational provider sync | Compare retained match clocks and valid provider timestamps before changing live scores; disclose unresolved disagreements | Keep original names when no search alias exists, preserving native identity storage | Both through the existing sync owner | Alias handling and football ordering solve distinct failures. Existing alias regression and added stale/equal-clock and cross-provider regressions cover the combined code. No second sync or identity owner. |
| API-Football client | Statistics, events and player resource methods reuse `_get` | Provider failures, quotas and bounded historical selection | Existing bounded client plus resource methods | New methods use the same request-budget and transport path; they do not activate acquisitions or replace provider failure isolation. |
| Resolution work scheduling | Database clock for immediate eligibility, with explicit clock-skew tests | Same database clock fix with a different local variable name | One database-clock implementation; incoming parameterized regression retained | Both implementations are behaviorally identical. Retain main's `now` name and the useful incoming comment. No duplicate production code retained. |
| Serving and contracts | Match-clock ordering, score conflict disclosure and scoped read-only market diagnostics | Unknown-season handling and current fixture safeguards | Additive combined Go, OpenAPI and TypeScript contracts | Changes touch separate request/query fields and preserve existing optional-field defaults and canonical scope guards. Contract, Go serving, component and API tests verify compatibility. |
| Raw/experimental storage | Explicit target and operating URLs, server identity/OID checks, persistent isolation marker and pinned connection | Existing immutable retention and historical recovery | Incoming isolation guard on experimental paths; existing operational path retained | Experimental writers cannot inherit an operating target. Source and artifact owners stay shared. Isolation and publication-fencing regressions are mandatory. |
| Migration history | Earlier `202611020100` adds honest `provider_native` metadata without changing old claims | Operating history already extends through `202611100100`, skipping that earlier version | Preserve exact original SQL under `infrastructure/migrations/legacy-v4/`; active forward-only `202611100200` | Read-only operating history confirms the gap. Four existing V4 databases already contain the older version. Retain those records and original bytes; upgrade both histories normally without `allow-missing`, fabricated versions, renumbering or reinterpreted identities. |
| Engineering guidance and state | Frontend/backend standards and V4 checkpoints | Latest owner navigation rules, remediation checkpoints and provider-wide access register | Main guidance plus unique engineering requirements; both status histories; one current access policy | Cosmetic blank-line changes discarded. Current main timestamp retained until this integration checkpoint. Source access and downstream qualification remain distinct; task-specific prohibition on acquisition is binding. |

No conflicting model implementation was selected, no model mathematics were
changed beyond integrating PR #178's existing distribution projections, and no
production routing or forecast result was changed by this task. No new performance
claim is made. Main's bounded context-refresh migrations and their committed
profiling evidence remain intact; PR #178 does not replace them.

## Migration compatibility and recovery

The operating database has `202611020200`, `202611030100`, `202611030200`,
`202611090100`, `202611090200` and `202611100100` applied. It has never applied
`202611020100`. Four V4 identity-recovery experiment databases have applied that
older migration. All such databases were inspected read-only.

Goose 3.27.1 discovers `*.sql` directly in its selected directory and refuses
missing older migrations. Its [versioned implementation](https://github.com/pressly/goose/blob/v3.27.1/up.go)
confirms that inserting the old file into the active list would block the operating
upgrade. Relocating the original bytes outside that list preserves the legacy
migration for historical recovery. An additive later migration supports either
history without altering existing rows or Goose records. The new migration
refuses downgrade; use a separately reviewed forward repair. The original legacy
Down remains preserved for historical restore procedures only.

The two-history regression tests inject a failure after the first ALTER, verify
transactional rollback of constraints and version history, then upgrade/retry and
verify original claims, sources, decisions and admissions. Fresh database and
populated operating-restore checks are required before this task passes.

## Provider integration audit

This is an offline code/interface audit. Coverage and access limitations below
are existing recorded states, not newly acquired evidence. No provider was
queried, activated or scheduled by this task.

| Provider | Preserved implementation and integration | Qualification / remaining limitations |
| --- | --- | --- |
| FotMob | Operational sync/history owner, native parsers and normalized resources | Existing identity/season and access gates remain; bounded history and live priorities preserved. |
| PitchAPI | Operational sync, native season checkpoints and rich normalizers | Existing quotas, live priority and source-specific semantics remain. |
| API-Football | Bounded product/history client plus native rich statistics, events and player ports | Existing account entitlement and qualification remain; ports do not activate requests. |
| football-data.org | Existing explicit-crosswalk history fallback and native normalizers | Credentials, plan limits and historical identity qualification unchanged. |
| Football-Data.co.uk | Immutable CSV/ZIP acquisition, rolling occurrence versioning, historical importer | Exact source/season/country rules and correction guards preserved; no new import. |
| OpenFootball | Commit-pinned mirror, bulk JSON importer and native contracts | No event/player/xG capability invented; existing history qualification retained. |
| StatsBomb | Pinned acquisition/canonical ingestion, shared registered-resource reader, native identity and observation normalizers | New surrogate claims use `provider_native`; old deterministic claims and blocked independent crosswalk proof remain unchanged. No admission. |
| Understat | Existing source pipeline, native parser and results/shot normalizers | Experimental only; source timezones, coordinate semantics, identity and historical qualification stay explicit. |
| ESPN | Source pipeline, native parser, scoped summary identity and rich normalizers | Native event/league/competitor proof is distinct from canonical qualification. Experimental chains remain blocked where previously recorded. |
| WhoScored | Source pipeline, native parser and season/stage-aware normalizer | Exact requested season/stage checks retained; reachable pages do not establish full coverage. |
| Flashscore | Existing experimental source pipeline and summary/event/statistic/lineup normalizers | Source restrictions and shared upstream dependence retained; no independent confirmation or production activation inferred. |
| Soccerway | Existing experimental source pipeline with shared native resource contracts | Livesport dependence, source restrictions and canonical qualification remain visible. |
| FBref | Retained original-HTML/archive normalizer and shared immutable registration/observation publication | Existing recorded partial archive support; missing seasons, score basis, player membership and source access remain outside this task. |
| Sofascore | Retained event/statistic/lineup/incident normalizer and shared publication | Existing recorded partial support; unknown period meaning, historical completeness and membership remain unqualified. |
| ClubElo | Retained dated CSV rating normalizer and shared publication | Existing recorded snapshot support; native target identity/history and unverified chart parsing remain limited. |

Source retention and retries use the shared registration, immutable files and
observation identities. V4 observations remain experimental; provider availability
is not forecasting eligibility. Existing research/market/player/source blockers
remain unchanged. No obsolete competing ingestion, identity, recovery or
publication implementation was introduced or retained by conflict resolution.

## Verification

The aggregate completed with **exit 2**: its 973 existing storage cases passed,
but the two added migration tests incorrectly entered a pre-Phase-15 fixture
helper even though the current SQL lock guard already exists. The helper correctly
refused that override. The tests now seed through the real current lock path;
**both corrected migration cases pass** (4.55 s). No production code, assertion,
lock or gate was weakened. The original aggregate failure is retained; no
successful aggregate exit is claimed. The remaining PostgreSQL/Redis/Go API integration check passes (exit 0).
Successful checks are retained rather than rerunning unaffected suites after this
test-fixture-only correction.

Completed:

- Focused offline retained-identity, live-resource/order, experimental-isolation and API-Football resource tests: **62 passed**.
- Python unit tests: **2,157 passed**, seven existing dependency warnings.
- Strict mypy: **498 source files** and the two code-intelligence files pass. Python lint/format, Rust lint/format and architecture checks pass.
- Rust: **16 passed**. Web component/contract tests: **181 passed**.
- Desktop/mobile Playwright: **42 passed, 26 skipped**, exit 0. Skips are the existing backend/real-provider harness cases and device-specific assertions; real-provider and operating-backend flags were unset. No new skip was added.

The read-only exported snapshot contains **9,370,649 rows across 49 protected
tables**, plus **314,876 eligible historical results**. Its fresh custom-format
backup is **1,847,231,178 bytes**, SHA256
`375c5d9daee0ec97b1e124441950850ac8d2c68931cae89eaab57995ff4fcacd`.
The accompanying JSON records per-table counts and SHA256 digests. The backup
restored with identical Goose history. Ordinary upgrade applied only
`202611100200` in 132.16 ms; retry applied nothing. All **49 table hashes and
9,370,649 rows** remained exact after upgrade, and the same-cutoff **314,876
eligible results** reproduced the exact SHA256. All prior migration records and
13 `LEGACY` routes remain unchanged. The private harness's last routing query
initially used `execution_mode`; the actual column is `route`. Every table hash
had already passed. The corrected final routing, migration-history and eligibility
checks pass; the original failed log is retained.

A later read-only operating comparison retains **all 1,114,469 baseline rows in
15 immutable registration/history tables**, including all **18,162 forecasts**,
**5,230 model registrations**, **22,900 admissions** and **862,214 historical
decisions**. Eight source snapshots and eight resources were added by unrelated
background work; no baseline row hash changed or disappeared. Operating migration
history remains identical and all 13 routes remain `LEGACY`.

Physical reads verify **12,310 observation files**, **26 capability files**,
**5,204 model manifests**, **5,204 model files** and **80,612 source-manifest
paths**. The champion file checksum remains
`e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4`.
Direct registry/path checks also observe **26 absent model manifests, 26 absent
model files, 34 absent source paths and 48 source-path hash disagreements**.
Sixty of these paths are already listed in the FR-011 retained-originals report.
These are operating retention findings, not changes made by this read-only
integration. A direct path/hash disagreement does not by itself classify the
provider-specific legacy manifest convention. No raw bytes were replaced and no
registration was changed to hide a gap. Existing data-quality and parity blockers
remain separately recorded; this task does not resolve them.

Initial test and private verification harness calls exposed incorrect test paths
(zero tests collected) and a relative data-root setting resolved against the new
worktree. Both were corrected and the original logs retained. The passing focused
and physical-file results above use the correct paths and original operating
storage root. Private backups, DSNs, raw files and
logs remain untracked under `.local/v4-integration`.

## Separately approved operating rollout

After review and merge authorization, take a fresh consistent operating backup,
verify its authenticated isolated restore, stop only the affected writers under
the established operator procedure, apply active Goose migrations normally, and
deploy the compatible writer. Inspect migration status and existing forecasts,
model/source hashes, identity claims and stage routing before resuming writers.
Do not apply the archived migration to the operating database. This task performs
none of those operating changes. Code rollback must retain the new mapping
metadata and existing data. Disable the affected writer rather than restoring
the version that mislabeled generated identities as deterministic. Schema recovery
uses reviewed forward repair, or an
explicitly authorized restoration from the verified backup. V2/V4 cutover,
training, promotion, provider activation and final PR merge remain owner-gated.

## Delivery assessment

The final code and contract matrix passes across the retained aggregate results,
two corrected migration cases and remaining API integration. That covers 975
storage cases in total. The complete aggregate's actual exit remains 2; its
fixture-only failures and corrected evidence are disclosed above. No unresolved
integration failure remains. Existing retention/qualification/scientific blockers
are preserved, and no later programme phase is authorized by this handoff.

The final main refresh still resolves to the baseline merge SHA. The integration
commit keeps both parents; every main migration and the original legacy V4
migration is byte-exact. The staged diff contains only this integration, with no
local task files, environment values, raw data, private receipts or generated
build/test files. The frontend/browser, architecture, complexity, duplication,
consumer and scope review found no integration-introduced competing owner or
unsupported production activation.
