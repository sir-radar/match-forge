# MatchForge functional, technical, and reliability audit

Audit date: **30 October 2026**, Africa/Lagos. Runtime observations were made during approximately 23:19–23:32 WAT (22:19–22:32 UTC). Counts below are timed observations of an active system, not a frozen database snapshot.

Audited source: `1cbc69a20a6f15a7e4f00e242a35c6d2569c3617` (`fix(web): keep polling pending context reports`). Audit branch: `ft/codebase-audit-2026-10-30`, created from the existing `ft/fix-context-refresh-polling` branch. The starting worktree was clean. This report is the only intended file change. No fixes, migrations, provider requests, job controls, model runs, or operational data changes were performed by the audit.

## 1. Executive summary

**Overall health: degraded. Do not use the current UI or source-accuracy summaries as evidence that end-to-end operation is reliable.** Fixture listing and stored forecast retrieval work in the sampled local runtime, but several downstream workflows are disconnected or misleading.

The highest-priority findings are:

1. **Performance is unavailable:** the live API returns HTTP 503 because eligible forecasts exist but no Performance reports have been published. Production scheduling covers context reports, not Performance or external-comparison reports.
2. **Recent Form remains unavailable despite the recent UI fix:** approximately 204,000 context refreshes are pending. All 430 fixtures in the sampled UTC day have pending generations. A maximum batch of 32, scheduled once per minute in the shared bulk lane, cannot promptly serve current fixtures behind this backlog.
3. **External source accuracy is inconsistent with current settlement:** the source summary reads first-result rows while prediction rows read latest revisions. There are 16 concrete disagreements, all now `PENDING`, but still counted as settled by the summary.
4. **External predictions have additional correctness gaps:** parsers can assign selections to the wrong date; unmatched imports cannot acquire a later fixture binding through a normal identical retry; comparison reports are absent; and failed source collection can be reported as a successful job.
5. **Synchronization failures are real but have multiple causes:** unresolved historical fixture recovery, identity/season evidence gaps, DNS/transport failures, and expired worker ownership. Relaxing identity or temporal checks would hide these problems and corrupt the guarantees the system is designed to preserve.
6. **Frontend defects extend beyond missing data:** mobile Predictions navigation disappears, consensus counts rows as sources across markets, score-matrix columns are misaligned and inaccessible, time labels are wrong, and simulated/loading or healthy-status indicators can contradict actual state.

No new **Critical** defect was confirmed. This is not a certification of absence of leakage, security vulnerabilities, or corruption. Five findings are rated High; the remaining findings and risks require the verification described below. In particular, model quality and full artifact reproduction were not re-evaluated.

### Severity and verification definitions

| Term | Meaning in this report |
| --- | --- |
| Critical | Confirmed leakage, destructive corruption, serious security compromise, or comparable system-wide correctness failure. None confirmed in this audit. |
| High | A core user workflow is unavailable or produces materially unreliable results. |
| Medium | A bounded correctness/reliability defect, degraded workflow, or a concrete scaling/recovery weakness. |
| Low | A limited display, navigation/filter consistency, or documentation defect. |
| Confirmed—runtime | Observed in the running local application or read-only database queries, with a corresponding source path. |
| Confirmed—code/reproduction | The implementation demonstrates the failure, sometimes with a small offline reproduction; no claim that every condition occurred in production. |
| Suspected | Evidence indicates a problem, but its cause or complete impact is not established. |
| Known blocker | Already recorded by the project; not reclassified as a new implementation defect. |
| Unverified risk | Requires additional access, an isolated environment, or a separately authorized exercise. |

Effort estimates are planning ranges for implementation and focused verification: **S** = about 0.5–1 engineer-day; **M** = 2–4 days; **L** = 5–10 days. They exclude provider waiting time, identity adjudication, rollout approval, and large data recovery. They are not delivery commitments.

## 2. Scope, authority, and method

### Decisions preserved

Read `AGENTS.md`, `docs/architecture.md`, `docs/project-status.json`, `PLAN.md`, `docs/backtesting.md`, `docs/model-governance.md`, `docs/contracts/live-match-context-v1.md`, the MVP completion/source documentation, and relevant migrations and implementation. Applied the API contract and accessibility audit workflows. Classified the audit as L3 because it covers historical correctness, governance, identity, and concurrent workers.

The tracked state says:

- Architecture V2 is `IN_PROGRESS`, through phase 33, with phases 34–48 pending and `runtime_cutover=false`. No live Wayfinder tool/map was available in this session; the tracked status and referenced decisions were used. This audit does not complete or reopen any map.
- `MF-AUD-0009` remains open; broader R3 identity/history acceptance is not met.
- Sprint 2 remains `FAIL` / `RETAIN_FAIL_AND_STOP`; Phase 3 remains blocked except for specifically authorized research.
- The multi-model evaluation retained the champion. Context and H2H research were rejected; their absence from predictive inputs is intentional. The final full-coverage reevaluation track remains `PREEXECUTION_DATA_INTEGRITY_BLOCK`.
- Simulation evidence and research diagnostics are intentionally not exposed by the public MVP API. Unsupported markets, unavailable source data, Forebet's access block, and fewer-than-50-forecast `UNRATED` results are not bugs by themselves.
- External collection deliberately retains structured facts rather than copied pages/articles under its private-local policy. This audit does not recommend bypassing that restriction.

The source already includes recent fixes for invalid season bounds, Recent Form rendering without a forecast, context refresh generation, and continued 503 polling. Old failure logs are not sufficient to declare those fixes ineffective. The current context backlog is separately confirmed below.

### Coverage matrix

| Area | Reviewed and exercised | Limits |
| --- | --- | --- |
| Fixtures `/` | Filters, date/status controls, competition rail, fixture rows, probabilities, expansion, polling; live list API | No provider acquisition or exhaustive traversal of every competition/date |
| All nine fixture tabs | Live Match, Overview, Markets, Score matrix, H2H context, Team statistics, Simulation evidence, Diagnostics, Forecast history | One representative forecasted fixture exercised end-to-end; context currently fails |
| Performance | UI filters/pagination and error state; API selection, source fingerprints, Python report generation, persisted reports | Successful populated live page blocked by missing reports; no report written |
| External predictions | Date/facets, source summaries, consensus, table states, settlement, collection/import, parser dates, matching | No fresh source requests; 20 unmatched records rechecked read-only |
| Admin | Initial page, status/coverage, hooks, start/stop/retry contracts, lanes, job status and logs | No mutation button activated; control endpoints reviewed only |
| Backend | Registered public/admin routes, validation, timeouts, CORS/local admin checks, SQL readers, readiness | No penetration/load test or destructive error injection |
| Providers and history | FotMob/PitchAPI operational paths; API-Football quota/context; football-data.org fallback; OpenFootball/Football-Data.co.uk backfill paths; identity and history work | Entitlements and upstream availability not re-probed; held identities not changed |
| Forecasting | Product forecast preparation/publication, refresh work, artifact checks, score buckets, analytics, PIT contracts, evaluation stop state | No fitting, protected-outcome access, authoritative evaluation, promotion, or full replay |
| Storage/infrastructure | Migrations, raw/Parquet/artifact ownership, work registry/fences, sync runner, scheduler, PostgreSQL activity, Redis readiness, Compose, systemd and CI | No restore, failover, crash, Redis restart, migration execution, or resource saturation exercise |
| Accessibility | Chromium/Playwright + axe on four routes; expanded matrix; tab arrow navigation; 320px reflow on Fixtures/Predictions | No VoiceOver/Safari session, full zoom/text-spacing/forced-color review, or WCAG conformance claim |

### Safety and execution

- API requests were local, read-only GETs. Browser automation blocked non-GET `/v1/` requests. Source review verified that the context GET does not enqueue work.
- Database connections used `default_transaction_read_only=on` and 10–12 second statement timeouts. Queries read aggregates, bounded samples, metadata, and existing logs. Existing background workers continued independently.
- No credentials or raw `.env` contents are reproduced here. The live `/version` reports `dev`, so exact running-binary/source-SHA parity is **unverified**. Static findings refer to the audited SHA; runtime findings refer to the observed service.
- Reviewed the Makefile graph. Per the repository's prose-only delivery policy, did **not** run `make check`, integration, build, lint, or code-test suites. Executed targeted read-only browser/API/database and offline parser checks instead. Historical test counts in project status were not claimed as newly executed tests.
- The first axe attempt used the wrong Playwright context construction and failed. It was terminated and rerun correctly. A first score-matrix probe omitted the documented NULL-to-legacy-version conversion and rejected six legacy rows; the corrected probe used the actual serving convention. Neither audit-harness failure is an application finding.

## 3. Complete findings

### A. Serving, context, and analytics

#### MF26-01 — Performance report production is disconnected from normal operation

**High · Confirmed—runtime and code · L**

- **Expected:** settled eligible forecasts produce readable league Performance results for all supported horizons; one pending league does not silently masquerade as no data.
- **Actual:** `GET /v1/performance?page=1&page_size=20` returned **503**, `{"error":"product data unavailable"}`, in 0.457s. The page shows the corresponding error. `product_read_reports` contained only `CONTEXT` rows, with no `PERFORMANCE` rows. Eligible source rows existed, including Primera B: 9 and Serie A: 18.
- **Evidence/files:** `go/api/internal/app/performance_store.go:45,110,154`; `go/api/internal/app/read_reports.go:16`; `python/football/src/football/product/public_reports.py:36,166`; `public_reports_cli.py`; `go/api/internal/app/app.go:180,206`; migration `202610200100_public_read_reports.sql`.
- **Root cause:** serving requires a report with the current source fingerprint. A nonzero source count with no matching report fails decoding, aborting the whole page. The explicit report CLI can produce it, but normal scheduler wiring only builds context reports. New outcomes/revisions would invalidate manually generated reports again.
- **Resolution:** connect Performance invalidation and bounded report production to the authorized work mechanism; cover all horizons. Define an explicit pending/failed report state and avoid one missing report blanking unrelated leagues. Keep analytics mathematics and historical eligibility unchanged.
- **Acceptance:** from a disposable database, ingest/persist a permitted result and forecast, run normal workers, and read the populated page without invoking the report CLI manually. Repeat after correction and at every horizon; verify counts and metrics against the Python owner.

#### MF26-02 — Context backlog prevents timely Recent Form, H2H, and team statistics

**High · Confirmed—runtime and code · M–L**

- **Expected:** context for current/upcoming fixtures becomes available promptly after deployment or source changes.
- **Actual:** 206,251 work rows, **203,979 pending**, with the oldest pending request at `2026-10-28T20:55:26.452040Z`. All **430/430** fixtures in the sampled UTC day had pending generations. The sampled fixture context endpoint returned 503; Overview displayed “Recent form is refreshing”; H2H and Team statistics also failed.
- **Evidence/files:** `python/football/src/football/product/public_reports.py:249` selects `ORDER BY requested_at,kickoff_at,fixture_id LIMIT 32`; `go/api/internal/app/app.go:206` runs once per minute; `admin_sync.go:310` places context in `BULK`; migration `202610280100_context_report_refresh_worklist.sql:28` seeds all serving fixtures. The queue head included December 2026 and December 2025 fixtures while today's fixtures remained pending.
- **Root cause:** bulk bootstrap order dominates user relevance, batch throughput is small, and context competes with other bulk jobs. At 32 completions/minute, 203,979 rows require **at least 106.2 hours**, ignoring worker duration, lane contention, new invalidations, and failures. Browser retries cannot solve this scheduling problem.
- **Resolution:** prioritize current/upcoming and explicitly requested scopes under an approved bounded policy, separate bootstrap/backlog handling from timely refresh, and expose queue age and report status. Preserve generation fencing and PIT eligibility. Do not remove identity checks to fill the UI.
- **Acceptance:** reproduce a large historical backlog and verify current-day contexts complete within an owner-approved latency bound while older work progresses fairly; preserve retry and generation correctness.

#### MF26-03 — External MatchForge agreement silently loses its report producer

**High · Confirmed—runtime and code · M**

- **Expected:** a selection with a supported market and a corresponding stored forecast receives a reproducible comparison; pending computation is distinguishable from unsupported input.
- **Actual:** no `COMPARISON` reports existed. `attachComparison` returns `UNABLE_TO_EVALUATE` whenever report bytes/digest are absent, even if a forecast was selected. The query recomputes the source fingerprint but there is no normal comparison-report scheduler.
- **Evidence/files:** `go/api/internal/app/postgres_store.go:439`; `read_reports.go:28`; `python/football/src/football/product/public_reports.py`; `public_reports_cli.py`; `app.go` scheduler wiring.
- **Root cause:** a derived-report dependency was added to serving without a corresponding automated production/invalidation lifecycle. Missing work is collapsed into the same enum as an unsupported market.
- **Resolution:** enqueue/rebuild comparisons on selection and relevant forecast changes, retain the existing probability-based agreement rule, and expose pending/failed/unsupported separately. This does not authorize using external picks as model inputs.
- **Acceptance:** a supported matched selection becomes comparable through normal operation; unsupported picks remain explicitly unsupported; source agreement rates follow the same records.

#### MF26-04 — Missing score provenance is encoded as fresh

**Medium · Confirmed—code · S**

- **Expected:** missing provenance is unknown/unavailable, not evidence of freshness.
- **Actual:** fixture listing uses `COALESCE(observation.stale_after < clock_timestamp(), false)`. A fixture without a matching score observation therefore has `stale=false`. The browser sample had a scheduled fixture without score provenance, alongside stale incident data.
- **Evidence/files:** `go/api/internal/app/postgres_store.go:51,69,134`; `web/components/fixture-explorer.tsx` status rendering; `expanded-fixture.tsx` provenance rendering.
- **Root cause:** a boolean freshness contract conflates “no observation/deadline” with “not stale.”
- **Resolution:** represent unknown freshness explicitly or derive it from observation presence before presenting a health indication. Preserve separate score/event/statistics provenance.
- **Acceptance:** fixtures with absent, fresh, and expired observations display three distinguishable states.

#### MF26-05 — Score/status and incident feeds can present contradictory match state

**Medium · Confirmed—runtime; underlying mapping cause suspected · M**

- **Expected:** a partial feed explains conflicting or missing lifecycle information rather than presenting it as an ordinary scheduled match.
- **Actual:** MC Oran–Olympique Akbou, fixture `dffecb0c-fdff-5811-a276-5ddebc9a71c2`, remained `SCHEDULED`, kickoff `2026-10-30T19:00:00Z`, no score, no score source. Live Match displayed a 20-minute red-card incident from FotMob match `5989865`. There were no canonical fixture observations for this fixture in the sampled query, but a normalized event resource existed. The API correctly marked the response partial and the incident stale; it did not reconcile or prominently explain the contradiction.
- **Evidence/files:** `go/api/internal/app/postgres_store.go:134` joins lifecycle/score and resources independently; `python/football/src/football/product/operational_provider_sync.py` resource ingestion/reconciliation; `web/components/expanded-fixture.tsx` Live Match panel.
- **Root cause:** independently acquired resource data can be linked while the canonical lifecycle remains unresolved. Why this specific score observation is absent requires source/mapping adjudication; an incorrect identity merge is **not established**.
- **Resolution:** investigate the retained native fixture/identity evidence and expose a clear lifecycle-conflict/score-unavailable state. Do not infer canonical results from incidents or force a name-based merge.
- **Acceptance:** resolve or explicitly disposition this fixture and test partial-resource combinations with lifecycle conflicts.

### B. External collection, matching, settlement, and accuracy

#### MF26-06 — Source accuracy reads obsolete first settlements

**High · Confirmed—runtime and code · M**

- **Expected:** prediction rows and source accuracy use the same current eligible settlement revision, including corrections and withdrawals.
- **Actual:** 39 first-result rows contained 33 correct selections. Latest revision state instead contained 18 `WON`, 5 `LOST`, and 23 `PENDING` across 46 mapped selections. **16 first-result rows disagreed with current eligibility: 15 previously correct and 1 previously incorrect were now PENDING.** They still contribute to source accuracy.
- **Evidence/files:** `external_predictions.py:24` appends revisions but inserts `external_prediction_results` with `ON CONFLICT(prediction_id) DO NOTHING`; `postgres_store.go:439` uses latest revisions for rows; `postgres_store.go:512` aggregates the first-result table.
- **Root cause:** two settlement authorities remain in active use. Preserving the original result is appropriate for history, but using it as current accuracy is not.
- **Resolution:** make current summaries consume the same revision selection and eligibility policy as row displays. Preserve all prior records; do not overwrite historical outcomes or broaden score-basis eligibility.
- **Acceptance:** transitions WON→LOST, WON→PENDING, LOST→VOID, and eligible corrections update both views consistently. Test retries and concurrent settlement, including a return to an earlier semantic state.

#### MF26-07 — External parsers accept the wrong prediction day

**High · Confirmed—offline reproduction · S–M**

- **Expected:** source-displayed day must match the requested day before selections are assigned that partition.
- **Actual:** R2Bet checks only that `%b %Y` occurs in its detected date. A page displaying `29th, Thu Oct 2026`, requested as 30 October, emitted a row stored as `2026-10-30`. 1960Tips uses substring matching: a heading `Predictions 11 Oct 2026`, requested as 1 October, emitted a row stored as `2026-10-01`.
- **Evidence/files:** `python/football/src/football/product/external_prediction_sources.py:158,214`; the synthetic HTML reproductions in section 5. No upstream calls were made.
- **Root cause:** incomplete or unanchored text matching followed by assignment of the caller's date rather than validation of a parsed source date.
- **Resolution:** parse each provider's full displayed date, compare exact calendar dates, and retain original text. Quarantine mismatches. Review affected retained structured records; do not silently rewrite immutable selections.
- **Acceptance:** same-month wrong-day, 1-versus-11/21/31, year boundary, malformed date, and valid source formats have explicit outcomes.

#### MF26-08 — Identical reimports cannot recover an unmatched fixture binding

**Medium · Confirmed—code; operational impact partly measured · M**

- **Expected:** a selection collected before fixture availability can later acquire a verified binding through a traceable correction workflow.
- **Actual:** `_match_fixture` reruns, but the insert conflicts on a hash that excludes the resolved fixture/mapping outcome and does nothing. The existing immutable row retains NULL `fixture_id`. Settlement inner-joins `product_fixtures`, so it will never reach that selection. No append-only external mapping correction consumer was found.
- **Evidence/files:** `external_predictions.py:142,197,257`; external prediction schema/mapping migrations. Runtime: 1,094 `UNMATCHED`, 7 `AMBIGUOUS`, 46 `MATCHED` among 1,147 selections. A bounded recheck of 20 latest unmatched selections still found all 20 unmatched; this audit does **not** claim the whole backlog is currently recoverable.
- **Root cause:** immutable source revision identity and mutable resolution progress are stored in one row, without a separate revision path for binding decisions.
- **Resolution:** introduce an approved append-only binding/correction workflow consuming independently verified identities; leave original selection bytes/fields intact. Surface unresolved reasons and review work.
- **Acceptance:** collect before the fixture exists, add verified mapping evidence in an isolated database, retry resolution, and settle without changing the original source revision or duplicating the pick.

#### MF26-09 — Collection failures can be reported as successful synchronization

**Medium · Confirmed—code and retained runtime history · S–M**

- **Expected:** preserve successful sources while truthfully reporting failures among sources attempted in that run.
- **Actual:** `_run_external_predictions` prints `status="COMPLETED"` and returns zero after source-level transport, parser, or persistence failures. `syncCompletion` only treats `COMPLETED_WITH_ERRORS` as failed. Existing 8/9 October jobs were `SUCCEEDED` despite SlyBet `PARSER_BROKEN` in their summaries. The current code still has this aggregate-status behavior; the particular old SlyBet parser issue may already be repaired.
- **Evidence/files:** `product/cli.py:866,916`; `external_prediction_sources.py:398`; `go/api/internal/app/admin_sync.go:493`.
- **Root cause:** source errors are retained as details but excluded from overall completion classification. Registry `checked_at` also remains the static qualification date, not latest collection health.
- **Resolution:** distinguish successful, partial, failed, intentionally disabled, and out-of-window collection. Keep source isolation; do not treat the intentionally disabled Forebet adapter as a new failing attempt. Display runtime health separately from access qualification.
- **Acceptance:** one/all attempted sources failing yields truthful aggregate status and visible reason, while successful rows remain committed and retryable.

#### MF26-10 — Settlement repeatedly scans all mapped selections

**Medium · Confirmed—code scaling defect; no present saturation proven · M**

- **Expected:** bounded, retryable settlement of changed result/selection scopes, including corrections.
- **Actual:** every call selects every mapped external prediction, performs a lateral provider-observation lookup, `fetchall()`, then attempts a revision insert for each and a legacy-result insert for eligible rows. There is no batch/checkpoint or changed-scope filter. Both operational provider syncs invoke this shared sweep.
- **Evidence/files:** `external_predictions.py:24`; `operational_provider_sync.py` settlement call around line 749; `sync.py:987`. Current scale was only 46 mapped predictions and 171 revisions, so a large performance incident is not inferred from these counts.
- **Root cause:** idempotent conflict handling is being used in place of incremental work selection.
- **Resolution:** enqueue affected predictions on canonical result/basis changes and imports, claim bounded batches, preserve correction history, and make retries converge. Keep a bounded reconciliation scan as a separately controlled recovery mechanism if required.
- **Acceptance:** unchanged runs perform bounded work; large backlogs resume after interruption; concurrent providers cannot publish an older result as current.

#### MF26-11 — Source accuracy includes selections first captured after kickoff

**Medium · Confirmed—runtime; intended retrospective policy needs clarification · M**

- **Expected:** prospective accuracy is distinguished from retrospective capture, with the eligible denominator explicit.
- **Actual:** **12/46** matched selections were first collected at or after current fixture kickoff; all 12 were present in the first-result accuracy table. The source aggregation has no capture-before-kickoff eligibility predicate. The table is not evidence that these picks were independently observed before the outcome became available.
- **Evidence/files:** `external_predictions.py:142`; `postgres_store.go:512`; `web/components/predictions-page.tsx` Source Audit. Source documentation permits structured historical collection but does not establish prospective publication time for these records.
- **Root cause:** collection provenance and prospective evaluation eligibility are not separated in source metrics.
- **Resolution:** decide and document the display policy: report retrospective capture separately, or require defensible pre-kickoff observation for prospective accuracy. Preserve original capture clocks. Do not apply the MatchForge research evaluation label to these descriptive source statistics.
- **Acceptance:** late/unknown-time records cannot silently increase a prospective hit rate; both denominators are visible and reproducible.

#### MF26-12 — Collection does not itself settle newly imported completed fixtures

**Medium · Confirmed—code · S–M**

- **Expected:** importing a selection for an already resolved match schedules its settlement without depending on another unrelated provider update.
- **Actual:** collection/import commits selections and returns; settlement is invoked by MVP/provider sync. The daily script runs MVP sync **before** collection. Newly imported historical selections can therefore wait for the next successful provider/MVP run even when their result is already stored.
- **Evidence/files:** `product/cli.py:866` and `_run_external_import`; `external_predictions.py:142`; `scripts/mvp-refresh.sh`; `sync.py:987`; `operational_provider_sync.py:749`.
- **Root cause:** settlement triggers are tied to provider jobs, not both sources of change: results and selections.
- **Resolution:** include collection/import in the bounded settlement invalidation path from MF26-10.
- **Acceptance:** import against an existing verified final result, with provider jobs stopped in an isolated environment; normal local work processing settles it.

### C. Data pipelines and operational reliability

#### MF26-13 — Repeated unresolved recovery contaminates routine sync health

**Medium · Confirmed operational failure; individual identity causes unresolved · M**

- **Expected:** useful current acquisition proceeds while held/unsupported/missing historical fixtures have actionable, scoped recovery states.
- **Actual:** in the observed trailing seven days, FotMob had 266 failed runs versus 236 succeeded; PitchAPI had 51 failed versus 234 succeeded (cancellations and active runs excluded from those pairs). A representative FotMob run fetched 305 rows using 20/20 successful requests, but was `FAILED` because two recovery fixtures were absent from provider responses. Its diagnostics recorded 1,748 unresolved fixtures outside the current window, 1,737 without a verified supported provider, and 234 unmatched rows in the run. Repeated missing-recovery failures dominated the FotMob failure group (226 runs).
- **Evidence/files:** run `add630ef-2ccd-4fea-83a6-4ca2bdec821f`; `product_sync_runs.summary`; `operational_provider_sync.py:769,855`; `admin_sync.go:493`.
- **Root cause:** missing recovery targets increment the same run-level failure counter as acquisition faults; persistent held cases repeatedly dominate operational health. Some causes are legitimate missing evidence, not bad transport or faulty rejection.
- **Resolution:** retain failures and held evidence, but separate current acquisition outcome from recovery backlog disposition. Apply scoped retry/terminal-review policy only after investigating the native response and supported scope. Report unchanged blockers without implying that every successful HTTP request advanced canonical data.
- **Acceptance:** a held recovery fixture remains visible/actionable without obscuring fresh acquisition success; quota-aware retries do not repeatedly hammer an unresolvable scope. No false `SUCCEEDED` admission or forced merge.

#### MF26-14 — Worker ownership failures and expired history claims need recovery verification

**Medium · Confirmed incidents; root cause suspected · M–L**

- **Expected:** interruption and lease loss leave work recoverable, and healthy workers can heartbeat despite concurrent serving/other jobs.
- **Actual:** recent failure groups included 16 PitchAPI and 10 FotMob “worker lease expired; safe to retry” failures, plus 14 PitchAPI and 11 FotMob worker-publication failures. Two inspected logs explicitly say `sync worker ownership lost` in `authorize_worker_publication()`. Six `HISTORICAL_ACQUISITION` items remained `RUNNING` with expired leases ranging from 29 October 18:12 UTC to 30 October 03:05 UTC. At a later sample, three active sync-run leases were current and PostgreSQL showed no sustained blocked transaction, so present database saturation was not demonstrated.
- **Evidence/files:** logs `.local/sync-runs/0064c998-ac3f-4d15-a141-2b474d490621.log` and `960000d1-9bbf-4930-a547-aed022ef9bda.log`; `admin_sync.go:459`; `football/work/storage.py`; history work/lease migrations and workers.
- **Root cause:** fencing correctly prevents publication after ownership loss. The initiating cause—process restarts/sleep, cancellation, connection contention, heartbeat delay, or an orchestration defect—was not established. Expired rows alone do not prove irrecoverability; no new claim was issued during this audit.
- **Resolution:** correlate job IDs, process lifecycle and database waits; expose lease loss reason/age; demonstrate domain-worker reclaim on a disposable database. Preserve fencing. Do not “fix” this by allowing expired workers to publish.
- **Acceptance:** kill/restart and heartbeat-failure scenarios converge without lost checkpoints, duplicate publication, indefinite RUNNING UI state, or retry storms.

#### MF26-15 — Daily refresh skips independent external collection after sync failure

**Medium · Confirmed—code · S**

- **Expected:** independent collection can proceed even if fixture sync partially fails, while the overall scheduled result remains truthful.
- **Actual:** `scripts/mvp-refresh.sh` uses `set -eu`, then `make mvp-sync`, then `make external-predictions`. A nonzero first command prevents the second from running. The frequent sync failure conditions above make this coupling operationally relevant; this audit did not prove the systemd timer is installed on the local macOS host.
- **Evidence/files:** `scripts/mvp-refresh.sh:1`; `infrastructure/systemd/matchforge-mvp-refresh.service` and `.timer`.
- **Root cause:** shell fail-fast sequencing couples otherwise independent sources.
- **Resolution:** execute independently safe stages with captured statuses and return an honest aggregate outcome. Settlement/report work must still obey its dependencies.
- **Acceptance:** inject a sync failure into an isolated wrapper test; collection is attempted once and the job does not report an all-success result.

#### MF26-16 — External read endpoints do unbounded per-source comparison work

**Medium · Confirmed—code scaling risk; current requests succeeded · M**

- **Expected:** date/source archives have bounded retrieval and scalable aggregate metrics.
- **Actual:** external predictions have no pagination/row bound, and agreement filtering occurs after loading rows. `ExternalPredictionSources` aggregates source totals, then calls `ExternalPredictions` once per returned source to calculate agreement, repeating source-fingerprint/report work. Unscoped requests grow with the full retained archive.
- **Evidence/files:** `postgres_store.go:439,512`; `web/lib/api.ts`; `predictions-page.tsx` renders every returned row. The scoped local requests succeeded in milliseconds; no load-test claim is made.
- **Root cause:** row retrieval is reused as an aggregation mechanism and the archive contract is unbounded.
- **Resolution:** define pagination/cursor and bounded aggregate queries or reports, keyed by every filter. Verify agreement denominators independently of row pages.
- **Acceptance:** representative large archives meet an agreed latency/memory budget, cancellation works, and results remain stable across pages and filters.

### D. Frontend functionality and presentation

#### MF26-17 — External “consensus” counts records as independent sources

**Medium · Confirmed—code · M**

- **Expected:** “2+ verified sources” and “N of M sources” mean distinct eligible sources agreeing on the same market for the same resolved fixture.
- **Actual:** `consensusRows` groups only by fixture ID or date/team text, counts every row by selection, and uses the number of rows as the denominator. It neither groups by market nor deduplicates source revisions nor enforces two verified sources. Multiple picks from one source can be presented as a multi-source consensus; unmatched same-name fixtures can be grouped together.
- **Evidence/files:** `predictions-page.tsx:343,507`; append-only selection revisions in `external_predictions.py`.
- **Root cause:** record counts and display names substitute for source and fixture/market identity in a user-facing comparison.
- **Resolution:** define the display policy for source revisions, use verified fixture + market keys and distinct source identities, and explicitly exclude or separately display unresolved comparisons. Keep this entirely outside model probabilities.
- **Acceptance:** one source with multiple revisions/markets never counts as multiple independent sources; ambiguous fixtures do not merge; the threshold label is actually enforced.

#### MF26-18 — Predictions has no mobile navigation

**Medium · Confirmed—browser and code · S**

- **Expected:** all four application sections remain reachable at narrow widths.
- **Actual:** at 320px, `/predictions` has **zero visible navigation links**. `AppShell` bypasses its standard/mobile navigation for this route, while the replacement header hides its nav below `md`. The logo still reaches Home, but Performance/Admin navigation is lost.
- **Evidence/files:** `web/components/app-shell.tsx:15`; `predictions-page.tsx:172`; Chromium DOM visibility check.
- **Root cause:** the custom page shell does not implement the mobile navigation it replaces.
- **Resolution/acceptance:** provide consistent keyboard-accessible mobile navigation and verify all four routes at 320px and intermediate widths.

#### MF26-19 — Score matrix has incorrect alignment, table semantics, and contrast

**Medium · Confirmed—browser/axe and code · S–M**

- **Expected:** each away-goal header aligns with its cells, rows/columns are conveyed to assistive technology, and text remains readable across heat levels.
- **Actual:** at 1440px, the `0 goals` header began at x=301, but the `0–0` cell began at x=433; subsequent columns also drifted. The parent grid has five columns while each nested row spans four and creates another five-column grid. Axe reported `aria-required-children` on `role="table"` and four contrast failures: 3.70, 3.45, 3.46, and 3.18 versus the 4.5:1 requirement for these small labels.
- **Evidence/files:** `expanded-fixture.tsx:183`; `web/app/globals.css:21`; browser bounding rectangles and axe output. Relevant criteria: structure/name-role relationships and text contrast (WCAG 1.3.1, 4.1.2, 1.4.3).
- **Root cause:** visual grids are nested inconsistently and ARIA table semantics are incomplete; muted text is reused over variable heat backgrounds.
- **Resolution:** use a correctly aligned native table or complete semantic grid/table structure, with contrast-safe text throughout the approved heat range.
- **Acceptance:** verify every header/cell relationship, keyboard/screen-reader reading order, responsive scrolling, and contrast at low/high probabilities.

#### MF26-20 — External time labels disagree with the formatter

**Low · Confirmed—code and browser labels · S**

- **Expected:** timestamp labels match the timezone used to format values.
- **Actual:** header says `UTC+0 London`, the table says `Date (UTC)`, and consensus appends `UTC`; the formatting helpers use `DISPLAY_TIME_ZONE` (`Africa/Lagos`). Times are one hour ahead of UTC while labeled UTC. The date partition is also not clearly distinguished from capture date.
- **Evidence/files:** `predictions-page.tsx:191,343,396,536`; `web/lib/display-date.ts`.
- **Root cause:** copied display labels bypass the shared timezone contract.
- **Resolution/acceptance:** label partition, capture time, and kickoff consistently; test midnight crossings with explicit UTC and Lagos examples.

#### MF26-21 — Healthy feed indicators are not connected to health

**Medium · Confirmed—browser and code · S–M**

- **Expected:** freshness/availability indicators reflect successful observation and loading/error state.
- **Actual:** AppShell and Predictions hardcode `Feed: Live`. Predictions renders `Cluster Synced` whenever it is not refreshing, including loading/error conditions. Clicking its simulated loading state showed “Loading external selections” together with “Cluster Synced.” Performance can be unavailable while the shell still says the feed is live.
- **Evidence/files:** `app-shell.tsx:38`; `predictions-page.tsx:190,327`; `use-resource.ts` state semantics.
- **Root cause:** static decorative indicators are presented as operational facts.
- **Resolution/acceptance:** derive scoped status from actual request/freshness information, distinguish unknown/stale/error, and avoid claiming cluster-wide health from one request. Verify offline and refresh-failure states.

#### MF26-22 — Production Predictions exposes simulated empty/loading controls

**Low · Confirmed—browser and code · S**

- **Expected:** the table reflects stored records and actual request state.
- **Actual:** “Empty State” hides actual rows and “Ingestion Skeleton” forces indefinite loading until the user switches modes. These are production controls, not merely test fixtures. The simulated state is not clearly described as a preview of an interface state.
- **Evidence/files:** `predictions-page.tsx:376`; `PredictionTableResource`; browser activation of “Ingestion Skeleton.”
- **Root cause:** presentation/demo state selection remains in the operational route.
- **Resolution/acceptance:** remove it from the normal workflow or explicitly isolate it in authorized preview tooling; loading/empty states must track real resources.

#### MF26-23 — Successfully loaded context does not refresh while the fixture stays open

**Medium · Confirmed—code · S–M**

- **Expected:** after a displayed fixture's context changes, its open analysis can refresh without collapsing/reopening the fixture.
- **Actual:** context is keyed only by fixture ID and automatically retried only on 503. Successful context does not poll or react to fixture/live/context revision changes. Fixture and Live Match requests refresh separately, leaving successful form/lineup/availability data potentially stale.
- **Evidence/files:** `expanded-fixture.tsx:41–67`; `web/hooks/use-resource.ts`; `docs/contracts/live-match-context-v1.md` polling expectations.
- **Root cause:** recovery polling and ongoing freshness are separate requirements; only recovery is wired for context.
- **Resolution/acceptance:** invalidate successful context using an actual revision/freshness signal or bounded polling appropriate to kickoff and visibility; demonstrate an updated lineup/context while keeping the panel open, without changing stored forecast probabilities.

#### MF26-24 — Admin stops observing schedules when no job is active

**Medium · Confirmed—code · S**

- **Expected:** an idle Admin page notices a later scheduled job and updates coverage/status.
- **Actual:** `useSyncStatus` polls only when its existing local `runs` contain an active job. If opened between runs, or after the last observed job finishes, no timer discovers the next background run. The page can continue saying no sync is running until a manual action/reload.
- **Evidence/files:** `web/hooks/use-sync-admin.ts:65`; `data-sync-admin.tsx` status panel.
- **Root cause:** polling frequency depends on already knowing about activity, with no idle discovery poll.
- **Resolution/acceptance:** use a lower-frequency idle/visibility-aware status refresh and faster active polling. Verify a scheduler-started run after the UI reaches idle.

#### MF26-25 — Competition rail can create contradictory filters

**Low · Confirmed—code · S**

- **Expected:** selecting a league from the rail yields a coherent scope.
- **Actual:** the rail always shows the first 18 competitions, irrespective of continent/country filters. Clicking one changes only `competition`; incompatible continent/country filters remain active. The API then receives an impossible intersection and shows no fixtures.
- **Evidence/files:** `fixture-explorer.tsx:62`, `FixtureFilters`, and `fixtureLoad` query construction.
- **Root cause:** rail selection does not share the dependent-filter reset logic used by the filter strip.
- **Resolution/acceptance:** scope rail choices to the current geography or update/reset dependent filters on selection. Test switching between incompatible countries through both controls.

### E. Documentation and auditability

#### MF26-26 — Agent guidance references missing supporting documents

**Low · Confirmed—filesystem · S**

- **Expected:** required engineering guidance resolves to current files.
- **Actual:** `AGENTS.md` points to missing `docs/engineering/git-delivery.md`, `writing-style.md`, `review-checklist.md`, and `testing.md`. Delivery, writing, and review guidance exist at `docs/git-delivery.md`, `docs/writing-style.md`, and `docs/review-checklist.md`; testing guidance is split among other existing documents. The initial required delivery read failed until the actual file was located.
- **Evidence/files:** `AGENTS.md:164,464,539,566`; referenced files and `docs/engineering/test-matrix.md`. Tracked project status is dated 20 October and cannot by itself attest to the 30 October runtime; its old PASS entries were treated as historical evidence.
- **Root cause:** references were not updated with document organization; historical completion statements are easy to mistake for current service health.
- **Resolution/acceptance:** repair links and make current/historical operational evidence clearly distinguishable without rewriting frozen decisions. Validate referenced paths with a documentation-specific check.

## 4. Existing blockers, suspected issues, and unverified risks

These items are separate from confirmed new defects. They must not be “fixed” by weakening contracts.

| ID | Severity / status | Evidence and consequence | Required next action |
| --- | --- | --- | --- |
| KB-01 | High · Known blocker | Project status retains R3 identity/history acceptance failure: 605 original FotMob team IDs, 108 origin declarations, and 210 original competition IDs held at that recorded checkpoint. Runtime sync still reports absent season labels and explicit cross-provider evidence requirements. These historical cohort counts were not re-audited as today's totals. | Resume only a newly authorized, evidence-based mapping route. Resolve native scopes and disputes prospectively; preserve denied and historical decisions. |
| KB-02 | Medium · Known blocker | API-Football season entitlements, football-data.org CL2020 access, incomplete PitchAPI proof, unsupported/cancelled scopes, and Forebet technical access restrictions are documented. Some cannot be solved in code alone. | Check exact entitlement/evidence under approved budgets; classify supported, deferred, denied, and terminal scopes. Do not bypass access controls or substitute another provider as proof for a provider-specific scope. |
| KB-03 | Medium · Intentional incomplete phase | Architecture V2 phases 34–48 and cutover are not complete. Shadow registries/projections are not proof that every production consumer/worker has moved. The Performance/comparison gaps are actual existing public-workflow failures, distinct from optional future migration work. | Repair current public workflows within explicit authorization; do not use this audit as permission for wholesale cutover. |
| KB-04 | High impact if ignored · Intentional governance stop | Sprint 2 failure, closed challengers, spent/protected targets, and final reevaluation integrity block remain authoritative. No new model promotion is justified by UI repair or larger raw history counts. | Retain champion and frozen criteria; any new scientific execution needs its own owner decision and admissible corpus. |
| R-01 | Medium · Suspected operational cause | DNS errors on FotMob and PitchAPI transport failures occurred; recent provider jobs also succeeded. Historical invalid-season-bound failures predate a source fix already in HEAD. | Correlate exact timestamps, network/process logs, and deployed revision before filing duplicate parser/season defects. |
| R-02 | Medium · Suspected batch recovery weakness | `run_public_reports` calls `_snapshot` outside `_publish`'s failure-recording block. A malformed/invalid scope can abort the selected batch before later scopes are attempted; FIFO context selection can repeatedly revisit it. No poisoned scope was demonstrated. | Add isolated failure-injection coverage and per-scope disposition without weakening report validation; measure starvation under a failing head item. |
| R-03 | Medium · Unverified recovery | Six expired history leases were observed, but no reclaim/restart exercise was authorized. Existing fences are protective, not evidence of a bug by themselves. | Perform the disposable-database recovery acceptance in MF26-14. |
| R-04 | Medium · Unverified deployment/monitoring | Work/domain metrics and administrative endpoints exist. Current alert delivery, automatic daily scheduling on this host, retention/rotation of accumulating `.local/sync-runs` logs, disk-pressure behavior, and operator response were not established. | Inventory deployed schedules, owners, metrics consumers, retention and alerts; test age/failure alarms without provider traffic. |
| R-05 | High consequence · Unverified restore | Prior Architecture V2 backup/restore evidence exists. This audit did not reproduce restoration of today's database together with raw/model files, test RPO/RTO, or verify every retained file checksum. Earlier status explicitly records unverifiable raw samples and unavailable datasets. | Run an authorized isolated restore and manifest verification; retain missing-source findings rather than filling them with invented bytes. |
| R-06 | High consequence · Unverified scientific integrity | Static review found separate cutoffs, label-free target contracts, artifact checksum checks, and same-kickoff batching. The audit did not reproduce every fitted artifact, backtest, calibration, SQL historical reconstruction, or Rust parity run. | Preserve frozen experiments; schedule permitted reproduction/invariant checks against isolated, approved inputs. A unit test's presence is not proof of live integrity. |
| R-07 | Medium · Unverified capacity/security | Local loopback admin checks and bounded HTTP deadlines exist; no remote deployment, adversarial security assessment, dependency vulnerability scan, provider flood, or sustained load test was performed. `/version` only returns `dev`. | Establish deployed build identity and supported trust boundary; test capacity and security in an isolated environment without consuming provider quotas. |
| R-08 | Medium · Unverified accessibility coverage | Four initial route states passed the executed axe scan, but expanded matrix failed. VoiceOver/Safari, zoom/text spacing, forced colors, reduced motion, full keyboard journeys and every responsive state remain unchecked. | Complete manual accessibility verification after MF26-18/19 and retest representative loading/error/populated states. |

## 5. Verification record and reproducible evidence

### Executed checks

| Check | Actual result |
| --- | --- |
| Git startup | Clean worktree; branch `ft/fix-context-refresh-polling`; audited SHA recorded above. Dedicated audit branch created; no commits rewritten. |
| Local API health/version/readiness | `/healthz` 200; `/version` `{"version":"dev"}`; `/readyz` 200. Dependency readiness does not establish product-report availability. |
| Competition/fixture APIs | `/v1/competitions` 200, about 0.144s; `/v1/fixtures?date=2026-10-30&timezone=Africa%2FLagos` 200, about 0.111s. These are single local observations, not latency percentiles. |
| Performance | `/v1/performance?page=1&page_size=20` 503 in 0.457s. Browser displayed error. |
| Context | `/v1/fixtures/00a35317-e03c-584a-a78f-84559c1469b9/context` 503 in about 0.024s. Representative expanded forecast fixture also showed pending form and unavailable H2H/statistics. |
| External APIs | Date-scoped predictions and source summaries returned 200, about 0.005s and 0.047s respectively. A successful response does not validate metric meaning. |
| Browser routes | `/`, `/performance`, `/predictions`, `/admin/data-sync` rendered, with no captured page exceptions. Initial-state axe scans returned zero violations on those observed states. |
| Expanded fixture | All nine tabs visited for MC Oran–Olympique Akbou. Forecast/markets/history displayed; context failed; research/simulation restrictions were explicit. ArrowRight from Overview selected Markets. |
| Mobile/reflow | At 320px, Fixtures and Predictions had document width 320px, without whole-document horizontal overflow. Predictions had zero visible nav links. This does not prove all controls are usable at all zoom levels. |
| Matrix | Axe found missing required table children and four contrast failures; bounding rectangles confirmed shifted columns. |
| Parser reproductions | Wrong-day R2Bet and substring-day 1960Tips examples both incorrectly emitted one row assigned to requested date. No network. |
| External matching sample | Existing read-only `_match_fixture` called for 20 latest unmatched rows: all 20 remained unmatched. No persistence called. |
| Stored 1X2 values | 11,332 forecast rows checked: zero sums deviated from 1 by more than `1e-8`. This is an audit sanity check, not a new model acceptance threshold. |
| Forecast timing sanity | Zero product forecasts had `created_at >=` their currently stored fixture kickoff. This does not prove historical kickoff revisions or all training eligibility. |
| Score-matrix sample | 100 rows ordered by forecast ID, using serving's documented legacy-version mapping: zero invalid/non-unit distributions at `1e-8`; maximum sum error `1.1102230246251565e-16`. Not a full joint-market or reproduction proof. |
| Model/runtime data | 530 legacy and 10,802 rolling10-v2 product forecasts, all `MVP_OWNER_AUTHORIZED`; 274,001 currently eligible history rows in the sampled view. Counts do not imply model-quality acceptance. |
| Database activity | Sample showed short active transactions and idle client connections, not sustained blocking. Active sync leases were current at that later observation; six historical work leases were expired. |
| Delivery verification | `git diff --check` and final file-scope review are the report-delivery checks; no claim that full code suites ran. |

### Read-only SQL reproductions

Run against an approved connection with `default_transaction_read_only=on` and a statement timeout. These queries inspect state; they do not repair it. Counts will change while workers are running.

```sql
-- Missing report kinds and report freshness.
SELECT report_kind, horizon, count(*), max(registered_at)
FROM football.product_read_reports GROUP BY 1, 2;

-- Context backlog.
SELECT count(*) AS total,
       count(*) FILTER (WHERE generation > completed_generation) AS pending,
       min(requested_at) FILTER (WHERE generation > completed_generation) AS oldest
FROM football.product_context_report_refresh_work;

-- First-result accuracy disagreeing with the latest result revision.
SELECT first_result.correct, latest.settlement_state, count(*)
FROM football.external_prediction_results first_result
JOIN LATERAL (
    SELECT settlement_state
    FROM football.external_prediction_result_revisions revision
    WHERE revision.prediction_id = first_result.prediction_id
    ORDER BY settled_at DESC, result_revision_id DESC LIMIT 1
) latest ON true
WHERE first_result.correct IS DISTINCT FROM CASE
    WHEN latest.settlement_state = 'WON' THEN true
    WHEN latest.settlement_state = 'LOST' THEN false
END
GROUP BY 1, 2;

-- Expired work, without trying to reclaim it.
SELECT work_type, count(*), min(lease_until), max(lease_until)
FROM football.work_items
WHERE state = 'RUNNING' AND lease_until < now()
GROUP BY 1;
```

### Offline parser reproduction

The following was executed with the installed repository Python environment and `PYTHONDONTWRITEBYTECODE=1`. It creates no files and makes no provider requests.

```python
from datetime import date
from football.product.external_prediction_sources import parse_r2bet, parse_1960tips

r2 = '''<section><h2>Best Picks</h2><p>29th, Thu Oct 2026</p>
<article><p>Premier League</p><p>Home</p><p>Away</p>
<p>Odds: 1.2</p><p>Pick: 1</p></article></section>'''
rows = parse_r2bet(r2, date(2026, 10, 30), "https://r2bet.com/test")
print(len(rows), rows[0].prediction_date)  # Observed: 1, 2026-10-30

tips = '''<h1>Predictions 11 Oct 2026</h1><div class="table-row">
<span class="tb-league">L</span><span class="tb-match">H vs A</span>
<span class="tb-tip">1</span></div>'''
rows = parse_1960tips(tips, date(2026, 10, 1), "https://www.1960tips.com/test")
print(len(rows), rows[0].prediction_date)  # Observed: 1, 2026-10-01
```

## 6. Prioritized remediation plan and execution order

This is a proposed plan for owner authorization, not permission to execute fixes, change scientific policy, or mutate retained data. Combine related changes where that preserves a reviewable scope; avoid treating every finding as a separate new subsystem.

| Order | Work package / findings | Impact and dependency | Effort | Completion evidence |
| --- | --- | --- | --- | --- |
| 1 | Restore report lifecycle: MF26-01/02/03; inspect R-02 | Restores Performance, form/H2H/statistics, and external agreement. Diagnose bulk-lane contention before choosing scheduling changes. | L | Normal workers produce current reports for a representative live date and all analytics horizons; bounded backlog and correction/retry tests; API/browser checks |
| 2 | Correct source-metric truth: MF26-06/07/09/11 | Prevents misleading accuracy and wrong-date imports. Policy decision needed for prospective versus retrospective source metrics. Independent of model changes. | M–L | Revision-based summaries match rows; exact-date parser cases; honest partial status; explicit timing denominators |
| 3 | Make matching and settlement recoverable: MF26-08/10/12 | Requires approved append-only mapping correction and resolved identities; does not justify admitting ambiguous sources. | L | Import-before-fixture and late-import scenarios; bounded concurrent settlement; interruption and correction convergence |
| 4 | Stabilize operations: MF26-13/14/15; KB-01/02; R-01/03/04 | Distinguishes provider outage, held evidence and orchestration failure; avoids repeating unproductive calls. Coordinate with report scheduling. | M–L plus external waiting | Scoped failure disposition, lease recovery proof, independent daily stages, actionable backlog/failure monitoring |
| 5 | Repair misleading and inaccessible UI: MF26-04/05/17–25 | Several S-sized fixes can proceed independently once API state meanings are agreed. MF26-05 still needs native evidence investigation. | M–L combined | Keyboard/mobile flows, matrix alignment/contrast, timezone cases, honest health/empty/error states, successful-context and idle-admin refresh |
| 6 | Bound serving growth: MF26-16 | Follow settled report/metric contracts; pagination must not change aggregate denominators. | M | Bounded fixture/archive fixtures in an isolated load scenario, cancellation, stable pagination/filter results |
| 7 | Repair guidance and close evidence gaps: MF26-26; R-05–08 | Enables reproducible operation and trustworthy handoff. No automatic research restart or production cutover. | S for links; separate M–L recovery/security exercises | Valid documentation paths, deployed SHA, restore evidence, manual accessibility and approved integrity/capacity checks |

### Required end-to-end acceptance before further feature development

1. Select a bounded representative set containing a current scheduled match, a completed regulation-time match, a postponed match, a corrected result, a provisional/unmatched fixture, and missing-provider-resource cases. Use a disposable database and existing retained evidence where possible.
2. Trace authorized fixture/history ingestion through verified identities, forecast eligibility, immutable forecast publication, UI retrieval, result update, settlement, report generation, and Performance/source display. Record IDs and exact report/artifact hashes. Do not use held or protected outcomes to tune models.
3. Demonstrate normal scheduling and recovery, not just direct CLI invocation of each missing stage. Prove current contexts are not starved by bootstrap history and that independent source failures do not erase successful work.
4. Reconcile source summary counts against current settlement revisions. Separate retrospective collection from prospective evidence. Verify comparisons and source consensus use their declared identity/market/revision rules.
5. Run applicable repository gates after code fixes, following the Makefile graph and a single final comprehensive validation where required. Add meaningful orchestration/contract cases for the failures above; mocked component success alone is insufficient.
6. Recheck four routes, all affected tabs, keyboard/mobile flows, loading/error/stale states, and operator job transitions. Complete the manual accessibility coverage that was not performed here.
7. Obtain a current backup/restore and operational-monitoring disposition, record remaining owner/provider blockers explicitly, and hand control back to the owner. Report workflow acceptance separately from scientific phase completion.

## 7. Audit disposition

**Report complete; remediation not performed.** The audit covers all major application subsystems and every implemented page/fixture tab, with explicit sampling and verification limits. It cannot guarantee that every possible defect has been found. No scientific gate, architecture map, provider qualification, or operational acceptance is declared complete by this report.

Only `docs/CODEBASE_AUDIT_REPORT.md` is delivered. Existing source, tests, `.env`, model artifacts, project status, and operational records are preserved. Commit, push, and PR delivery are intentionally omitted for this report-only audit.
