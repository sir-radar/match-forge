# Pre-P03 result recovery verification, 14 November 2026

Branch `ft/pre-p03-result-recovery` (PR #231) after the recovery scheduling
rework, compared with main `14e670fbf365eaed8040de2bacd127e6600df949`. The
operating database was read in read-only transactions only. It reported
migration `202611130300`, so the recovery migration was not applied there, and
no provider requests or operating writes were made. Provider behaviour below
comes from simulated responses on disposable PostgreSQL 18.6 databases.

## Root causes and fixes

| Defect | Cause | Fix |
| --- | --- | --- |
| A manual fixture or date request selected nothing | `_due_dates()` required the date's `next_attempt_at` to have passed, and `_claim_refresh()` applied the same freshness deadline, so the background attempt's delay of up to one day suppressed operator requests | Eligibility moved to `football.product_result_recovery_state`, per fixture and provider. Operator requests ignore MatchForge's schedule. The date row is a 15-minute lease that is released on completion |
| A newly eligible fixture waited for an earlier check on its date | The shared date row held the retry deadline for every fixture on that UTC date | The date row holds no deadline. A fixture becomes due by its own state, a changed purpose or a newer exact mapping |
| Provider deadlines were stored per date | `HistoryDeferred` and API-Football `retry_after` were written to the date row | The provider clients still enforce their deadlines. The latest deadline is also recorded per fixture and gates the next pass for every request, with `deferred_until` in the summary |
| A request was reported as a recovery | `COMPLETED` described the HTTP outcome; `updated` mixed fetched and published rows | Each fixture gets a named outcome. Summaries report `recovered`, `corrected`, `verified_unchanged`, `unresolved` and `coordinated`. An unresolved operator fixture request ends `COMPLETED_UNRESOLVED`, and the Admin run fails with the outcome |
| Old backlog could monopolize runs | Dates were ordered by oldest attempt, then oldest date | Half of each run's date limit goes to the newest due dates and half to the longest-waiting dates. Backoff grows with fixture age and repeated outcome |
| Verified results were never rechecked | Correction work existed only for explicit fixture requests | Finished mapped results are rechecked 1, 7 and 28 days after kickoff, then stop |
| 93,380 unknown-basis scores were candidates | The view treated every finished `UNKNOWN` basis as unresolved | Only unknown-basis scores without qualified history are candidates |
| Census query cost | One OR predicate forced a per-row history probe and a hash join over all identity resolutions | The view is split into three index- or anti-join-friendly branches |
| API-Football retained responses were ignored | Only FotMob and PitchAPI replayed retained evidence | The newest three retained responses for the date are re-offered through the same identity proof and result owners |
| Migration version collision with PR #230 | Both PRs added version `202611130400` | The recovery migration is now `202611140100`, after PR #230's three migrations, and its sync-type list includes `EXTERNAL_PREDICTION_SETTLEMENT` |

## Recovery coverage

Measured with the new candidate predicate at about 03:25 UTC. The 1,678 figure
in the [13 November audit](pre-p03-acquisition-audit-2026-11-13.md) used a
different predicate and is not a post-remediation count.

| Population | Count |
| --- | ---: |
| Recovery candidates (after duplicate-member exclusion) | 2,650 |
| Overdue and unfinished: verified / provisional | 1,030 / 254 |
| Finished, unknown basis, no history: verified / provisional | 139 / 671 |
| Finished regulation-time score, no history (verified) | 556 |
| Verified with an exact FotMob, PitchAPI or API-Football mapping | 1,714 |
| By route: API-Football / FotMob / PitchAPI | 1,677 / 42 / 1 |
| Routed fixtures by age: under 2 days / 2–14 days / 14–90 days / over 90 days | 42 / 528 / 1,071 / 73 |
| Routed fixtures with retained final evidence that states a duration | 38 |
| Verified without an operational route (5 with football-data.org only, 6 with none) | 11 |
| Identity pending (provider-scoped, not admitted) | 925 |
| Finished unknown-basis scores with qualified history (not candidates) | 92,184 |

The routed fixtures span 87 API-Football, 17 FotMob and 1 PitchAPI kickoff
dates. Correction discovery currently covers 12,206 API-Football, 785 FotMob and
20 PitchAPI fixtures across 26, 28 and 8 dates. Recovered, qualified and
corrected counts on operating data do not exist yet: the migration and worker
have not been deployed.

The 556 regulation-time scores without history have no history decision at
all. Recovery re-offers them through the provider's existing result owner; if
qualification still declines, the fixture is `QUALIFICATION_FAILED` and is
rechecked weekly. Unknown-basis scores are never promoted to regulation time.

## Provider participation

| Provider | Recovery role |
| --- | --- |
| API-Football | Dated fixture request with exact native identity, season and orientation proof. Persistent daily and minute budget. Retained responses replayed first |
| FotMob, PitchAPI | Dated calendar request through the operational observation owner, after replay of retained final observations with a stated duration |
| football-data.org | League-season history only, through the MVP history fallback. No per-date route; it covers 5 of the 11 unrouted fixtures |
| OpenFootball, Football-Data.co.uk, StatsBomb Open Data, Understat | Historical archives with no recurring route. They supply most finished scores with no stated duration |
| ESPN, Flashscore, Soccerway, WhoScored, Sofascore | Retained, experimental or unregistered as described in the audit. Not used for recovery |

No further adapter integration was justified: the three recurring routes reach
every verified candidate except 11 fixtures. The 925 identity-pending fixtures
need identity admission, which is outside result acquisition.

## Query cost on the operating census

| Query | Before | After |
| --- | --- | --- |
| Candidate view (2,650 rows) | 3.14 s, about 1.0 million buffers, temporary files | 0.39–0.66 s, about 36,000 buffers |
| Automatic due selection for API-Football (13,462 rows including the first correction pass) | not measured | 0.36 s |

The new state table is keyed by fixture and provider, with an index on
provider and next check. It grows by at most one row per routed fixture and
provider. Lock contention, WAL, CPU, memory, request latency and throughput on
populated operating data were not measured; that needs the authorized rollout.

## Tests

| Check | Result |
| --- | --- |
| Recovery unit tests (`python/football/tests/test_result_recovery.py`) | 13 passed |
| Recovery integration (`tests/integration/test_result_recovery.py`, `test_operational_recovery.py`) | 13 passed |
| Same plus external settlement and history acquisition, on a trial merge with PR #230 | 67 passed |
| Full integration suite on this branch, disposable cluster without the compose services | 1,015 passed, 29 failed; the 29 are compared with main below |
| Go `go vet` and `go test ./...` | passed |
| Web unit tests | 258 passed (261 on the PR #230 trial merge) |
| `pnpm build`, `make web-lint`, `make architecture-check`, `make project-status-check` | passed; one pre-existing lint warning in `forecast-history.test.tsx` |
| Ruff, ruff format and mypy | passed |

Acceptance scenarios covered by the integration tests:

- Manual fixture and date recovery after an automatic check; an invalid fixture
  ID reports `FIXTURE_NOT_FOUND` without a request.
- A fixture reinstated on an already checked date recovers in the next run
  without repeating or rewriting the earlier fixture's check.
- Fixtures at 23:50 and 00:10 UTC use one request per UTC date.
- A provider outage on one date does not block the next date; the failed
  fixture retries after five minutes and then recovers.
- A provider retry deadline stops further requests, including an operator's,
  until it passes.
- A lease held by another worker reports `IN_PROGRESS` and no request; after
  the lease expires the work completes once and a repeat is idempotent.
- A verified result is corrected from 2–0 to 2–2 by the scheduled check, with
  both history decisions kept and the earlier one visible at an earlier cutoff.
- Retained FotMob/PitchAPI and API-Football evidence recovers a result without
  a request, keeps the original acquisition time, and replays idempotently.
- An external prediction with no internal forecast settles after recovery,
  re-settles once after a correction (`WON`, then `LOST`) and not again on retry.

Not exercised here: populated preservation and performance, real provider
traffic, and a production-shaped multi-worker load.

## PR #230 compatibility

PR #230 was an open draft at `887acb8`. A trial merge into this branch had
textual conflicts in `docs/api/openapi.yaml`, `web/lib/contracts.ts`,
`web/components/data-sync-admin.tsx` and the shared settlement test file. Each
is a union of both sync types or both tests. Under PR #230 settlement requires
a matched fixture association and a verified source date, so this branch's
settlement test now seeds both, and it passes before and after the merge. The
trial merge was not pushed. Merge PR #230 first, then rebase this branch and
apply the same resolutions.
