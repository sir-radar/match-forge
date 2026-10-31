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

Later phases remain in progress; their drafts are excluded from the Phase 1 commit.


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
