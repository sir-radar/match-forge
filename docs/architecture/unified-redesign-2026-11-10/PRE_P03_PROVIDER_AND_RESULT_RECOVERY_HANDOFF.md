# Pre-P03 provider and result recovery handoff

**Verdict: PRE_P03_BLOCKED.** The code is integrated with PR #230 and passes local checks; `PRE_P03_CODE_READY` needs green CI on the final head.
`PRE_P03_OPERATING_READY` and
`PRE_P03_READY` need the authorizations under
[Outstanding owner decisions](#14-outstanding-owner-decisions).

| State | Status |
| --- | --- |
| Implemented | Yes, on `ft/pre-p03-result-recovery` |
| Integrated with PR #230 | Yes, rebased onto `bdb75ab` |
| Tested locally | Yes; full integration failures are environment or ordering only |
| Verified in CI | Pending on the final head; see PR #231 |
| Migration and preservation rehearsed on populated data | Yes, on an existing isolated restore |
| Recovery rehearsed on populated data | No; needs an isolated evidence root |
| Merged | No |
| Deployed or activated | No |
| Verified against operating data | Read-only census only |

Evidence: the [branch verification record](../../evidence/pre-p03-recovery-verification-2026-11-14.md),
the [PR #230 integration record](../../evidence/pre-p03-pr230-integration-2026-11-14.md)
and the [13 November audit](../../evidence/pre-p03-acquisition-audit-2026-11-13.md),
the pre-implementation baseline.

## 1–3. Commits and integration

PR #230 merged as `bdb75ab33bd4df702491083f73591ba799e7b0c6`. PR #231 was
rebased from `4423d06` onto it; its final head is the one PR #231 shows. Three rebase stops were
resolved as unions of both sync types and both test sets. One interaction
defect was fixed: the two PRs' readiness probes together failed the Go
complexity lint. The [integration record](../../evidence/pre-p03-pr230-integration-2026-11-14.md#integration)
lists each resolution.

## 4. Migration

`202611140100_result_recovery` follows PR #230's `202611130400`–`0600`. From
the operating schema (`202611130600`) it adds the candidate view, the state
table and its index, and widens the sync type check to include
`RESULT_RECOVERY` while keeping `EXTERNAL_PREDICTION_SETTLEMENT`. Existing rows
and other constraints are unchanged. It applied in 256 ms on the populated
restore. `down` refuses; only forward repair is supported.

## 5. Tests and CI

See the [integration record](../../evidence/pre-p03-pr230-integration-2026-11-14.md#tests-on-the-integrated-branch).

## 6. Provider recovery capabilities

API-Football, FotMob and PitchAPI recover by UTC date through their existing
ingestion owners, replaying retained evidence first. football-data.org has
only league-season history through the MVP fallback. Other archives have no
recurring route. The [design section](design.md#pre-p03-result-recovery) has
the rules. Finished results are rechecked 1, 7 and 28 days after kickoff.
Later corrections are re-ingested through fixture or date requests; finding
them belongs to [P09-01](p09-01-historical-completeness-plan.md#phase-4-remaining-overdue-result-gaps-c4-c5).

## 7. Current population

Operating, 14 November 03:35 UTC, read-only: 2,651 candidates. 1,715 are
verified with an exact recurring route (39 with retained final evidence), 925
await identity admission and 11 verified fixtures have no recurring route (5
football-data.org only). 285 kicked off in the last 7 days. None has been
recovered on operating data.

## 8. Populated preservation

On the reused isolated restore `settlement_remediation_restore`, 21 protected
tables were hashed row by row before and after the migration, and the P02
preservation hashes were captured. All were identical. The bounded recovery
pass on populated data is still open.

## 9. External settlement

Settlement has one owner, used by the sync, operational and recovery paths. It
needs no internal forecast, honours PR #230's fixture association and source
date rules, re-evaluates a corrected result once, and is idempotent on retry and
under concurrent manual and scheduled runs. Recovery, settlement and history
backfill share the bulk lane and never run together.

## 10. Request and resource cost

Selection costs 0.4–0.9 s per provider on populated data. The API-Football
backlog is about 87 date requests against a 100-request daily quota that
operating sync exhausted on four of the last seven days, so quota sets the
pace. Initial interval: `MATCHFORGE_RESULT_RECOVERY_INTERVAL=30m`, revisited
after observed cycles. Lock, WAL, CPU, memory and latency under real recovery
are not measured.

## 11. Source limitations

925 fixtures need identity admission; 11 have no recurring provider route.
API-Football's daily quota bounds backlog speed. These are P09 work or provider
limits, not recovery defects.

## 12. Rollback

1. Set `MATCHFORGE_RESULT_RECOVERY_INTERVAL=0` and restart the API. No new
   scheduled recovery starts.
2. Let an active `RESULT_RECOVERY` run finish, or cancel it from Admin. Its
   lease expires in 15 minutes and committed outcomes stay.
3. Keep the migration. Do not run `down`; it refuses, because run history,
   recovery state and acquired evidence must be kept.
4. Do not roll the API or web back below this PR. Builds before it reject
   `RESULT_RECOVERY` rows when listing runs, and builds before PR #230 also
   reject `EXTERNAL_PREDICTION_SETTLEMENT`. The oldest compatible API, web and
   worker build is this PR's merge commit. A Python worker rollback alone is
   safe with the interval at zero: older workers never read the new view or
   table, but they lack `recover-results`, so an Admin recovery request fails
   its run until the worker is restored.
5. Published results, history decisions, settlement revisions and evidence
   are append-only and stay. Correct a wrong result through the existing
   correction path, which appends a new decision and settlement revision.
6. After any rollback, list Admin runs and check the API reads both new sync
   types before resuming scheduled work.

## 13. Rollout

Not started. Preflight, all of which must hold first:

- [x] PR #230 merged (`bdb75ab`).
- [x] PR #231 integrated against that `main`.
- [ ] CI green on the final head.
- [ ] PR #231 merged; the merge commit is the build to deploy (API, web, worker).
- [x] Migration chain verified from `202611130600`.
- [ ] Fresh operating backup taken and independently restored under the
      [recovery policy](../../recovery.md).
- [ ] P02 preservation baseline and the 21-table row hashes captured on
      operating data.
- [ ] Runtime versions, Git SHA and migration status recorded.
- [ ] Active work and leases audited; no bulk-lane run active.
- [ ] Provider budgets reviewed for the day.
- [x] Rollback compatibility documented above.

Activation, after authorization:

1. Record the operating Git SHA and `goose status`.
2. Verify the backup restores.
3. Capture P02 and row-hash baselines.
4. Apply `202611140100_result_recovery`.
5. Deploy the API, web and worker from the merge commit with
   `MATCHFORGE_RESULT_RECOVERY_INTERVAL=0`.
6. Confirm automatic recovery is off (no scheduled `RESULT_RECOVERY` run).
7. Recover one eligible fixture from Admin, preferably one of the 39 with
   retained final evidence, then one UTC date.
8. Inspect the source snapshot, canonical change and recovery outcome.
9. Check the team history decision.
10. Check external settlement for affected predictions.
11. Compare preservation hashes; only the recovered fixtures may differ.
12. Record request counts, run time, database time, locks and WAL.
13. Set the interval to `30m`.
14. Observe at least four scheduled runs.
15. Confirm a same-day result is recovered.
16. Recount unresolved and blocked fixtures by outcome.
17. Restart the API and worker mid-run and confirm the lease expires and work
    resumes once.

## 14. Outstanding owner decisions

1. **Isolated evidence root for the populated recovery pass.** Authorize an
   isolated copy (or copy-on-write clone) of `FOOTBALL_DATA_ROOT` for the reused
   restore, so a bounded recovery pass (one fixture, one date, then up to eight
   dates per provider) can run with real provider traffic and without writing
   into the operating evidence store. Alternatively, accept the rollout steps 7–12
   as that evidence.
2. **Merge PR #231** once CI is green.
3. **Operating rollout:** apply the migration, deploy the merge build and run
   the activation steps above.

`docs/project-status.json` still records `PRE_P03_BLOCKED` and
`NOT_AUTHORIZED_OR_APPLIED`; it changes only with those decisions.

## 15. P03 readiness

**PRE_P03_BLOCKED.** P03 must not start until recovery runs on operating data
and same-day results are verified (`PRE_P03_READY`). P03 inherits the contracts
`202611140100_result_recovery`, `football.product_result_recovery_candidates`,
`football.product_result_recovery_state`, the date lease rows in
`football.product_provider_refresh_state` and
`POST /v1/admin/sync/result-recovery` (optional UTC `date` or `fixture_id`). P03
keeps live scheduling, fairness across live work and affected-only
dependencies. P04 keeps committed events, SSE and browser freshness. P09 keeps
identity admission, unrouted fixtures, other source gaps and correction
discovery after 28 days.
