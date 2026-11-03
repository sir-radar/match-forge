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
| FR-006 | IN_PROGRESS | Populated admission profile and refresh-key equivalence |
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
