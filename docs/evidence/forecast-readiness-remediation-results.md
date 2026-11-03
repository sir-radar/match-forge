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
| FR-002 | NOT_STARTED | Native-target relationship proof and unchanged previews |
| FR-003 | NOT_STARTED | Exact retained-history failed predicates |
| FR-004 | NOT_STARTED | Authentic missing team/season slices |
| FR-005 | NOT_STARTED | Scottish historical namespace relationships |
| FR-006 | VERIFIED | Batched context invalidation; operating rollout remains pending |
| FR-007 | NOT_STARTED | Rolling occurrence compatibility and 730 conflict dispositions |
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
