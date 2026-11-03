# Forecast readiness investigation and remediation plan

Investigation date: **3 November 2026**. Delivery scope: **research and documentation only**.
Source checkout: `fd606e3` on `ft/data-status-remediation`, after merging `main`
`e4ea615c`. No production fix, migration, identity admission, recovery mutation,
model fit, evaluation, promotion, cutover or deployment is part of this task.

## Investigation checkpoints

| Phase | Scope | Result |
| --- | --- | --- |
| 1 | Current requirements, main synchronization, operating baseline and prior-target accounting | PASS_WITH_WARNINGS; baseline collected, detailed cause investigation continues |
| 2 | Source/code traces, identity, coverage, parity and external research | IN PROGRESS |
| 3 | Actionable issue specifications, dependencies, acceptance review and delivery | PENDING |

## 1. Executive summary

The earlier **153** verified upcoming blockers are not the current backlog.
At the fresh baseline, all **29 Coventry**, **20 Málaga** and **13 Armenian**
targets have `FORECAST_AVAILABLE`; **91** original targets remain blocked.
These recoveries preceded this investigation. Do not count them as potential
new gains or design another identity merge to recover them again.

The fresh scheduled-future population contains **6,320** fixture records:
**2,365** verified available, **196** verified blocked (148 insufficient history,
48 source-incomplete), and **3,759** provisional source-incomplete records.
The 196 include the 91 remaining original targets and 105 additional targets.
The universe moves with time, provider discovery and background workers.
Stored availability is a diagnostic label; later sections separately test identity
and history prerequisites. Provisional records and multiple representations must
not be added to a promise of unique forecast gains.

There are **226** competitions marked available and **301,307** eligible
historical results at the baseline cutoff. The five historical parity jobs
completed execution but each produced a **BLOCKED** diagnostic report. They
repeat the shared Architecture V2 comparison requirements; they are not five
independent fixture-reconciliation failures.

## 2. Operating baseline and evidence method

### Snapshot and scope

Baseline B1: `2026-11-03 14:56:39.190037 UTC` (15:56:39 Africa/Lagos), database
`football`, PostgreSQL 18.6, snapshot `17918226:17918226:`. Connections set
`default_transaction_read_only=on`; collections explicitly begin
`REPEATABLE READ READ ONLY` and roll back. Credentials stay in the local `.env`.
The [PostgreSQL transaction contract](https://www.postgresql.org/docs/18/sql-set-transaction.html)
explains the consistent snapshot and enforced write restrictions.

Private receipts and query text are under `.local/forecast-readiness-investigation/`.
They are not distributable football datasets. The tracked report will retain
exact target IDs, aggregate results and reproducible query recipes. Snapshot
identifiers are descriptive, not replayable after their transaction closes.
Collections made later are separate snapshots, not extensions of B1.

The first baseline collector successfully completed every population query, then
failed its final stage-settings query because it used `stage_order` instead of
schema column `stage`. The successful read-only results remain in `baseline.json`;
the failed query is disclosed rather than represented as a passing collection.
The stage query is corrected in the separate detailed collection. Initial
sandbox denials for Git metadata, localhost and GitHub were resolved through
reviewed access. No automatic approval rejection occurred.

| Population | B1 measurement | Interpretation |
| --- | ---: | --- |
| Competition availability | 226 available; 1,017 insufficient history; 361 source-incomplete; 54 no fixtures | 1,658 competition rows, not a market-qualification count |
| Eligible history | 301,307 | Existing eligibility function at B1 knowledge cutoff |
| Retained history | 479,460 | Includes ineligible observations; not additive with eligible history |
| Latest history decisions | 301,307 eligible; 178,151 identity-policy ineligible; 2 non-played | One latest decision per fixture |
| Context report work | 148,095 pending of 229,235 rows; zero recorded errors | Backlog, not 148,095 missing football matches |
| Performance reports | 7 pending of 3,794 | Secondary derived reporting |
| Comparison reports | 0 pending of 1,362 | No current backlog in this queue |
| Forecast refresh work | 0 pending of 8,276 | Empty queue does not prove all targets are forecastable |
| Native history scopes | 1,224 total, only 2 SUCCEEDED | Completion requires exact scope evidence |
| Parity follow-ups | 5 executed SUCCEEDED, all outcomes BLOCKED | Worker success differs from parity success |

| Provider | Retained product history | Eligible history | Eligible competitions |
| --- | ---: | ---: | ---: |
| API-Football | 58,949 | 58,077 | 318 |
| football-data.org | 5,389 | 2,646 | 8 |
| Football-Data.co.uk | 236,709 | 136,927 | 20 |
| FotMob | 87,743 | 29,813 | 75 |
| OpenFootball | 89,930 | 73,828 | 45 |
| PitchAPI | 740 | 16 | 3 |

Provider totals must be read from B1, not copied from earlier recovery receipts.
StatsBomb and retained research providers use separate representations; their
resource/event counts are not product-history counts.

### Repository and programme dependencies

[PR #179](https://github.com/sir-radar/match-forge/pull/179) is the current branch's
open delivery PR. [PR #178](https://github.com/sir-radar/match-forge/pull/178) remains
open at `463ec15a8a0720fb48e842af5a009cf140545f90`. Neither is merged or deployed by
this task. PR #178's StatsBomb recurrence prevention records database-generated
UUIDs honestly as `provider_native`; its independent relationship prerequisite
and actual legacy correction remain blocked. A five-fixture research pilot is
not operating forecast or broad V4 acceptance.

The operating migration is `202611020200`. Architecture V2 remains in progress;
cutover and retirement remain blocked. Sprint 2 remains FAIL and later scientific
work is not reopened. This is an owner-requested investigation, not a claimed
Wayfinder implementation ticket. No terminal route is mutated. See
[project status](../project-status.json), the latest sections O/P of the
[data recovery report](data-status-remediation-report.md), and the
[source acquisition register](../source-acquisition.md).

### Investigation standard

Trace source registration → parser → provider identity → admitted MatchForge
identity → fixture reconciliation → dated history decisions → eligible history
→ ten-match rolling inputs → forecast publication. Use existing SQL functions
and Python owners. A name match, source download, successful job or admitted
competition alone does not prove the rest of this chain.

Research records distinguish factual football evidence, exact native-ID evidence,
access/entitlements and scientific eligibility. Newly retrieved facts cannot be
backdated into earlier forecast inputs. This document recommends later work;
its illustrative execution phases do not authorize that work.
