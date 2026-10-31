# MatchForge codebase remediation

Status: PASS_WITH_WARNINGS — authorized implementation verified; external identity/evidence limits and operating rollout remain open. Completed verification 31 October 2026 (Africa/Lagos).

Disposition: **24 FIXED_VERIFIED, 1 ALREADY_RESOLVED_VERIFIED, 1 BLOCKED_WITH_EVIDENCE**. All 26 findings, four KB items and eight risks are recorded separately below. This is a code-delivery result, not certification that the operating instance has been upgraded.

Source: `docs/CODEBASE_AUDIT_REPORT.md`, audited/startup commit `1cbc69a20a6f15a7e4f00e242a35c6d2569c3617`. Branch: `ft/codebase-remediation-2026-10-30`. Isolated checkout: `/private/tmp/matchforge-remediation-20261030`. The owner's audit is preserved unchanged. The original checkout's source and operating service were not edited/restarted by this task; its task-branch pointer was set during startup. Background owner processes continued independently.

## Scope and execution

The owner authorized phases A–E of this remediation. No active Wayfinder map was available; no terminal route was reclaimed. L3 classification applies to identity, historical eligibility, immutable revisions and concurrent publication. No external football-provider requests, operating data mutations, forced mappings, protected scientific runs, champion changes or Architecture V2 cutover were performed.

Dependency order and commits:

1. A — normal report production, invalidation, fairness and failure isolation: `ccd424f`.
2. B — append-only external recovery, exact dates, current eligible metrics and bounded reads: `a87e1d3`.
3. C — scoped sync health, daily retry cooldown and independent wrapper stages: `d93db6b`.
4. D/E integration — reviewed bindings, conflicting-resource protection, pre-match serving, frontend behavior, runtime identity and real-backend browser acceptance: `c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e`.
5. E security — patched dependency/toolchain locks and matching CI/bootstrap pins: `596714bb8bde58b4d386ef87edfb02de764f78e3`.

The pre-existing related context-polling follow-up `1cbc69a` remains intact above the original main base. No commit was amended or rewritten. Full validation ran in the isolated checkout with disposable databases and provider schedules disabled.

## Finding ledger

Every verification below is also covered by the final quality-graph results. Files named without directories are the existing product modules in `python/football/src/football/product/`, `go/api/internal/app/` or `web/components/`; migrations are under `infrastructure/migrations/`. The commits above identify exact changed paths.

### MF26-01 — Performance report production is disconnected from normal operation

- Original severity: High.
- Status: FIXED_VERIFIED.
- Root cause: Current source fingerprints were required by serving without scheduled Performance production.
- Changes/files/commits: Transactional invalidation for all seven horizons; bounded scheduled report production; per-league pending/failed states retain available leagues. Files: public_reports.py, cli.py, 202610300100_public_report_scheduling.sql, Go report/scheduler stores, web contracts/components and owning architecture/OpenAPI. Commit: ccd424f; final integration follow-ups: c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e.
- Verification: 21 disposable PostgreSQL report cases passed, including the actual Go scheduler launching the Python worker, corrections and report retrieval; Performance mixed-state component regression passed.
- Before/after: Missing reports previously failed the entire page; available leagues now remain visible while missing scopes are pending.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-02 — Context backlog prevents timely Recent Form, H2H, and team statistics

- Original severity: High.
- Status: FIXED_VERIFIED.
- Root cause: Bootstrap FIFO ordering and the bulk lane starved relevant context.
- Changes/files/commits: Separate public-report lane; bounded capacity per kind; half context capacity reserved for old work and half for fixtures in the preceding 24 hours through the next 72 hours; retries rotate by attempt time. Files: public_reports.py, cli.py, 202610300100_public_report_scheduling.sql, Go report/scheduler stores, web contracts/components and owning architecture/OpenAPI. Commit: ccd424f; final integration follow-ups: c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e.
- Verification: Disposable backlog test proves current fixture and historical work both progress in a bounded batch. Generation completion and PIT tests pass; the final real-backend browser consumes scheduled context while provider acquisition is disabled.
- Before/after: Current fixtures behind bootstrap history now receive reserved capacity; no production drain/latency measurement is claimed.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-03 — External MatchForge agreement silently loses its report producer

- Original severity: High.
- Status: FIXED_VERIFIED.
- Root cause: Comparison serving had no scheduled producer and collapsed missing reports into unsupported agreement.
- Changes/files/commits: Selection/forecast changes enqueue comparison reports. Explicit comparison_status distinguishes READY/PENDING/FAILED/UNSUPPORTED/NO_FORECAST/UNMATCHED. Files: public_reports.py, cli.py, 202610300100_public_report_scheduling.sql, Go report/scheduler stores, web contracts/components and owning architecture/OpenAPI. Commit: ccd424f; final integration follow-ups: c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e.
- Verification: Actual Go scheduler launches worker and verifies comparison probability through the Go store; immutable retry and stale-source tests pass.
- Before/after: Supported matched selections now obtain comparisons through the normal scheduler.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-04 — Missing score provenance is encoded as fresh

- Original severity: Medium.
- Status: FIXED_VERIFIED.
- Root cause: The legacy boolean encoded absent freshness deadlines as false.
- Changes/files/commits: Additive freshness enum preserves UNKNOWN/FRESH/STALE through SQL, Go and frontend parsing; unknown is never labelled fresh. Files: public_reports.py, cli.py, 202610300100_public_report_scheduling.sql, Go report/scheduler stores, web contracts/components and owning architecture/OpenAPI. Commit: ccd424f; final integration follow-ups: c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e.
- Verification: Three-state Go live-source regression and UI missing-source/lifecycle regression pass; desktop/mobile browser checks passed.
- Before/after: Unknown sources now display freshness unknown; legacy boolean remains for wire compatibility.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-05 — Score/status and incident feeds can present contradictory match state

- Original severity: Medium.
- Status: BLOCKED_WITH_EVIDENCE.
- Revalidated cause: read-only operating evidence retains SCHEDULED fixture `dffecb0c-fdff-5811-a276-5ddebc9a71c2`, a normalized resource attached there, and native FotMob `5989865` mapped to `264ccd72-e939-520b-b7b1-0f049ecea19d`. Later FINISHED observations remain unbound; contradictory mapping and absent-season decisions prevent automatic adjudication.
- Changes/files/commits: c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e, plus ccd424f. `operational_provider_sync.py` rejects a conflicting snapshotless detail candidate. Migration `202610310200_uncontested_live_resources.sql` excludes retained resources that contradict a verified native mapping. `postgres_store.go`, `product.go`, OpenAPI and `expanded-fixture.tsx` expose withheld identity data, partial state, unknown score freshness and unresolved lifecycle. Original bytes/mappings remain unchanged.
- Verification: disposable conflicting-candidate and actual Go LiveFixture tests passed; UI partial/lifecycle tests passed in the final suites.
- Before/after: unrelated timed incidents could appear as ordinary scheduled-match data; conflicting resources are now withheld with an explicit explanation. This mitigates the code defect without declaring a result or selecting the disputed identity.
- Remaining blocker / next action: obtain independently admissible native season/fixture evidence in a newly authorized identity-review route. Do not force a mapping, infer a score from incidents or reuse a terminal route. No operating mapping was changed.

### MF26-06 — Source accuracy reads obsolete first settlements

- Original severity: High.
- Status: FIXED_VERIFIED.
- Root cause: Source summaries joined obsolete first-result rows.
- Changes/files/commits: Current settlement-revision views, pending-generation exclusion and one filtered source aggregate query. Files: external_prediction_store.go, external_prediction_recovery.py, recovery migration; commit a87e1d3.
- Verification: Correction sequence WON→LOST→PENDING→VOID→WON and actual Go reader metrics passed.
- Before/after: Corrections now replace the current metric contribution without changing old rows.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-07 — External parsers accept the wrong prediction day

- Original severity: High.
- Status: FIXED_VERIFIED.
- Root cause: Source day matching used partial/sub-string date text.
- Changes/files/commits: Locale-independent complete day/month/year parsing, source-date mismatch rejection and append-only retained-date reviews. Files: external_prediction_sources.py, recovery migration; commit a87e1d3.
- Verification: Wrong day, malformed dates, December/January and February boundaries passed in 43 source/CLI cases.
- Before/after: Contradictory dates are rejected or quarantined, with original text preserved.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-08 — Identical reimports cannot recover an unmatched fixture binding

- Original severity: Medium.
- Status: FIXED_VERIFIED.
- Root cause: Immutable source revisions had no independent binding correction record.
- Changes/files/commits: Append-only binding chains backed only by existing verified exact native mappings; an explicit evidence/reason-backed review CLI supports captures without native IDs. Mapping revocation appends unmatched state; post-kickoff review receives no prospective credit. Original capture and source rows remain immutable. Final follow-up: c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e. Files: external_prediction_recovery.py, external_predictions.py, recovery migration; commit a87e1d3.
- Verification: Import before mapping, verified later binding, identical retry and refusal to match native-ID failure by names passed.
- Before/after: A later verified mapping repairs the effective binding through new evidence.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-09 — Collection failures can be reported as successful synchronization

- Original severity: Medium.
- Status: FIXED_VERIFIED.
- Root cause: Collection aggregate status ignored per-source errors and disabled/out-of-window outcomes.
- Changes/files/commits: Truthful attempted/successful/partial/failed/skipped statuses and immutable collection attempts, separate from static qualification. Files: cli.py, external_prediction_sources.py, admin_sync.go; commit a87e1d3.
- Verification: Aggregate status unit matrix, retained attempts and per-source persistence failures passed.
- Before/after: Successful sources remain committed; partial/failing collection exits nonzero and retains its exact source status.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-10 — Settlement repeatedly scans all mapped selections

- Original severity: Medium.
- Status: FIXED_VERIFIED.
- Root cause: Every settlement call scanned all mapped selections.
- Changes/files/commits: Generation checkpoint queue, 128-selection cap, short per-item transactions, consistent lock order and skip-locked ownership. Files: external_prediction_recovery.py, recovery migration; commit a87e1d3.
- Verification: Bounded concurrent workers, transaction rollback, unchanged retry and repeated correction cases passed.
- Before/after: Imports, binding changes and result changes enqueue only affected work.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-11 — Source accuracy includes selections first captured after kickoff

- Original severity: Medium.
- Status: FIXED_VERIFIED.
- Root cause: Settlement denominators did not distinguish retrospective captures.
- Changes/files/commits: Current verified bindings, exact source dates, first capture and current revision-start strictly before kickoff; future observations and same-time conflicting picks excluded. Files: external_prediction_store.go and capture views; commit a87e1d3.
- Verification: Real Go source counts exclude kickoff-time capture; A→B→A capture history and same-time conflict cases passed.
- Before/after: Late captures remain visible under a separate denominator and receive no prospective credit.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-12 — Collection does not itself settle newly imported completed fixtures

- Original severity: Medium.
- Status: FIXED_VERIFIED.
- Root cause: Only provider synchronization called settlement.
- Changes/files/commits: Selection/result invalidation and bounded settlement at the start of normal public-report work. Files: public_reports.py, recovery migration; commit a87e1d3.
- Verification: Late import against an already stored verified final result settles without a provider fetch.
- Before/after: Normal local scheduling processes imports even while provider schedules are disabled.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-13 — Repeated unresolved recovery contaminates routine sync health

- Original severity: Medium.
- Status: FIXED_VERIFIED.
- Root cause: Missing historical targets incremented the current acquisition failure counter and retried on the short freshness cooldown.
- Changes/files/commits: Separate current_acquisition and historical_recovery summaries; truthful aggregate error; one-day missing-native-ID cooldown. Files: operational_provider_sync.py and architecture.md; commit d93db6b.
- Verification: Successful current acquisition plus absent historical target, immediate cooldown skip and later native recovery passed.
- Before/after: Useful acquisition stays visible while unresolved evidence and actual aggregate failures remain explicit.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-14 — Worker ownership failures and expired history claims need recovery verification

- Original severity: Medium.
- Status: ALREADY_RESOLVED_VERIFIED.
- Root cause: Ownership-fence incidents are retained; initiating heartbeat/process cause is not in available logs.
- Changes/files/commits: No lease or publication rule relaxed. Real killed/restarted worker exercise supplements existing shared-work and fencing cases. Files: test_operational_recovery.py; commit d93db6b.
- Verification: Committed checkpoint survived process kill, new generation reclaimed, old heartbeat rejected and replacement published once.
- Before/after: Recovery works under the existing contract; original host incident cause remains unknown, with no confirmed code defect to repair.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-15 — Daily refresh skips independent external collection after sync failure

- Original severity: Medium.
- Status: FIXED_VERIFIED.
- Root cause: Shell fail-fast sequencing prevented the independent collection stage after sync failure.
- Changes/files/commits: Capture both stage exits, attempt both once and return aggregate failure. Files: mvp-refresh.sh, test_mvp_refresh.py; commit d93db6b.
- Verification: Four independent-stage wrapper cases passed, including both failure directions and both stages failing.
- Before/after: Collection runs after sync failure, and the wrapper reports both exit codes.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-16 — External read endpoints do unbounded per-source comparison work

- Original severity: Medium.
- Status: FIXED_VERIFIED.
- Root cause: Archive retrieval was unbounded and source agreement repeated full retrieval per source.
- Changes/files/commits: Bounded 20/50/100-row pages, repeatable-read filtered counts/consensus, one source aggregate query and cancellation. Files: external_prediction_store.go, product.go, web contracts/components; commit a87e1d3.
- Verification: Actual 20/8-row API pages, stable identity coverage, query count and cancellation passed. A 5,001-current-selection benchmark passed in final integration.
- Before/after: Page size no longer grows with retained archive size; denominators remain independent of the visible page.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-17 — External “consensus” counts records as independent sources

- Original severity: Medium.
- Status: FIXED_VERIFIED.
- Root cause: Client grouped raw rows by names/fixture without independent-source or market rules.
- Changes/files/commits: Server consensus uses verified effective fixture/market, distinct enabled public sources, current prospective selections and a strict majority of at least two. Files: external_prediction_store.go, predictions-page.tsx and contracts.ts; commit a87e1d3.
- Verification: Real two-source consensus, same-time conflict exclusion, independent page consensus and single-source/minority rejection passed.
- Before/after: Duplicate revisions, different markets and unmatched names cannot manufacture source agreement.
- Remaining blocker: none for this implementation; live adoption is separate.

### MF26-18 — Predictions has no mobile navigation

- Original severity: Medium.
- Status: FIXED_VERIFIED.
- Root cause: Predictions bypassed the shell containing mobile navigation while its own header hid primary navigation.
- Changes/files/commits: Shared mobile navigation is rendered by both shell paths, including the 761–767px gap. Files: app-shell.tsx, globals.css.
- Verification: Browser checks at 320, 765 and 1024 pixels passed in final acceptance.
- Before/after: All four routes remain keyboard reachable at narrow widths.
- Remaining blocker: none for this implementation; live adoption is separate.
- Commit: c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e.

### MF26-19 — Score matrix has incorrect alignment, table semantics, and contrast

- Original severity: Medium.
- Status: FIXED_VERIFIED.
- Root cause: Nested grid columns misaligned scores and an incomplete ARIA table omitted row/cell semantics.
- Changes/files/commits: Native table with caption, scoped row/column headers, fixed readable cells, internal scrolling and forced-color borders. Files: expanded-fixture.tsx, globals.css.
- Verification: Matrix tab component cases passed; 320px native relationships, keyboard scrolling, axe and forced-color browser checks passed in final acceptance.
- Before/after: Home-goal rows and away-goal columns align; relationships no longer depend on visual placement.
- Remaining blocker: none for this implementation; live adoption is separate.
- Commit: c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e.

### MF26-20 — External time labels disagree with the formatter

- Original severity: Low.
- Status: FIXED_VERIFIED.
- Root cause: Capture/kickoff used the configured display timezone while labels claimed UTC/London.
- Changes/files/commits: Label first capture and kickoff with DISPLAY_TIME_ZONE; keep the source prediction partition separate. File: predictions-page.tsx.
- Verification: 08:15 UTC renders 09:15 Africa/Lagos and both column labels identify that zone; component regression passed.
- Before/after: Source day, original capture and kickoff are distinct concepts.
- Remaining blocker: none for this implementation; live adoption is separate.
- Commit: c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e.

### MF26-21 — Healthy feed indicators are not connected to health

- Original severity: Medium.
- Status: FIXED_VERIFIED.
- Root cause: Feed Live and Cluster Synced were static assertions.
- Changes/files/commits: Selections show actual loading/refreshing/unavailable/loaded request state; the shared shell describes stored forecasts. Files: predictions-page.tsx, app-shell.tsx.
- Verification: Component regression confirms scoped loaded state and absence of hardcoded healthy claims.
- Before/after: No request result claims cluster-wide operational health.
- Remaining blocker: none for this implementation; live adoption is separate.
- Commit: c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e.

### MF26-22 — Production Predictions exposes simulated empty/loading controls

- Original severity: Low.
- Status: FIXED_VERIFIED.
- Root cause: Simulated empty/loading buttons changed the production data view.
- Changes/files/commits: Remove ViewMode, StateBar and StateButton; render only actual resource states. File: predictions-page.tsx.
- Verification: Component regression confirms production controls are absent and normal error/empty/populated cases pass.
- Before/after: Users cannot replace actual data with simulated states.
- Remaining blocker: none for this implementation; live adoption is separate.
- Commit: c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e.

### MF26-23 — Successfully loaded context does not refresh while the fixture stays open

- Original severity: Medium.
- Status: FIXED_VERIFIED.
- Root cause: Context retried temporary misses but never refreshed after success.
- Changes/files/commits: Visibility-aware completed-request context refresh at 60/120 seconds, preserving immutable forecast ID; repeated 503 misses after success advance retry/backoff on each completed request. File: expanded-fixture.tsx.
- Verification: Open-panel context changed without reopening or another forecast request; unmount stops refresh. Repeated misses after a successful load continue retrying with backoff. Regressions passed.
- Before/after: Already loaded form/context can update while the panel stays open.
- Remaining blocker: none for this implementation; live adoption is separate.
- Commit: c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e.

### MF26-24 — Admin stops observing schedules when no job is active

- Original severity: Medium.
- Status: FIXED_VERIFIED.
- Root cause: Admin polling required an already active run.
- Changes/files/commits: Idle discovery at 60 seconds, active 2.5 seconds, hidden 120 seconds and visibility refresh; sequential and abort-safe. File: use-sync-admin.ts.
- Verification: Idle→scheduled job, visibility refresh, no overlapping poll and terminal-response race regressions passed.
- Before/after: A page opened idle discovers background work without manual reload.
- Remaining blocker: none for this implementation; live adoption is separate.
- Commit: c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e.

### MF26-25 — Competition rail can create contradictory filters

- Original severity: Low.
- Status: FIXED_VERIFIED.
- Root cause: Rail selection changed competition without clearing incompatible geography.
- Changes/files/commits: Clear country/continent when selecting another rail competition, retaining other independent filters. File: fixture-explorer.tsx.
- Verification: England→Serie A regression checks query has the selected competition and no country restriction.
- Before/after: The requested competition cannot be silently excluded by stale geography.
- Remaining blocker: none for this implementation; live adoption is separate.
- Commit: c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e.

### MF26-26 — Agent guidance references missing supporting documents

- Original severity: Low.
- Status: FIXED_VERIFIED.
- Root cause: supporting documents moved to docs/ while guidance retained docs/engineering/ paths; the PR template path was also stale.
- Changes/files/commits: repaired AGENTS.md and docs/git-delivery.md to reference the existing documents; no duplicate guidance created. Commit: ccd424f; final integration follow-ups: c9d8fe7ea70076f08efb25e672abdf6ba1f0c06e.
- Verification: Python path validator checked all ten distinct document references in AGENTS.md; all exist. git diff --check passed.
- Before/after: required guidance reads failed; every referenced supporting document now resolves.
- Remaining blocker: none for this finding. Historical project PASS records are explicitly not current runtime certification.

## Known blockers and risks

| ID | Final disposition | Evidence and required next action |
| --- | --- | --- |
| KB-01 | BLOCKED_WITH_EVIDENCE — identity/history admission | Retained R3 holds and current read-only missing-season/contradictory-mapping decisions remain. Historical counts (605 team IDs, 108 origins, 210 competition IDs) are checkpoint counts, not refreshed totals. Resolve only through a newly authorized evidence-based route; no name-only merge or historical decision rewrite. |
| KB-02 | BLOCKED_WITH_EVIDENCE — provider entitlement/access | API-Football season entitlement, football-data.org CL2020, incomplete PitchAPI proof and Forebet restrictions were not bypassed or retested with live traffic. Code distinguishes disabled, outside-window and failed collection. Owner must authorize exact entitlement/evidence checks under provider budgets. |
| KB-03 | INTENTIONAL_INCOMPLETE_PHASE — preserved | Architecture V2 phases 34–48/cutover remain unauthorized. Current public report workflows were repaired within existing ownership; shadow infrastructure was not presented as a completed runtime migration. A separate owner decision is required for later phases. |
| KB-04 | GOVERNANCE_STOP_PRESERVED | Sprint 2 FAIL, closed challengers, protected targets and reevaluation integrity stops remain unchanged. Champion retained; no promotion or protected outcome access. Future scientific execution requires its own admissible-input/owner decision. |
| R-01 | BLOCKED_WITH_EVIDENCE — original transport cause | Retained DNS/transport incidents coexist with successful later acquisitions; the initiating network/process traces are absent. No new provider request was made to manufacture a reproduction. Obtain timestamped host/network/heartbeat logs before attributing a new provider defect. |
| R-02 | FIXED_VERIFIED — poisoned batch isolation | Snapshot/report failures are recorded per scope; unrelated reports continue and retry ordering rotates. Disposable failure injection and bounded fairness cases passed through the normal worker implementation. |
| R-03 | ALREADY_RESOLVED_VERIFIED for recovery; cause still unknown | Real child-process interruption preserved its committed checkpoint. A replacement reclaimed a new generation, rejected the expired heartbeat and published once. Six operating expired leases were observed read-only; this task did not reclaim them. Original incident cause still needs host traces; no fencing rule was relaxed. |
| R-04 | PARTIALLY_VERIFIED; deployment evidence blocked | Metrics age/state and administrative tests pass. Repository systemd timer specifies 06:00 Africa/Lagos; no MatchForge launch-agent entry was found on this host. Installed daily scheduling, alert consumers/recipients, retention ownership and disk-pressure response are not established. Owner/operator must confirm deployment and an alert delivery/retention drill. |
| R-05 | PARTIALLY_VERIFIED — current isolated restore passed | Current database backup/restore and copied-file checksums passed (details below). These timings do not establish an approved RPO/RTO or prove every registered resource exists. Previously missing/unverifiable bytes remain evidence gaps. Owner must approve recovery targets and disposition unavailable resources. |
| R-06 | PARTIALLY_VERIFIED — invariants passed; research stops retained | Final suites exercise cutoff isolation, same-kickoff ordering, artifact tamper/round-trip checks, deterministic simulation, immutable publication and historical storage. Champion checksum is unchanged. This does not reproduce every fitted artifact/calibration/backtest or authorize frozen scientific evaluation. Remaining reproductions require approved inputs and a separate owner decision. |
| R-07 | PARTIALLY_VERIFIED — security/build/bounded capacity | Four advisory scans report no security vulnerabilities after patches; Rust has one informational unmaintained dependency. Actual API build identity and 5,001-selection bounded reads passed. Loopback/auth/deadline/cancellation tests passed. Remote deployment, sustained SLO/load, independent penetration testing and provider flood behavior are not certified. |
| R-08 | PARTIALLY_VERIFIED — automated/manual code review scope | Desktop Chromium and mobile WebKit, 320/765/1024px navigation, matrix native semantics/keyboard scrolling, representative states, normal-color axe, forced-color border/focus and reduced motion passed. Forced-color screenshots were inspected. VoiceOver with Safari, native browser zoom and complete text-spacing/assistive-technology journeys remain unverified; no full WCAG 2.2 AA claim. |

## Final verification

The final `make check integration web-e2e` run passed backend formatting/lint/strict typing/complexity, migration validation, 1,708 Python unit cases, 16 Rust cases, Go tests and all backend builds. It then stopped at two unsupported Testing Library `exact` options in new tests. Removing those options changed test queries only. The continuation reused the successful backend build and ran:

```sh
MATCHFORGE_REAL_PROVIDER_E2E=false make -o build web-lint web-test web-build integration web-e2e
```

This continuation passed (exit 0). Successful backend tests were not rerun without a relevant code change. Combined, the two commands cover the complete Make dependency graph; the first failed invocation is not recorded as a successful aggregate.

| Gate | Actual result |
| --- | --- |
| Ruff format/lint, strict mypy | PASS; 501 formatted files, 432 typed source files |
| Clippy, Go vet/golangci-lint/complexity, shell syntax, Goose validate | PASS; no checks weakened |
| Python unit suite | 1,708 passed; seven existing upstream penaltyblog/NumPy deprecation warnings |
| Rust workspace | 16 passed; repeat/parallel deterministic cases included |
| Go unit suite | PASS; database cases additionally run inside disposable integration |
| Frontend ESLint/typecheck | PASS; one pre-existing unused `_input` test-argument warning |
| Frontend Vitest | 96 passed across 12 files |
| Python wheel/sdist, Rust/Go, Next production build | PASS |
| ProjectStatusV2 validator | PASS |
| Storage/migration/API/real-backend browser integration | 738 passed; fresh/repeated migrations and API integration PASS |
| Deterministic browser suite | 32 passed (41.9s); 12 skipped (live-provider, harness-only or device-specific cases; real-backend desktop case passed separately inside integration) |
| Diff whitespace and staged secret/local-file review | PASS; `.env`, backups, provider bytes, local tools/logs and node_modules excluded |

The normal Go application scheduler launched the actual Python command runner, recorded a successful PUBLIC_REPORTS root run and produced CONTEXT, COMPARISON and all seven PERFORMANCE horizons. The real browser consumed Performance, Recent Form, H2H, Team Statistics, Markets, Score Matrix, Diagnostics and Predictions through the real API/SQL implementation. Its routing forwards requests to the disposable API without synthesizing response data. Representative provider acquisition/result fixtures elsewhere in the same integration graph cover postponed/finished/corrected/unmatched/partial states, retries, concurrency and process interruption. No live provider acquisition was performed.

Real scheduler evidence: fixture `6358574b-5c44-4cc0-9aa7-2bfdfdaaaca7`; CONTEXT record SHA-256 `1d5fc722ee53fa0b526d8ebdd42d693f7cfd5fad688c3d5068c4bd9cb591bd14`. Full nine-report identities/source fingerprints are in ignored `.local/remediation-browser-evidence.json`.

Additional regressions found during remediation and fixed before handoff:

- Queuing a new external validation generation immediately hides the old comparison and eligible aggregate contribution until that generation completes.
- A corrected kickoff excludes post-kickoff or future-cutoff immutable forecasts from both active summaries and comparisons, with SOURCE_DATA_INCOMPLETE when none qualifies. Retrieval by historical ID remains unchanged.
- Reviewed bindings without native IDs require retained verified mapping evidence, exact source revision hash and reason. Revocation appends unmatched state; late review gets no prospective credit.
- Repeated identical context misses after a successful load keep retrying with backoff. Successful context refresh never silently swaps the immutable forecast.
- Mobile WebKit keyboard scrolling is explicitly supported by the shared named TableScroll region. Nested controls keep their own arrow keys.
- Test fixtures preserve old-schema upgrade compatibility, valid public UUIDs, coherent matrix payloads and database capture clocks. No production validator or assertion was relaxed.

### Security and runtime identity

Security scans used the final lock files: `pnpm audit --json` (zero vulnerabilities), pip-audit over 91 locked runtime packages (zero), `govulncheck -json ./...` (zero finding objects), and `cargo audit --json` (zero security vulnerabilities). JSON contents were checked; Go JSON exit status alone previously concealed findings and is not the acceptance criterion.

Patched versions: Next/ESLint config 16.4.1, Vitest 4.1.12, Vite override 7.3.7, certifi 2026.10.23, Pillow 13.0.0, Go 1.27.3 and x/text 0.41.0. No modelling-library replacement or numerical configuration change. Existing artifact dependency hashes remain immutable. The exact CI-pinned pnpm 10.19.0 accepted the final frozen lock offline without changing its checksum. The package manager's lifecycle-script restrictions were preserved; no build-script allowlist was relaxed.

Published patch evidence: [Next.js advisory](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw), [Vitest advisory](https://github.com/vitest-dev/vitest/security/advisories/GHSA-qxg6-89mg-rqv8), [Pillow release](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html), [certifi release](https://github.com/certifi/python-certifi/releases/tag/2026.10.18). RustSec RUSTSEC-2024-0436 identifies transitive nalgebra dependency paste 1.0.15 as unmaintained, without a security vulnerability. It is retained explicitly rather than suppressed or replaced through an unauthorized numerical change.

`make build` links the exact Git commit, uv.lock SHA-256 and source clean/dirty state. `/version` returns these values independently of the moving runtime checkout; unidentified direct builds say unknown. Actual binary HTTP verification is included in API integration. Final clean-commit build identity is checked after the evidence commit and reported in the PR/handoff.

### Restore and artifact evidence

A read-only repeatable-read operating snapshot was dumped and restored only to a unique disposable database. Migration version plus full-row digests/counts matched for fixtures, forecasts, external captures, first results, result revisions and native mappings. The restored database was removed.

- Backup: 1,044,602,477 bytes; SHA-256 `30ab91539be33d64425bb15753dea4d35f5192260a9387ed830cfa9f79a3301c`; capture 119.53 seconds; isolated restore 397.12 seconds.
- Retained raw-file copy: 76,189 files, 8,179,985,091 bytes; every copied file matched its source. Path/hash manifest SHA-256 `0d26da931cc0d7d2b86a1c4ad2a5f19258e71c3888920f6becda7a50ac3fe6f5`.
- Champion copied and verified unchanged: `e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4`.

These are observed exercise results, not approved recovery objectives or proof that missing registered resources exist. Opaque dumps/raw copies remain ignored, access-restricted local evidence; they are not published in Git. Background operating workers continued independently; this task made no operating-record writes.

### Static analysis and frontend review

Fallow 3.38.0 complete root analysis and staged security/preview ran before each code commit. Root envelopes are valid. Final measured-coverage analysis reports zero health findings, zero clone groups and zero unresolved imports. The one pre-existing unused-file report, `web/playwright.real.config.ts`, is a verified explicit CLI configuration (`--config playwright.real.config.ts --list` succeeds); it was retained without suppression or configuration changes. Root node_modules/boundary/policy diagnostics are limitations: dependencies live in web/, and no architecture rule pack is configured. Zero policy findings therefore does not imply measured architecture conformance.

Coverage command: `pnpm exec vitest run --coverage --coverage.reporter=json --coverage.reporter=json-summary --coverage.reportsDirectory=../.local/remediation/codebase-2026-10-30/coverage`. All 96 cases passed. Instrumented frontend files: 92.75% lines, 78.16% branches. Supplying measured coverage resolves six moderate estimated-health recommendations at complexity 10; no threshold, baseline or rule was weakened. Python/Go complexity gates pass. An existing response-fixture decision chain was replaced with a response table to reduce cognitive complexity while preserving routes.

Application staged security: zero candidates and zero unresolved edge files; 83 changed-line dynamic-dispatch diagnostics consist of test/request/assertion APIs and the inspected DOM preventDefault call in TableScroll. Earlier Phase B fixed-origin SSRF candidate was ruled out with a hostile-filter test: URLSearchParams under a literal path/configured browser API origin cannot change origin/path. Auto-fix previews proposed zero edits; none applied. No secret/local/generated artifacts are staged.

Shared UI review inventoried the existing shell navigation and two native table-scroll consumers. MobileNavigation reuses the existing route/current-page contract; TableScroll preserves labels, semantic tables and CSS tokens. No Figma, shared variant, token or package API changes. Read-only frontend review covered touched routes, accessibility, request cancellation/stale responses, error/empty/partial states, API parsing, immutability and unrelated diff contamination. No unresolved actionable implementation finding remains; assistive-technology/deployment risks above remain explicit. This was the implementing agent's review, not a claim of independent human review.

## Evidence files and delivery

Verbose evidence remains under ignored `.local/remediation/codebase-2026-10-30/`; committed tests and this ledger provide reproducible scope. Relevant local records: `final-gates.log`, `final-continuation.log`, `final-suite.xml`, `application-fallow.json`, `application-security.json`, `security-fallow.json`, `security-security.json`, the four advisory scan JSON files, coverage JSON, read-only operating JSON and `current-restore/report.json`/`raw-copy-report.json`.

Local evidence SHA-256:

- `final-gates.log`: `40f6a5fd53c0c4662fcfdbd556cf9412123ba3ee512a1cbff7690b09753a0215`
- `final-continuation.log`: `3c5255bdc3f5af678504e1b2240409a4a691780a610dfcc16ba17f71184aeff2`
- `final-suite.xml`: `fbe14dddea800ec1e0b028a10c34dbe9a7257c12f55ae5899bfb14351c9e2f2a`
- `npm-audit-final.json`: `902485ba571e1c2dcbb444dc04dc0acdafb1a81c0b5a18c0c584e9090ab59df7`
- `python-audit-final.json`: `a12e70c50a6ff2b9ce1426abde441c5915159c4d4501752fc6739e4db39003c3`
- `go-vuln-final.json`: `483c76491dd351282acf67aebc0883e626f7f84f2f21a72e217f25085dba4474`
- `rust-audit.json`: `c010164417756a4e25192470149f4114aa08c2d5a04d0ebb8cbddeda8212073f`

The branch must be reviewed through its PR before applying the four roll-forward migrations and installing/restarting the reviewed build through normal operations. Existing migration history, immutable source rows and scientific stops remain intact. The operating instance was not upgraded by this task and is not certified ready from this isolated proof alone. Authorized application workflows pass in isolation; MF26-05/KB-01–04 and the unverified operational/assistive-technology limits remain the precise handoff conditions. No later phase or feature work begins here.
