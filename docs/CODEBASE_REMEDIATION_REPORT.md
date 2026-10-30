# MatchForge codebase remediation

Status: IN PROGRESS. Started 30 October 2026 (Africa/Lagos).

Source: `docs/CODEBASE_AUDIT_REPORT.md`, audited commit `1cbc69a20a6f15a7e4f00e242a35c6d2569c3617`. Startup HEAD is identical. Branch: `ft/codebase-remediation-2026-10-30`. Implementation checkout: `/private/tmp/matchforge-remediation-20261030`; the original checkout has an active watcher and remains unchanged apart from its task branch pointer. The untracked audit report was supplied by the owner and is preserved unchanged.

## Authorization and limits

This task authorizes remediation across phases A–E. It does not advance Architecture V2 beyond phase 33, authorize cutover, reopen a terminal Wayfinder route, admit held identities, call external providers, change the champion, or access protected scientific outcomes. No active Wayfinder tool/map is available. Existing phase gates and owner decisions remain authoritative. Engineering classification: L3 (identity, immutable histories, eligibility, concurrent publication).

## Execution plan and checkpoint

1. A: repair report scheduling/invalidation and isolate failures (MF26-01–05, R-02). Test normal worker entry points, all horizons, correction, fairness and partial states.
2. B: current-revision/prospective metrics and exact source dates; append-only binding; bounded settlement triggered by imports/results; paginated reads and distinct-source consensus (MF26-06–12,16–17).
3. C: scoped acquisition/recovery health, safe retry and lease recovery, independent daily stages (MF26-13–15, R-01,03–04).
4. D: mobile navigation, matrix, clocks, scoped request states, refresh and filters (MF26-18–25 plus 04–05,16–17).
5. E: guidance paths, runtime identity, isolated restore/integrity/security/accessibility evidence, final end-to-end and repository gates (MF26-26, R-05–08, KB-01–04).

Current phase: A implemented; focused checks passed. Next: commit the verified report lifecycle changes, then begin phase B. Browser acceptance, remaining findings and final comprehensive gates remain open.

Validation: inspect the Makefile dependency graph; use focused tests during implementation; execute `make check integration` once after final code changes. Do not run provider acquisition or scientific evaluation targets. Keep verbose logs in ignored `.local/remediation/codebase-2026-10-30/`.

## Finding ledger

Intermediate states are INVESTIGATING, IMPLEMENTING and VERIFICATION_PENDING. Final dispositions are restricted to FIXED_VERIFIED, ALREADY_RESOLVED_VERIFIED, NOT_REPRODUCIBLE or BLOCKED_WITH_EVIDENCE. Unexecuted checks never count as success.

### MF26-01 — Performance report production is disconnected from normal operation

- Original severity: High.
- Status: VERIFICATION_PENDING.
- Root cause: Current source fingerprints were required by serving without scheduled Performance production.
- Changes/files/commits: Transactional invalidation for all seven horizons; bounded scheduled report production; per-league pending/failed states retain available leagues. Files: public_reports.py, cli.py, 202610300100_public_report_scheduling.sql, Go report/scheduler stores, web contracts/components and owning architecture/OpenAPI. Commit pending.
- Verification: 21 disposable PostgreSQL report cases passed, including the actual Go scheduler launching the Python worker, corrections and report retrieval; Performance mixed-state component regression passed.
- Before/after: Missing reports previously failed the entire page; available leagues now remain visible while missing scopes are pending.
- Remaining action: final browser/end-to-end acceptance and repository gates.

### MF26-02 — Context backlog prevents timely Recent Form, H2H, and team statistics

- Original severity: High.
- Status: VERIFICATION_PENDING.
- Root cause: Bootstrap FIFO ordering and the bulk lane starved relevant context.
- Changes/files/commits: Separate public-report lane; bounded capacity per kind; half context capacity reserved for old work and half for fixtures in the preceding 24 hours through the next 72 hours; retries rotate by attempt time. Files: public_reports.py, cli.py, 202610300100_public_report_scheduling.sql, Go report/scheduler stores, web contracts/components and owning architecture/OpenAPI. Commit pending.
- Verification: Disposable backlog test proves current fixture and historical work both progress in a bounded batch. Generation completion and PIT tests pass.
- Before/after: Current fixtures behind bootstrap history now receive reserved capacity; no production drain/latency measurement is claimed.
- Remaining action: final browser/end-to-end acceptance and repository gates.

### MF26-03 — External MatchForge agreement silently loses its report producer

- Original severity: High.
- Status: VERIFICATION_PENDING.
- Root cause: Comparison serving had no scheduled producer and collapsed missing reports into unsupported agreement.
- Changes/files/commits: Selection/forecast changes enqueue comparison reports. Explicit comparison_status distinguishes READY/PENDING/FAILED/UNSUPPORTED/NO_FORECAST/UNMATCHED. Files: public_reports.py, cli.py, 202610300100_public_report_scheduling.sql, Go report/scheduler stores, web contracts/components and owning architecture/OpenAPI. Commit pending.
- Verification: Actual Go scheduler launches worker and verifies comparison probability through the Go store; immutable retry and stale-source tests pass.
- Before/after: Supported matched selections now obtain comparisons through the normal scheduler.
- Remaining action: final browser/end-to-end acceptance and repository gates.

### MF26-04 — Missing score provenance is encoded as fresh

- Original severity: Medium.
- Status: VERIFICATION_PENDING.
- Root cause: The legacy boolean encoded absent freshness deadlines as false.
- Changes/files/commits: Additive freshness enum preserves UNKNOWN/FRESH/STALE through SQL, Go and frontend parsing; unknown is never labelled fresh. Files: public_reports.py, cli.py, 202610300100_public_report_scheduling.sql, Go report/scheduler stores, web contracts/components and owning architecture/OpenAPI. Commit pending.
- Verification: Three-state Go live-source regression and UI missing-source/lifecycle regression pass; final browser checks remain.
- Before/after: Unknown sources now display freshness unknown; legacy boolean remains for wire compatibility.
- Remaining action: final browser/end-to-end acceptance and repository gates.

### MF26-05 — Score/status and incident feeds can present contradictory match state

- Original severity: Medium.
- Status: VERIFICATION_PENDING.
- Root cause: Independent timed incidents may be present while lifecycle remains SCHEDULED and score provenance is absent; incorrect identity is not established.
- Changes/files/commits: Display an explicit unresolved-lifecycle warning; retain separate source clocks and missing score. No identity or result inferred. Files: public_reports.py, cli.py, 202610300100_public_report_scheduling.sql, Go report/scheduler stores, web contracts/components and owning architecture/OpenAPI. Commit pending.
- Verification: Partial-feed UI regression passes. Investigation of the named retained fixture remains open.
- Before/after: Conflicting timed incidents now have an explicit warning; native identity evidence is still required for adjudication.
- Remaining action: final browser/end-to-end acceptance and repository gates.

### MF26-06 — Source accuracy reads obsolete first settlements

- Original severity: High.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-07 — External parsers accept the wrong prediction day

- Original severity: High.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-08 — Identical reimports cannot recover an unmatched fixture binding

- Original severity: Medium.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-09 — Collection failures can be reported as successful synchronization

- Original severity: Medium.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-10 — Settlement repeatedly scans all mapped selections

- Original severity: Medium.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-11 — Source accuracy includes selections first captured after kickoff

- Original severity: Medium.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-12 — Collection does not itself settle newly imported completed fixtures

- Original severity: Medium.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-13 — Repeated unresolved recovery contaminates routine sync health

- Original severity: Medium.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-14 — Worker ownership failures and expired history claims need recovery verification

- Original severity: Medium.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-15 — Daily refresh skips independent external collection after sync failure

- Original severity: Medium.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-16 — External read endpoints do unbounded per-source comparison work

- Original severity: Medium.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-17 — External “consensus” counts records as independent sources

- Original severity: Medium.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-18 — Predictions has no mobile navigation

- Original severity: Medium.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-19 — Score matrix has incorrect alignment, table semantics, and contrast

- Original severity: Medium.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-20 — External time labels disagree with the formatter

- Original severity: Low.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-21 — Healthy feed indicators are not connected to health

- Original severity: Medium.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-22 — Production Predictions exposes simulated empty/loading controls

- Original severity: Low.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-23 — Successfully loaded context does not refresh while the fixture stays open

- Original severity: Medium.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-24 — Admin stops observing schedules when no job is active

- Original severity: Medium.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-25 — Competition rail can create contradictory filters

- Original severity: Low.
- Status: INVESTIGATING.
- Root cause: audit finding pending current-code revalidation.
- Changes/files/commits: none yet.
- Verification: not run.
- Before/after: audit behavior retained until verified.
- Remaining action: implement and demonstrate the acceptance recorded in the audit.

### MF26-26 — Agent guidance references missing supporting documents

- Original severity: Low.
- Status: FIXED_VERIFIED.
- Root cause: supporting documents moved to docs/ while guidance retained docs/engineering/ paths; the PR template path was also stale.
- Changes/files/commits: repaired AGENTS.md and docs/git-delivery.md to reference the existing documents; no duplicate guidance created. Commit pending.
- Verification: Python path validator checked all ten distinct document references in AGENTS.md; all exist. git diff --check passed.
- Before/after: required guidance reads failed; every referenced supporting document now resolves.
- Remaining blocker: none for this finding. Historical project PASS records are explicitly not current runtime certification.

## Blockers and risks

| ID | Disposition | Evidence / next action |
| --- | --- | --- |
| KB-01 | INVESTIGATING; High · Known blocker | Project status retains R3 identity/history acceptance failure: 605 original FotMob team IDs, 108 origin declarations, and 210 original competition IDs held at that recorded checkpoint. Runtime sync still reports absent season labels and explicit cross-provider evidence requirements. These historical cohort counts were not re-audited as today's totals. Next: Resume only a newly authorized, evidence-based mapping route. Resolve native scopes and disputes prospectively; preserve denied and historical decisions. |
| KB-02 | INVESTIGATING; Medium · Known blocker | API-Football season entitlements, football-data.org CL2020 access, incomplete PitchAPI proof, unsupported/cancelled scopes, and Forebet technical access restrictions are documented. Some cannot be solved in code alone. Next: Check exact entitlement/evidence under approved budgets; classify supported, deferred, denied, and terminal scopes. Do not bypass access controls or substitute another provider as proof for a provider-specific scope. |
| KB-03 | INVESTIGATING; Medium · Intentional incomplete phase | Architecture V2 phases 34–48 and cutover are not complete. Shadow registries/projections are not proof that every production consumer/worker has moved. The Performance/comparison gaps are actual existing public-workflow failures, distinct from optional future migration work. Next: Repair current public workflows within explicit authorization; do not use this audit as permission for wholesale cutover. |
| KB-04 | INVESTIGATING; High impact if ignored · Intentional governance stop | Sprint 2 failure, closed challengers, spent/protected targets, and final reevaluation integrity block remain authoritative. No new model promotion is justified by UI repair or larger raw history counts. Next: Retain champion and frozen criteria; any new scientific execution needs its own owner decision and admissible corpus. |
| R-01 | INVESTIGATING; Medium · Suspected operational cause | DNS errors on FotMob and PitchAPI transport failures occurred; recent provider jobs also succeeded. Historical invalid-season-bound failures predate a source fix already in HEAD. Next: Correlate exact timestamps, network/process logs, and deployed revision before filing duplicate parser/season defects. |
| R-02 | INVESTIGATING; Medium · Suspected batch recovery weakness | `run_public_reports` calls `_snapshot` outside `_publish`'s failure-recording block. A malformed/invalid scope can abort the selected batch before later scopes are attempted; FIFO context selection can repeatedly revisit it. No poisoned scope was demonstrated. Next: Add isolated failure-injection coverage and per-scope disposition without weakening report validation; measure starvation under a failing head item. |
| R-03 | INVESTIGATING; Medium · Unverified recovery | Six expired history leases were observed, but no reclaim/restart exercise was authorized. Existing fences are protective, not evidence of a bug by themselves. Next: Perform the disposable-database recovery acceptance in MF26-14. |
| R-04 | INVESTIGATING; Medium · Unverified deployment/monitoring | Work/domain metrics and administrative endpoints exist. Current alert delivery, automatic daily scheduling on this host, retention/rotation of accumulating `.local/sync-runs` logs, disk-pressure behavior, and operator response were not established. Next: Inventory deployed schedules, owners, metrics consumers, retention and alerts; test age/failure alarms without provider traffic. |
| R-05 | INVESTIGATING; High consequence · Unverified restore | Prior Architecture V2 backup/restore evidence exists. This audit did not reproduce restoration of today's database together with raw/model files, test RPO/RTO, or verify every retained file checksum. Earlier status explicitly records unverifiable raw samples and unavailable datasets. Next: Run an authorized isolated restore and manifest verification; retain missing-source findings rather than filling them with invented bytes. |
| R-06 | INVESTIGATING; High consequence · Unverified scientific integrity | Static review found separate cutoffs, label-free target contracts, artifact checksum checks, and same-kickoff batching. The audit did not reproduce every fitted artifact, backtest, calibration, SQL historical reconstruction, or Rust parity run. Next: Preserve frozen experiments; schedule permitted reproduction/invariant checks against isolated, approved inputs. A unit test's presence is not proof of live integrity. |
| R-07 | INVESTIGATING; Medium · Unverified capacity/security | Local loopback admin checks and bounded HTTP deadlines exist; no remote deployment, adversarial security assessment, dependency vulnerability scan, provider flood, or sustained load test was performed. `/version` only returns `dev`. Next: Establish deployed build identity and supported trust boundary; test capacity and security in an isolated environment without consuming provider quotas. |
| R-08 | INVESTIGATING; Medium · Unverified accessibility coverage | Four initial route states passed the executed axe scan, but expanded matrix failed. VoiceOver/Safari, zoom/text spacing, forced colors, reduced motion, full keyboard journeys and every responsive state remain unchecked. Next: Complete manual accessibility verification after MF26-18/19 and retest representative loading/error/populated states. |

## API states and contract verification

The existing OpenAPI specification owns wire fields. Record endpoint changes and state/contract tests here as implementation proceeds. Pending, failed, unsupported, empty and partial states must remain distinct. Immutable report/source hashes continue to select current data.

## Verification log

Phase A: 20 PostgreSQL report integration cases passed (exit 0), including all seven horizons, correction, immutable report bytes, source invalidation, snapshot failure isolation, and current/history scheduling. The actual Go-to-Python scheduled-worker case now passes after fixing a task-introduced parser registration error. Final report integration suite: 21 passed; separate public-report/CLI unit suite: 17 passed. One attempted combined unit/integration invocation failed collection because of duplicate test module basenames; the repository normally runs those suites separately, and the separate runs passed. Focused Go report/scheduler unit tests and strict mypy on public_reports.py passed. Frontend contract/Performance/fixture tests: 54 passed; expanded fixture suite exposed a changed status-label expectation, since corrected. Ten AGENTS document paths now resolve. Full final gates have not run. Prior PASS evidence in project status is historical and does not establish current runtime readiness.

## Delivery

Required: reviewable dependency-aware commits, push and PR under `docs/git-delivery.md`. No implementation commits yet. No readiness or completion claim.

### Phase A static-analysis disposition

Fallow 3.38.0 was installed only in ignored local tooling. Full root analysis: valid combined envelope, one pre-existing unused-file finding (the explicit playwright.real.config.ts CLI configuration), six moderate estimated-health findings and no unresolved imports. An exact HEAD baseline has the same six categories; live-panel complexity improved from 12 to 10. New/changed units respect the repository threshold of 10. Added partial-feed and mixed-report-state tests exercise the changed branches. No suppressions, baselines or analyzer configuration were changed. Preview proposed zero auto-fixes; none applied. Staged security scan: zero candidates and zero unresolved edge files. Fourteen changed-file dynamic-dispatch diagnostics comprise three static array includes() calls in enum validators and eleven Testing Library/Vitest response/assertion calls, all inspected directly; none conceals an application security sink. Global unresolved-callee count is a conservative JS graph limitation, not a claim about backend code. Root node_modules warning is expected for this Python/Go repository with its frontend package in web/; web dependencies are installed and imported paths resolve. Other pre-existing findings remain in scope only when a later fix touches their behavior.
