# Pre-P03 provider and result recovery handoff

**Verdict: PRE_P03_BLOCKED.** The merged code is `PRE_P03_CODE_READY` (PR #231 merged as `6e4b85c`, CI green). The operating rollout began on 14 November under `AUTHORIZE_PRE_P03_OPERATING_ROLLOUT_V1` and stopped on two defects; see [13. Rollout](#13-rollout) and the [rollout evidence](../../evidence/pre-p03-operating-rollout-2026-11-14.json).

| State | Status |
| --- | --- |
| Implemented | Yes, on `ft/pre-p03-result-recovery` |
| Integrated with PR #230 | Yes, rebased onto `bdb75ab` |
| Tested locally | Yes; full integration failures are environment or ordering only |
| Verified in CI | Yes, on merge `6e4b85c` |
| Migration and preservation rehearsed on populated data | Yes, on an existing isolated restore |
| Recovery rehearsed on populated data | No; needs an isolated evidence root |
| Merged | Yes, `6e4b85c` |
| Deployed or activated | Migration applied and release running; scheduled recovery off |
| Verified against operating data | Fixture, date and bounded batch runs on 14 November |

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

**14 November: partially applied, stopped.** Owner decision
`AUTHORIZE_PRE_P03_OPERATING_ROLLOUT_V1`
([record](../../evidence/owner-decision-authorize-pre-p03-operating-rollout-2026-11-14.json),
[evidence](../../evidence/pre-p03-operating-rollout-2026-11-14.json)).

- Backup: a snapshot-consistent logical dump (`ef1ea98b…`) restored in an
  isolated cluster, with P02 hashes identical to operating. The NTC drive was
  disconnected; the last Restic point is `02376823` (12 November).
- Migration `202611140100_result_recovery` applied at 04:23 UTC in 6.3 s, none
  pending, with `MATCHFORGE_RESULT_RECOVERY_INTERVAL=0`.
- Recovery: one fixture (score basis recovered), one UTC date (27 recovered
  with one API-Football request) and one bounded batch (4 same-day results).
  That is 32 results and 31 newly qualified history rows from validated
  snapshots. Every protected-row change was attributed to these runs, and P02
  hashes are unchanged.
- Stopped:
  1. Admin external settlement fails inside the worker fence before settling
     anything; the fix is PR #233.
  2. API-Football rejects date requests outside a narrow window, and 7 of 8
     batch requests failed while spending quota. A failed date is retried after
     5 minutes, backing off to at most 1 hour, so a `30m` schedule would exhaust
     the 100-request day. Scheduled recovery must stay off until this is fixed.
- Admin hid "Settle Finished Predictions" until the status request finished;
  the fix is PR #232.
- Limits observed: 29 of 38 retained-evidence candidates have a provider
  kickoff that moved from the canonical one, and their replay is declined
  without a recorded reason. Some routed fixtures lack trusted team mappings
  (`IDENTITY_UNRESOLVED`), so "routed" overstates what is recoverable now.

**14 November, later: settlement verified, batches stopped on low yield.**
With PRs #232, #233, #235 and #236 deployed, settlement settled 15 predictions,
14 of them without an internal forecast, and a second run changed nothing.
A probe confirmed the API-Football free-plan window: yesterday to tomorrow (UTC).
Two more bounded batches, under `AUTHORIZE_PRE_P03_ADDITIONAL_RECOVERY_BATCHES_V1`,
recovered nothing and were stopped. The backlog is an identity problem, not a
provider-capacity one:

- 291 candidates have a same-match twin fixture: 39 tier-1 pairs (15 of them
  both VERIFIED) and 68 tier-2.
- 121 are blocked by 149 untrusted FotMob team mappings.
- 746 have only PROVISIONAL PitchAPI identities.

The case keys for the Resolution Center are in the
[evidence](../../evidence/pre-p03-recovery-batches-and-identity-2026-11-14.json).
Scheduled recovery needs the live-sync reserve in PR #237 first.

**14 November, identity remediation.**

- Cross-provider discovery (PR #239) finds 0 pure mapping gaps on operating;
  the 36 audit candidates were duplicate twins or moved kickoffs.
- Under `AUTHORIZE_PRE_P03_TIER1_DUPLICATE_RESOLUTION_V1`, 17 of the 21
  previewed tier-1 duplicates were resolved through the Resolution Center:
  16 candidates resolved, 15 with qualified history.
- The other 4 were refused correctly: 2 twins were already quarantined, and 2
  are three-way duplicates blocked by the history identity guard. Their FotMob
  follow-ups preview QUALIFIED.
- See the [evidence](../../evidence/pre-p03-identity-remediation-2026-11-14.json).

Original preflight list:

- [x] PR #230 merged (`bdb75ab`).
- [x] PR #231 integrated against that `main`.
- [x] CI green on the final head.
- [x] PR #231 merged; the merge commit is the build to deploy (API, web, worker).
- [x] Migration chain verified from `202611130600`.
- [x] Fresh operating backup taken and independently restored under the
      [recovery policy](../../recovery.md) (logical dump; not a Restic point).
- [x] P02 preservation baseline and the 21-table row hashes captured on
      operating data.
- [x] Runtime versions, Git SHA and migration status recorded.
- [x] Active work and leases audited; no bulk-lane run active.
- [x] Provider budgets reviewed for the day.
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

Items 2 and 3 below were decided on 14 November. Open now:

- review and merge PR #232 and PR #233;
- choose the API-Football recovery fix (skip or long-defer dates outside the
  plan's window, and record the rejection text);
- then resume the rollout from settlement verification and scheduled recovery.

The list as written before the rollout:

1. **Isolated evidence root for the populated recovery pass.** Authorize an
   isolated copy (or copy-on-write clone) of `FOOTBALL_DATA_ROOT` for the reused
   restore, so a bounded recovery pass (one fixture, one date, then up to eight
   dates per provider) can run with real provider traffic and without writing
   into the operating evidence store. Alternatively, accept the rollout steps 7–12
   as that evidence.
2. **Merge PR #231** once CI is green.
3. **Operating rollout:** apply the migration, deploy the merge build and run
   the activation steps above.

`docs/project-status.json` records `PRE_P03_BLOCKED` with operating rollout
`PARTIALLY_APPLIED_STOPPED`.

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
