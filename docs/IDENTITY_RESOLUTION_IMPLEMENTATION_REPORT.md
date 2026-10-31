# Identity Resolution Center implementation

## Phase 0 baseline and implementation map

The read-only audit on `football_architecture_v2_shadow_20261016` revalidated 4,160 unresolved mappings, 108 contradictory mappings, one revoked mapping, 984 unsafe shared identity groups, 33 unavailable source resources, and three unavailable dataset files. There are 59,903 provisional fixtures. The audit used existing identity qualification and both supported raw-file verification owners; the frozen 4,253 proof-availability set has a different denominator and is not relabeled as the current mapping backlog. See `docs/evidence/identity-resolution-baseline-2026-10-31.json`.

Reuse:

- Existing crosswalks, alias normalization, admissions and effective-dated team corrections own identity. Review candidates never authorize admission.
- Existing operational mapping qualification and fixture reconciliation own fixture decisions and retained observations.
- Existing immutable file store and integrity verifier own source/dataset verification and publication.
- Existing Work Orchestrator owns downstream leases, fencing, retries and completion.
- Existing Go Admin private-local checks and owner credential protect the new routes; Python retains domain decisions.
- Existing Next.js shell, tables, form styling and resource states provide navigation and presentation.

Gaps: unified case discovery, bounded review, evidence-version previews, authenticated decision endpoints, review audit history, retained-file recovery controls, actionable parity views, and isolated migration preparation. One additive append-only review log records workflow state without duplicating domain decisions.

Phase order: (1) identity diagnostics; (2) read-only queue; (3) protected preview/apply; (4) independent bounded batches; (5) qualified fixture/recovery integration; (6) source recovery/disposition; (7) existing evidence-backed parity; (8) isolated controls/rehearsal; (9) retirement preparation; (10) final verification and delivery. Each checkpoint is recorded in local ignored `CURRENT_TASK_STATUS.md`.

Production Phase 35 cutover and Phase 36 retirement remain blocked by missing identity proof, authentic source bytes/lineage, complete production-scope parity, and explicit acceptance. The 59 generic Elo conflicts and 327 insufficient-history targets remain explicit limitations. No provider requests, authoritative evaluation, model fitting or promotion is authorized by the review interface.

## Phase 1 — Identity diagnostics

`resolution_identity.py` reuses existing trust and effective-dated identity owners.
It reports the five requested review statuses, retains explicit contradictions and
revocations, discovers native-ID and exact-alias candidates without admitting them,
and returns retained correction contexts, bounded fixture impacts and evidence
versions. No identity table, admission rule, model input or historical query changed.

Verification: seven focused unit tests and five PostgreSQL acceptance tests passed.
The database tests migrate disposable databases only through `202610310300`, before
any Resolution Center migration. They prove read-only operation, stable evidence
hashes, explicit crosswalk discovery, protected alias-only candidates, missing-byte
blocking, and prospective correction/revocation without changing earlier cutoffs.
The exact staged commit was also tested separately from later-phase drafts:

```sh
uv run --locked --no-sync pytest tests/test_resolution_identity.py tests/integration/test_resolution_identity_database.py
```

Result: 12 passed. Ruff, format checks, mypy, architecture checks and
`make project-status-check` passed for this phase.

Later-phase drafts were excluded from the Phase 1 commit.


## Phase 2 — Read-only Admin Resolution Center

The existing Admin shell now links to Identity Review, Fixture Review, Missing
Data, Migration Parity, Cutover Controls and Resolution History. Filtered counts,
pages, bounded groups, stable case keys, source details, candidate hints, reason
codes and dependent fixtures use existing tables. No migration or write endpoint
was introduced. Current admission records in queue counts are labeled separately
from independently requalified proof in case details.

The Python bridge uses read-only repeatable-read transactions. Go retains the
private-local access checks, cancels the child process group with the request,
bounds output and disables response caching. The client validates response shapes,
aborts superseded requests, preserves same-query rows on refresh failure and
exposes retry. Native tables, controls and disclosures support keyboard review.

A read-only shadow audit returned 17,594 identity rows, 132,776 fixture/native
cases, 749,680 recorded/current history rows, 55 unavailable source/dataset cases,
eight blocked parity domains and 13 blocked migration stages. The 55 cases are 33
resources and 22 dataset versions with unavailable or invalid registered files;
22 versions must not be confused with the baseline's three missing physical file
rows. No records were repaired or admitted. Bulk file checks reduced the missing
inventory scan from 50.44 seconds to 7.07 seconds without weakening full dataset
integrity checks or publication gates.

Verification: 26 focused PostgreSQL/integrity tests passed, and the separate real
Go/Python/browser journey passed after correcting its cell selector. The browser
journey inspected a retained identity, original history, missing source and all
migration blockers in a disposable pre-Resolution-Center database, with no writes.
Desktop/mobile synthetic browser journeys passed, including axe, focus return,
320px reflow and keyboard table scrolling. All 101 existing/new frontend tests,
pinned Next.js 16.4.1 production build, Ruff, mypy (438 files), Go tests and Go lint
passed before the final contract-drift assertion; the final focused checks cover
that assertion. Manual VoiceOver and full WCAG conformance were not evaluated.

Production cutover and retirement remain blocked.


## Phase 3 — Interactive identity decisions

The Admin workflow now supports independently qualified admission, retained team
correction, reviewed fixture mapping, prospective quarantine, exact-candidate
rejection, evidence requests, blocked/deferred review and revalidation. The
existing domain owners retain admission authority. One append-only workflow log
records approved inputs, actor fingerprint, exact preview, result and pending
work; original identity/fixture decisions are not rewritten.

Preview is read-only. Apply requires the private-local checks plus the configured
owner credential, explicit approval and a request UUID. The backend prepares
source bytes before ordered locks, rechecks current evidence and review versions
under those locks, and atomically records the domain result and audit event.
Repeated clicks return the same event; changed inputs cannot reuse a UUID.

Verification: six disposable PostgreSQL tests passed, covering correction/retry,
stale mappings, alias-only rejection, prospective quarantine, concurrent repeated
approval and tampered bytes. A separate real browser journey passed through
Next.js, Go and Python: it selected retained correction evidence, reviewed a
qualified preview, supplied owner approval and found the correction in history.
The original published forecast remained present. Eight initial focused frontend
tests and three final decision-form tests passed; focused Go tests, Go lint,
Ruff/format, mypy (439 files), architecture/status checks, migration validation
and the pinned production build passed. Fallow removed one unused task export;
its remaining client fetch candidate has a fixed build-time origin and encoded
query values. No scanner suppression or dependency was added.

Downstream fixture reconciliation is explicitly pending until Phase 5 integrates
the scoped workflow. No live identity decisions, cutover, retirement, evaluation
or model fitting were executed by these acceptance tests.


## Phase 4 — Bounded batch adjudication

Admin selection now spans pages and is capped at 20 cases, one normal Admin
page, to bound synchronous proof gathering and response size. A shared retained
verifier gathers proof for batch previews. Each approval still has its own exact
preview hash, request UUID, backend qualification, transaction and audit event.
Overlapping mapping targets, canonical identities or fixture effects require
separate reviews. Partial failures leave independently committed cases intact;
retries return original per-case outcomes. Candidate rejection binds the selected
retained candidate rather than rejecting a name or score.

The queue groups current cases by provider, kind, country, recorded evidence
status/reason and known canonical competition/season memberships. Unknown
memberships stay empty; one case may occur in several season groups. Group counts
do not replace the distinct case denominator. The read-only shadow inventory
remained 17,594 identity cases; the expanded grouping query completed in 5.6 seconds.
The frozen 4,253 proof set remains separate and no live backlog was admitted.

Verification: five focused batch tests passed (one bound/duplicate-input test and
four PostgreSQL tests). They cover read-only proof gathering, shared-fixture
conflicts, partial stale failures, repeat convergence and competition/season
cohorts. A real owner-approved two-case browser review passed and recorded two
independent audit events without changing the published forecast. Frontend tests
cover cross-page selection, exact candidate binding and per-case failures. Go
checks cover owner authorization and batch bounds. Ruff/format, mypy (440 files),
Go tests/lint, frontend lint/types, pinned production build and architecture/status
checks passed. Shared form lifecycle and browser-backend helpers removed newly
introduced duplication; no new dependency or admission threshold was added.


## Phase 5 — Scoped fixture and downstream recovery

Approved identity changes and revalidation now freeze affected fixture and retained
observation IDs with their hashes in the approval transaction. Shared
`CANONICAL_RECONCILIATION` work processes at most 32 targets per page. Each target
has an immutable, fenced checkpoint; a continuation publishes with the page receipt
and depends on its parent. Existing claim ordering, leases, retries and cancellation
remain authoritative. The Go scheduler resumes committed work after restart, drains
bounded pages fairly and cancels/waits during shutdown.

The existing fixture owner now accepts a scope. It retains every competing match
in the same competition/kickoff neighborhood before checking uniqueness; more than
100 neighbors requires separate review. The unknown-season owner shares one rule
between its original API and a scoped overload. All candidates in the selected
native-ID family remain visible until uniqueness is measured. A regression first
proved an unsafe scoped merge, then verified that both global and scoped calls
block two competing known-season candidates.

Retained observation replay reuses the existing normalization and reconciliation
owner. Source bytes are checked before coordination locks and rechecked through a
sealed verifier under the lease. Missing proof blocks new merges. Original provider
rows, source clocks, canonical IDs and published forecasts remain retained. Requests
for context, eligible future forecasts, performance and external settlement use the
existing generation queues. A checked fixture is not relabeled as resolved. Current
case details distinguish recovery receipts from actual pending downstream queues.

Verification: 13 recovery acceptance tests passed, plus a focused current-progress
check; 72 fixture/identity/replay/approval regressions passed in a fresh disposable
database. Tests cover 65 frozen fixtures over three pages, partial checkpoint retry,
lease expiry, input-hash mismatch, pre-lock byte verification, missing proof,
retained observation clocks, restart execution and scoped/global ambiguity parity.
The real single and batch approval browser journeys passed. Go tests/lint,
Ruff/format, mypy (441 files), architecture/status checks, migration validation,
frontend tests/types/lint and the pinned production build passed. Final source
review also corrected the shared form hook; its earlier Phase 4 lint-pass statement
was inaccurate. No lint rule or worker-registration gate was bypassed.

No live identity changes, recovery, evaluation, cutover or retirement were executed.

## Phase 6 — Missing-data recovery and dispositions

Missing-data details expose original registrations, manifests, checksums, retained
locations, dependent datasets, file recovery attempts and full integrity results.
Recovery freezes the exact registered target and authentic retained input in an
approved `PROVIDER_ACQUISITION` job. Files publish exclusively before a fenced
receipt; retries reconcile authentic bytes published before a database interruption.
Native StatsBomb and Football-Data-UK layouts, source wrapper manifests, legacy raw
files, dataset manifests and Parquet files retain their original paths and hashes.
A missing wrapper must be recovered before its raw path can be discovered.

Admin supports original-evidence verification, retained-file recovery, explicit
case exclusions, evidence requests, deferral and blocked dispositions. All require
an exact preview, owner credential, reason and append-only approval. Exclusions
retain unavailable counts and do not waive complete-data parity. File verification
is separate from full dataset verification; only a passing case requests scoped
canonical recovery. Approval wakes the existing recovery scheduler immediately.
Dependent parity remains explicitly due for the Phase 7 verifier.

Verification: 20 disposable-database recovery/disposition tests, 11 contract tests,
24 identity/batch/recovery regressions, 107 frontend tests, and two real Admin
browser journeys passed. Coverage includes changed inputs, traversal, symlinks,
wrong checksums, conflicting existing bytes, source manifests, native and dataset
paths, concurrent claims, cancellation fencing, interrupted publication and retries.
Go tests/lint, Ruff/format, mypy (442 files), migration validation, architecture
checks, frontend lint/types and production build passed. Browser checks include axe;
formal screen-reader certification was not performed.

Gate: PASS_WITH_WARNINGS. New-version reconstruction remains operationally blocked
without independently approved source-backed build inputs, complete lineage and
an eligible trusted change set. The existing dataset publisher remains the owner;
this workflow grants no replacement-version or historical-cutoff exception. No live
recovery, exclusion, identity decision, model fit, evaluation or migration occurred.

## Phase 7 — Recorded parity rechecks

Admin can preview and approve a parity recheck, inspect current diagnostics and
review prior verification results. Shared projection work retains immutable inputs,
leases, fencing and checksum-bound reports. Verification reads source availability,
full dataset integrity, identity audit, canonical decisions and fixture counts in
a repeatable-read read-only snapshot. It rechecks retained comparison artifacts,
original arithmetic hashes and registered file sizes. Missing retained artifacts
block verification; changed evidence fails it. No model fit or evaluation is run.

The dashboard covers all 11 required check groups, including historical coverage,
performance/external reports, artifacts and model routing. It distinguishes exact
bounded comparisons from complete production scopes, retains the 59 Elo conflicts
and 327 insufficient-history targets, and requires every mandatory check before
full PASS. Historical results retain expected/actual results, scopes, source hashes,
verification time, operator/reason and report checksum. Database/evidence bindings
prevent a copied or outdated report from claiming current readiness. Missing-data
dispositions and completed scoped recovery request dependent parity rechecks;
a successful worker job does not imply a passing migration gate.

Verification: 44 parity/recovery checks passed, followed by final focused gate,
receipt and copied-database checks. The real Admin parity browser journey passed
with axe and durable blocked-result inspection. Frontend 107 tests, Go tests/lint,
Ruff/format, mypy (443 files), migration validation, architecture checks and pinned
production build passed. Full production-scope old/new comparisons remain BLOCKED
or NOT_RUN where the required evidence does not exist. Phase35/36 remain blocked;
no live recovery, exception, cutover, evaluation or fitting was executed.

## Phase 8 — Gated controls and real projection rollback

All 13 stages expose versioned configuration, dependencies, approval/execution
history, rollback capability and actual binding gaps. Production advance is blocked.
Twelve stages still have explicit shadow operations without qualified production
replacements; their controls reject switches and rehearsals rather than presenting
unimplemented routes as ready. The existing read-model backend supports a concrete
isolated rehearsal. This is controlled preparation, not complete Phase35 routing.

The stage8 worker binds the approved configuration generation, database and exact
fixture-projection hash. It refreshes the real materialized view, selects its leased
V2 route and compares exact rows before rolling back. It verifies restored cache
and fixture hashes before publishing the immutable receipt. Failed refreshes and
lease loss retain the previous route/cache. Revocation selects legacy automatically;
an approved rollback can clear stale metadata. Go fixture serving consumes the closed
SQL route and rejects a revoked V2 response before returning it.

Verification: 11 database scenarios passed across focused runs, including all13
advance refusals, real projection equality, database-error rollback, stale config,
stale fixtures, lease fencing, revocation, cross-stage audit rejection and explicit
approval. Fourteen gate tests passed. The real Admin rehearsal journey passed with
axe. A real Go fixture request exercised the leased V2 projection and returned an
identical legacy response after revocation, preserving source/history/artifacts.
Frontend107 tests, Go tests/lint, Ruff/format, mypy444, migration/architecture checks,
frontend lint/types/build and Fallow passed. The existing unrelated unused Playwright
configuration and estimated-coverage advice remain documented.

Gate: PASS_WITH_WARNINGS for verified controls and isolated preparation. Full
production routing and complete per-stage production rehearsals remain BLOCKED
until source/identity/parity gaps, qualified runtime bindings and independent owner
acceptance are supplied. No production switch or scheduler retirement was executed.

## Phase 9 — Conditional retirement preparation

Stage13 details expose current operator/history/provider-scope queues, forecast
generations, shared leases, expired claims, blocked work and unfinished dependencies.
Current owner/adaptor source hashes are recorded; deployed binaries and remaining
production readers are explicitly unverified. Unbound pre-migration in-flight rows
retain their compatibility path. A generation awaiting registration on claim is not
labeled an orphan. The same inventory joins durable parity verification history.
No scheduler, queue record, compatibility path or legacy code was retired.

Verification:22 isolated checks passed, covering3 new inventory/upgrade tests,
14 existing domain-owner regressions and5 parity regressions. They verify read-only
snapshots, preservation of active shared ownership, cancellation/publication fences,
pre-adapter in-flight compatibility and unchanged source/history/artifacts. Ruff,
format, mypy445, architecture and project-status checks passed.

Validation incident: the first regression command incorrectly pointed
TEST_DATABASE_URL at the configured local database. Two older tests used that URL
directly. Their synthetic fixtures were cleaned up; two canceled synthetic work
records remain as operational evidence. The failed test's forecast transaction
rolled back before commit. Read-only timing and code audit distinguishes the32
committed forecasts from separate concurrent background work; no genuine records
were removed or rewritten. Both tests now use the existing disposable database
fixture, with every assertion preserved. The successful rerun additionally isolated
both DATABASE_URL and TEST_DATABASE_URL and used a temporary data root. Raw audit
records are retained locally in .local/phase9-validation-audit*.json.

Gate: PASS_WITH_WARNINGS for isolated preparation. Live retirement remains BLOCKED
by incomplete Phase35, unverified deployed consumers and missing stabilization/
rollback acceptance. Queue counts and repository source do not establish those gates.


## Phase 10 — Final verification and delivery

The Resolution Center implementation and isolated preparation are verified with
warnings. Production Phase 35 cutover and Phase 36 retirement remain BLOCKED. No live
identity adjudication or recovery was performed to reduce the baseline counts.
All phases have separate commits; the final phase includes integration registration,
two repaired browser assertions, this report and the final read-only metrics.

The final snapshot used the same frozen shadow database in a read-only repeatable
transaction. Exact inputs and results are retained in
`docs/evidence/identity-resolution-final-2026-10-31.json`, bound to the baseline hash,
code revision and dependency lock. Counts are unchanged:

| Metric | Baseline | Final |
| --- | ---: | ---: |
| Unresolved mappings | 4,160 | 4,160 |
| Contradictory mappings | 108 | 108 |
| Revoked mappings | 1 | 1 |
| Currently admitted mappings | 13,325 | 13,325 |
| Unsafe shared identity groups | 984 | 984 |
| Provisional fixtures | 59,903 | 59,903 |
| Verified fixtures | 149,844 | 149,844 |
| Missing original resource payloads | 33 | 33 |
| Missing physical dataset file rows | 3 | 3 |
| Dataset versions with unavailable/invalid registered files | 22 | 22 |

The 22-version diagnostic was first measured in Phase 2. It is a different denominator
from three physical file rows. Missing-data cases remain 55 (33 resources plus 22
versions). The frozen 4,253 proof set is distinct from current classifications. The
59 Elo conflicts and 327 insufficient-history targets remain unresolved; no exception
was approved. A worker success or isolated route comparison cannot waive these gates.

Verification completed across the original aggregate and focused repairs:

- `env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATA_ROOT make check integration web-e2e`
  ran once. All `make check` dependencies passed: Ruff/format, mypy (445 files), Go lint/tests,
  Rust Clippy, 1,758 Python tests (seven third-party NumPy deprecation warnings),
  16 Rust tests, architecture/status validation, packaging/build, 107 frontend tests,
  frontend lint/types and the pinned Next.js 16.4.1 production build.
- Fresh migrations through 202610310800 and repeated migration-up passed. Storage
  integration executed 833 cases: 831 passed; two browser assertions failed. One still
  expected eight parity groups after Phase 7 introduced 11; the other selected a hidden
  diagnostics label instead of the opened verification history. Assertions now check
  the exact 11 groups and the visible history result. Both affected real Go/Python/
  Admin journeys passed on rerun (2 passed, 44.91s) in a disposable migrated database.
  Frontend lint/types passed after these test-only changes.
- The initial aggregate exited 2 at those failures and did not reach its remaining
  commands. `./scripts/integration.sh` then passed independently with disposable
  PostgreSQL 18.6, Redis 8.10 and real Go API checks. `pnpm test:e2e` in `web` passed
  36 desktop/mobile tests in 46.9s. Its 24 conditional real-backend cases were skipped
  by that runner; those journeys use the disposable storage integration harness.
  Successful core/build/storage tests were not needlessly repeated.
- The storage runner now sets both database variables to its disposable database,
  uses its own temporary data root and includes all Phases 6–9 acceptance modules.
  Existing concurrency, forecast, history, migration and leakage assertions remain
  intact. Final schema review confirmed that composite foreign keys already forbid
  cross-snapshot dataset inputs; no speculative recovery change was retained.
- Final staged-diff review, project-status validation, shell syntax, diff checks and
  Fallow analysis are recorded in the local Phase 10 verification evidence. Previous
  phase records retain focused failure, retry, authorization and cancellation tests.
  Automated axe, keyboard, mobile, reduced-motion and forced-colors checks passed;
  manual VoiceOver and full WCAG certification remain unverified.

Raw logs are local: `.local/phase10-full-check.log`,
`.local/phase10-fixed-browser-checks.log`, `.local/phase10-api-integration.log`,
`.local/phase10-web-e2e.log` and `.local/phase10-fallow-*.json`. The initial failure
log is preserved. The Phase 9 configured-database isolation incident remains recorded
above: two terminal synthetic work rows remain; no test forecast persisted. The
final frozen-shadow audit made zero writes. No authoritative evaluation, fitted
artifact, promotion, live exclusion, cutover or retirement was performed.

Remaining operational prerequisites:

- Independently qualified identity evidence and authentic missing source/dataset
  bytes, or explicit scoped dispositions that do not claim full-data parity.
- Complete production old/new comparisons and resolution/disposition of 59/327
  retained model/history discrepancies.
- Qualified production runtime bindings and per-stage rollback evidence for the 12
  currently unbound stages; only stage 8 has an isolated concrete serving rehearsal.
- Independent acceptance of deployed consumers, operational ownership, rollback and
  stabilization evidence, followed by explicit owner approval for Phase 35/36.

Gate: PASS_WITH_WARNINGS for authorized tooling and isolated preparation. Operational
readiness: BLOCKED. No production migration or legacy removal is implied by delivery.
