# Runbook: apply P02 form policy and re-qualify history

**Status: PROPOSED.** The owner runs this on the operating database. Nothing in this repository has applied it there. It was rehearsed on a restored copy of the operating database on 11 November 2026 (see [Rehearsal results](#rehearsal-results)).

**Scope:** migration `202611110100_form_policy_source.sql` and a one-time replay of retained API-Football fixture-date responses through history qualification (defect D-01 in [P02](../../architecture/unified-redesign-2026-11-10/roadmap.md)). The runbook does not change forecasts, forecast artifacts, published read reports, models or provider acquisition.

## Preconditions

1. The branch build that contains the migration, `football.product.history_requalification` and the v1/v2 report fallback is deployed to the API host but not yet restarted. The fallback serves existing reports until they are rebuilt, so the API stays up between the migration and the rebuild.
2. The retained raw responses under `FOOTBALL_DATA_ROOT` are present. The replay verifies each file's SHA-256 against `source_snapshots.manifest_sha256` and stops on a mismatch.
3. No sync or report job is running. Pause the scheduler from the admin console and wait for active work to finish.

## 1. Back up

Take a manual backup through `/admin/backup` (see [recovery](../../recovery.md)) and record its identifier. Then capture the preservation hashes:

```sql
SELECT 'forecasts', count(*), md5(string_agg(forecast_id::text||payload_sha256, ',' ORDER BY forecast_id)) FROM football.product_forecasts
UNION ALL SELECT 'forecast_artifacts', count(*), md5(string_agg(t::text, ',' ORDER BY t::text)) FROM football.forecast_artifacts t
UNION ALL SELECT 'read_reports', count(*), md5(string_agg(input_sha256||record_sha256, ',' ORDER BY input_sha256)) FROM football.product_read_reports
UNION ALL SELECT 'history_decisions_before_run', count(*), md5(string_agg(decision_id::text, ',' ORDER BY decision_id))
  FROM football.product_match_history_decisions WHERE decided_at < :'run_start';
```

Set `run_start` to the time you start step 2.

## 2. Migrate

```bash
make migrate
```

Rehearsal: 32 ms. `goose down` followed by `goose up` was also exercised on the copy and restores the previous objects exactly.

## 3. Dry run, then apply the re-qualification

```bash
.tools/bin/uv run python -m football.product.history_requalification --database-url "$DATABASE_URL" --data-root "$FOOTBALL_DATA_ROOT" --checkpoint .local/p02/requal-dry.json --dry-run --time-limit 1800
```

The dry run rolls every snapshot back. Check that `missing_files` is empty. Then apply:

```bash
.tools/bin/uv run python -m football.product.history_requalification --database-url "$DATABASE_URL" --data-root "$FOOTBALL_DATA_ROOT" --checkpoint .local/p02/requal.json --time-limit 43200
```

Each snapshot is its own transaction followed by a checkpoint, so a stopped run resumes from the last committed snapshot when rerun with the same checkpoint. The run is complete when the output has `"complete": true`.

The replay qualifies a result only when the retained response shows the same score that is stored. New decisions are stamped with the replay time and are append-only, so no knowledge cutoff before the run gains facts. A team/kickoff collision skips that one row and records it in `fixture_identity_ingestion_conflicts` with stage `HISTORY_QUALIFICATION` for the existing identity review.

## 4. Verify

1. Rerun the preservation query. Every hash must be unchanged. A changed hash is a stop condition: go to [Rollback](#rollback).
2. Run the integrity audit (`python -m football.product.integrity_audit`). Remaining API-Football `REGULATION_90` results without history should be identity conflicts awaiting review.
3. Run the affected-forecast inventory (`affected_forecasts` with `decided_from = run_start`) and attach it to the [re-evaluation proposal](../../governance/p02-forecast-reevaluation-proposal.md). Do not change any forecast.

## 5. Rebuild context reports and restart

Restart the API on the branch build and resume the scheduler. `refresh-public-reports` drains the context-report worklist and runs the scheduled detection and repair (`maintain_history`). Fixtures that are not yet rebuilt keep serving their v1 report with `form: null` and `RECENT_FORM_POLICY_UNKNOWN` until their next refresh. To bring upcoming fixtures forward, queue them:

```sql
SELECT football.enqueue_product_context_report_refresh(fixture_id)
FROM football.product_fixtures
WHERE kickoff_at BETWEEN statement_timestamp() - interval '1 day' AND statement_timestamp() + interval '14 days';
```

## Rollback

- **Before step 3 completes:** `goose down` one version removes the v2 source, the scope table and the trigger. The branch API keeps serving v1 reports.
- **After step 3:** the new history rows and decisions cannot be removed selectively without breaking the append-only decision log. Restore the step 1 backup, then redeploy the previous build.
- Forecasts, artifacts and published reports are never rewritten by this runbook, so no rollback of them is needed.

## Rehearsal results

Restored copy of the operating database, 11 November 2026, branch `ft/p02-remediation`:

| Measure | Result |
| --- | --- |
| Restore | 288,888 fixtures, 7 min 42 s |
| Migration up / down / up | passed, 32 ms |
| Snapshots replayed | 122 of 122, no missing or mismatched files |
| Finished rows read / qualified | 38,152 / 14,797 |
| Identity collisions handed to review | 1,282 events over 583 fixtures |
| API-Football `REGULATION_90` still without history | 490 (486 identity conflicts; 4 with no retained final-score response) |
| Preservation hashes (forecasts 18,224; artifacts 9,990; reports 310,024; prior decisions 867,839; eligible history at 1 Nov) | unchanged |

The evidence file for the rehearsal audit is listed in [docs/README.md](../../README.md).
