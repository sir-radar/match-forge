# Pre-P03 provider and result recovery handoff

**Verdict: PRE_P03_BLOCKED.** The branch implements the foundation below.
Dataset-wide recovery, the complete acceptance matrix, and controlled operating
adoption are pending.

## Implementation

- Completed historical scopes can be refreshed the same day. The global
  result freshness gate and API-Football season cap were removed. Catalogue
  caching and retry deadlines still apply. The hourly minimum and the
  two-scope/one-discovery hard ceilings were removed. Operators can still cap
  per-run work.
- Result recovery runs through the existing Go sync runner and Python
  ingestion owners. The Admin actions select an individual fixture, a UTC
  kickoff date, or a batch of unresolved fixtures. An eligible historical
  scope can be refreshed from the same page.
- FotMob and PitchAPI try retained regulation-time evidence for exact
  native mappings before requesting the corresponding provider date.
  API-Football uses the same candidate view, the existing budget and exact
  fixture identity checks. Each provider can proceed if another fails.
- Existing result, history and external settlement owners consume the
  evidence. Tests exercise stale fixtures outside the live date window,
  source cooldowns, correction history and the Admin fixture selector.

The [Phase A audit](../../evidence/pre-p03-acquisition-audit-2026-11-13.md)
contains the restriction inventory, provider capability matrix and operating
census. Its 1,678 overdue unresolved rows, 29 eligible candidates in the old
view, and 93,380 unknown score-basis rows were measured before implementation.
They are not a recovery count.

## P03 integration

The current contracts are migration `202611130400_result_recovery`,
`football.product_result_recovery_candidates`, the existing
`football.product_provider_refresh_state`, and
`POST /v1/admin/sync/result-recovery` with an optional UTC `date` or
`fixture_id`. The `RESULT_RECOVERY` run uses existing sync-run history and
publication fencing. The
[Admin OpenAPI contract](../../api/openapi.yaml) also records historical
refresh. P03 retains live resource scheduling, fairness, catch-up and
dependency-specific work. P04 retains committed events, SSE and browser
freshness. P09 retains broader source and identity gaps.

## Open requirements

- Verify actual scoped entitlements and supported results outside the three
  automated provider routes. Football-data.org remains a historical fallback
  through the MVP path. Other providers have retained or experimental
  acquisition where evidenced in the audit. Cross-provider coverage for
  fixtures lacking an admitted native mapping remains open.
- Demonstrate autonomous correction discovery for already-qualified results,
  advanced lifecycle and provider-ID changes, retained-evidence reactivation,
  and populated request and database costs. Existing cross-source conflicts
  require qualified evidence. A manual recheck does not resolve them by itself.
- Complete the controlled rehearsal, P02 preservation checks and external
  settlement verification on the intended release. PR #230 was an open draft
  during Phase A. The implementation uses settlement code and SQL triggers
  already on main.
- Record a verified deployment, resource consumption and dataset-wide recovery
  results before declaring readiness.

## Controlled rollout

Use the [recovery policy](../../recovery.md) to capture and verify a recoverable
backup before an authorized rollout. Record the current process Git SHA,
migration status and the [P02 preservation hashes](../../../scripts/p02/preservation.sql)
on the operating database. Rehearse the migration and a selected date or
fixture on an isolated restore. Check canonical and settlement changes
against retained evidence and compare protected hashes.

After approval, apply the migration and deploy the verified build. Start
with one eligible date, inspect requests and lease or cooldown state, then
choose a monitored `MATCHFORGE_RESULT_RECOVERY_INTERVAL` based on measured
capacity. The example and local environment set it to zero until activation.
Check the next scheduled run, resulting history and settlement, and any
unresolved provider and identity dispositions.

To stop scheduled recovery, set the interval to zero and restart the API.
Cancel an active recovery through the existing Admin sync control if needed.
Keep acquired evidence, work records and published revisions. Revert the
worker/API prospectively if necessary, with migration and protected-data
changes handled under the existing recovery policy. Rollout is pending owner
authorization and must be verified independently of code delivery.
