# Pre-P03 provider and result recovery handoff

**Verdict: PRE_P03_BLOCKED.** The implementation and its deterministic
acceptance tests are complete on the branch. `PRE_P03_CODE_READY` still needs
PR #230 merged and this branch reconciled with it, and CI green on the result.
`PRE_P03_OPERATING_READY` needs the authorized rollout below, populated
preservation and capacity evidence, and observed recovery outcomes.

## Implementation

- Completed historical scopes can be refreshed the same day. The global
  result freshness gate, the API-Football season cap, the hourly minimum and
  the two-scope/one-discovery hard ceilings were removed. Catalogue caching,
  provider cooldowns and operator per-run caps still apply.
- `RESULT_RECOVERY` runs through the existing Go sync runner and Python
  ingestion owners. Admin actions recover one fixture, one UTC kickoff date or
  a batch, and refresh an eligible historical scope.
- Eligibility is per fixture and provider in
  `football.product_result_recovery_state`. The shared UTC date row is only a
  15-minute lease against duplicate requests. Operator requests ignore
  MatchForge's own schedule but not provider deadlines. A newly eligible
  fixture is never held back by an earlier check of its date.
- Every checked fixture has a named outcome and a next check. Runs split their
  date budget between the newest and the longest-waiting dates, and back off by
  fixture age (15 minutes to 7 days). Blocked fixtures are retried weekly, or at
  once when an exact mapping changes.
- FotMob, PitchAPI and API-Football replay retained evidence before making a
  request. Finished mapped results are rechecked for corrections 1, 7 and 28
  days after kickoff, then no further. Corrections go through the existing
  versioned history decisions and external settlement work.
- The Admin panel and run summary report recovered, corrected and unresolved
  fixtures, not fetched resources. An operator fixture request that is not
  recovered fails its run with the outcome.

The [design section](design.md#pre-p03-result-recovery) describes the rules.
The [verification record](../../evidence/pre-p03-recovery-verification-2026-11-14.md)
has the root causes, current census, provider participation, query cost and
test results. The [13 November audit](../../evidence/pre-p03-acquisition-audit-2026-11-13.md)
is the pre-implementation baseline.

## Current population

On 14 November, 2,650 fixtures were recovery candidates. 1,714 are verified
and reachable through an exact API-Football, FotMob or PitchAPI mapping, and
38 of those already have retained final evidence. 925 are provider-scoped
fixtures awaiting identity admission, and 11 verified fixtures have no
recurring provider route (5 football-data.org only). Of the 93,380 finished
unknown-basis rows, 92,184 already have qualified history and are not
candidates. No result has been recovered on operating data yet.

## P03 integration

The contracts are migration `202611140100_result_recovery`,
`football.product_result_recovery_candidates`,
`football.product_result_recovery_state`, the date lease rows in
`football.product_provider_refresh_state`, and
`POST /v1/admin/sync/result-recovery` with an optional UTC `date` or
`fixture_id`. P03 inherits working recovery and correction discovery for
mapped fixtures. It keeps live resource scheduling, fairness across live work
and affected-only dependencies. P04 keeps committed events, SSE and browser
freshness. P09 keeps identity admission for the 925 provider-scoped fixtures,
the 11 unrouted fixtures and other authentic source gaps.

## Remaining before readiness

1. Merge PR #230, rebase this branch, resolve the four known conflicts as in
   the verification record, and get CI green.
2. Run the populated preservation rehearsal on an approved restore or
   existing isolated snapshot: P02 hashes, fixture identities, snapshots,
   mappings, history, forecasts, external predictions and settlements before
   and after the migration and a bounded recovery pass.
3. Complete the authorized rollout below and record request volume, latency,
   recovered and corrected counts, retry rates, database cost and the oldest
   runnable age over several cycles.

## Controlled rollout

Requires operating-write and deployment authorization.

1. Confirm a verified recoverable backup under the [recovery policy](../../recovery.md).
   Record the process Git SHA, migration status and
   [P02 preservation hashes](../../../scripts/p02/preservation.sql).
2. Apply the migration. It adds a view, a table and an index on that table;
   no existing row changes and no long lock is taken on existing tables.
3. Deploy the API, web and worker together with
   `MATCHFORGE_RESULT_RECOVERY_INTERVAL=0`.
4. Recover one fixture, then one date, from Admin. Inspect provider requests,
   outcomes, canonical changes, history decisions and settlements.
5. Run one unscheduled batch with the default eight dates per provider, then
   set a monitored interval. About 15 runs cover the current API-Football
   backlog; steady-state correction checks need about three requests per
   provider per day.
6. Watch repeated cycles: same-day results, older fixtures still progressing,
   provider deferrals and P02 hashes.

## Rollback

Set `MATCHFORGE_RESULT_RECOVERY_INTERVAL=0` and restart the API; cancel any
active run from Admin. That stops new recovery work. Keep the migration: the
`Down` step refuses to run, because run history, recovery state and acquired
evidence must be kept. Earlier workers ignore the new view and table.

Revert the Python worker and Go scheduling if needed, but keep a web and API
build that knows the `RESULT_RECOVERY` sync type. Earlier web builds reject an
unknown sync type when they list runs, and recovery runs stay in history.
Published results, history decisions and settlements are append-only and stay
in place; correct any wrong result through the existing correction path.
