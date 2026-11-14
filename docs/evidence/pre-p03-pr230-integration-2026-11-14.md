# Pre-P03 integration with PR #230, 14 November 2026

Record of integrating `ft/pre-p03-result-recovery` (PR #231) with the merged
external prediction settlement work (PR #230), and of the checks run on the
combined code. It follows the [branch verification record](pre-p03-recovery-verification-2026-11-14.md).
Not an owner decision. Operating access was read-only; nothing was deployed.

## Integration

| Item | Value |
| --- | --- |
| PR #230 merge commit on `main` | `bdb75ab33bd4df702491083f73591ba799e7b0c6` (merged 03:12 UTC) |
| PR #231 head before integration | `4423d06cc4b3db1f538b204825c5d22b80ba6492`, 15 commits, based on `14e670f` |
| Strategy | Rebase of the 15 commits onto `bdb75ab`, then two new commits |
| Operating schema at integration | `202611130600`; PR #230's three migrations applied, no result recovery migration |

The rebase stopped three times. Each conflict was resolved as the union of both
sides and checked against the merged code, not by taking one side:

| Commit | File | Resolution |
| --- | --- | --- |
| `17a8651` | `docs/api/openapi.yaml`, `web/lib/contracts.ts` (type and parser) | Sync type lists keep `EXTERNAL_PREDICTION_SETTLEMENT` and add `RESULT_RECOVERY`. The settlement endpoint from PR #230 and the result recovery path both stay |
| `17a8651` | `web/components/data-sync-admin.tsx` | Keeps PR #230's settlement action filter and adds `recover` and `refreshHistory` from this branch; label map has both types |
| `ee08edf` | `tests/integration/test_external_prediction_recovery.py` | Both sets of tests kept |
| `708f9f1` | `web/components/data-sync-admin.tsx` | PR #230's label map plus this branch's `formatOptionalTime` |

Checks on the auto-merged files found one interaction defect. PR #230 and this
branch each added a readiness probe to `requireProviderSyncSchema` in
`go/api/internal/app/dependencies.go`. Together they exceeded the `cyclop`
limit, so `golangci-lint` failed. The probes now live in one table, with no
behaviour change.

No other duplication was found. There is one settlement owner
(`football.product.external_predictions.settle_external_predictions`), called
by the sync, operational and recovery paths. There is one sync type constraint,
redefined last by `202611140100_result_recovery` with both new types. Each Admin
endpoint, Go command mapping and scheduler loop exists once. `RESULT_RECOVERY`,
`EXTERNAL_PREDICTION_SETTLEMENT` and `HISTORY_BACKFILL` share the bulk lane and
its single-active-run index, so they never run at the same time.

## Migration

On a disposable PostgreSQL 18.6 cluster, a database was migrated to
`202611130600` (current operating schema), seeded with settlement, history and
FotMob runs, and migrated to `202611140100`.

- Existing sync run rows were identical by row hash before and after.
- Constraints on existing tables were unchanged except the sync type check,
  which gained `RESULT_RECOVERY` and kept `EXTERNAL_PREDICTION_SETTLEMENT`.
- Added: view `product_result_recovery_candidates`, table
  `product_result_recovery_state`, its primary key and its due index.
- Both new sync types are accepted. `goose down` refuses with
  `result recovery run history requires a forward repair`; version and rows stay.
- `goose validate` passes. Migration IDs are unique and ordered. The operating
  database never applied the earlier `202611130400_result_recovery` number, and
  goose keeps no checksums, so the renumbering needs no repair.

On the populated restore described below the migration took 256 ms.

## Populated rehearsal

No new copy of operating data was made. The rehearsal reused
`settlement_remediation_restore`, an isolated restore kept from the PR #230
rehearsal (verified dump `206537e9…`, cluster identifier `7707531760395534379`;
operating is `7679328148388241450`). It was at `202611130600` with no other
sessions. The later `settlement_remediation_final_restore` was left untouched.

Before and after the migration, every row of 21 tables was hashed: fixtures,
team match history, identity resolutions, provider mappings, provider
observations, source snapshots, forecasts, forecast artifacts, model
artifacts and registrations, external predictions, bindings, fixture evidence,
captures, settlement revisions and results, history decisions, result
conflicts, raw-file bindings and sync runs. All 21 were identical. The P02
[preservation hashes](../../scripts/p02/preservation.sql) were captured before
and after with the same result.

A bounded recovery pass on this restore was not run. It writes new raw
evidence under `FOOTBALL_DATA_ROOT`, and pointing that at the operating
evidence store would add files the operating database does not reference.
Copying the 11 GB store to an isolated root was refused as further duplication
of operating data. Running the pass needs an authorized isolated evidence root.

## Current population

Read-only census of the operating database at 03:35 UTC, using the view
definition in a repeatable-read transaction (0.92 s):

| Cohort | Fixtures |
| --- | ---: |
| Recovery candidates | 2,651 |
| Overdue unfinished / unqualified score / unknown score basis | 1,285 / 556 / 810 |
| Verified with an exact FotMob, PitchAPI or API-Football route | 1,715 |
| … of which retained final evidence already exists | 39 |
| Provider-scoped, awaiting identity admission | 925 |
| Verified with no recurring route (5 football-data.org only) | 11 |
| Kickoff in the last 7 days | 285 |

Verified routes: API-Football 1,678, FotMob 42, football-data.org 5, PitchAPI 1.
The oldest candidate kicked off on 9 March 2024. The baseline on the branch
record was 2,650 / 1,714 / 925 / 11 / 38. No candidate has been recovered on
operating data, because recovery is not deployed.

Next action by cohort:

- **1,715 routed:** recovery after rollout. 39 can be recovered from retained
  evidence without a request.
- **925 identity pending:** P09 identity admission. Result acquisition cannot
  resolve them without weakening P02 identity rules.
- **5 football-data.org only:** league-season history through the existing
  MVP fallback; no per-date route exists.
- **6 other unrouted:** no configured provider covers them; P09 source work.

## Capacity

Measured on the populated restore, cold cache:

| Query | Time |
| --- | --- |
| Candidate view count | 138 ms |
| Recovery census (`recovery_coverage`) | 0.37–0.68 s |
| Due selection, API-Football | 889 ms |
| Due selection, FotMob | 398 ms |

Due selection scans `product_fixtures` (306,820 rows) and
`product_team_match_history` (537,781 rows) sequentially; it reads about
45,000 buffers and runs once per provider per run.

On the restore the routed backlog is 87 API-Football UTC dates, 17 FotMob and
1 PitchAPI; one request covers one date. Correction checks over the last 28
days add one date per provider per day at each of three offsets.

Operating provider budgets, 8–14 November (read-only):

| Provider | Daily requests | Quota |
| --- | --- | --- |
| API-Football | 17–101; exhausted on 10, 11, 12 and 13 November | 100 per day |
| FotMob | 317–13,199 | none recorded |
| PitchAPI | 673–19,268 | none recorded |

API-Football quota, not the recovery interval, limits backlog progress.
Recovery uses the same persistent budget, so an exhausted day defers its
requests to the next window instead of retrying. At 8 dates per run the
87-date backlog needs about 11 runs, spread over the days with spare quota.

Recommended initial `MATCHFORGE_RESULT_RECOVERY_INTERVAL`: `30m`. The shortest
retry delay for a recent fixture is 15 minutes and a fixture becomes a
candidate 4 hours after kickoff, so 30 minutes adds at most 30 minutes to a
same-day result. Selection costs about 2 s of database time per run across
three providers, about 1.6 minutes a day. A longer interval also leaves the
shared bulk lane free for history backfill and settlement. Revisit after
observed cycles. Lock contention, WAL, CPU, memory, throughput and settlement
latency under real recovery were not measured; that needs the rollout.

## Correction discovery after 28 days

Automatic correction checks stop 28 days after kickoff. A later correction is
found only through a fixture or date request, which selects finished fixtures
of any age. P09-01 owns finding those fixtures from provider revisions,
fingerprints and historical reconciliation, then submitting them through the
existing request. `test_correction_after_the_schedule_is_reingested_by_a_targeted_request`
shows a 120-day-old result corrected from 1–0 to 1–1 this way, with both
history decisions kept, and confirms the automatic run does not select it.

## Tests on the integrated branch

| Check | Result |
| --- | --- |
| Format, ruff, mypy (strict sets), clippy, `go vet`, `golangci-lint`, `goose validate` | passed after the probe-table fix |
| Python unit suite with coverage (`make test`) | 2,347 passed |
| Rust `cargo test --workspace`; Go `go test ./...` | passed |
| Architecture, project status and docs checks; `make build` | passed |
| Web lint and typecheck, unit tests, production build | 261 passed; build passed; one existing lint warning in `forecast-history.test.tsx` |
| Recovery and settlement integration (`test_result_recovery.py`, `test_operational_recovery.py`, `test_external_prediction_recovery.py`) | 39 passed, then the new correction test passed |
| Full integration suite, disposable cluster, one shared database | 31 failed, the rest passed; classified below |
| Browser and accessibility (Playwright) | not run locally; CI |

The first recovery run had two failures: the test helper's 30-second `goose up`
timed out while `make test` and the builds ran alongside. Alone, all passed.

`pnpm install --frozen-lockfile` failed with
`ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`: the existing `web/node_modules`
had a different layout and pnpm will not remove it without a terminal. With
`CI=true` it reinstalled from the unchanged lockfile and the web checks passed.
This was the earlier unexplained pnpm failure; it is local state, not a
lockfile or build defect.

The 31 integration failures, none in recovery or settlement code:

| Class | Tests | Evidence |
| --- | ---: | --- |
| Shared database order | 13 | `test_integrity_verification.py` (10), `test_source_manifest_bindings.py` (1), the tampered geography case in `test_operational_provider_sync.py` (1) and `test_recovery_dispositions.py` (1) fail with duplicate provider codes or leftover rows, and pass when their files run alone |
| Compose environment and approved database namespace | 7 | `test_complete_recovery.py` (3) and `test_postgres_recovery.py` (4) need `POSTGRES_USER`/`POSTGRES_DB` from `.env`, the compose service or the approved temporary database namespace |
| Go API or browser fixture without compose settings | 11 | the real-browser and Go fixture tests in `test_remediation_browser.py`, `test_resolution_*.py` and `test_history_diagnostics_api.py` stop at `POSTGRES_ADDR is required` |

The branch record counted 29 on both the branch and `main` in the same kind of
environment. The suite was not rerun on `main` here. CI runs the full suite
with compose, restic and browsers and is authoritative for the 18
environment-dependent tests.

## Not established

- Recovery on populated data with real provider traffic (needs an authorized
  isolated evidence root, or the rollout).
- Resource use and latency under real recovery load.
- Browser and accessibility checks locally (Playwright browsers are not
  installed here; CI runs them).
