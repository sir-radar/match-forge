# Runbook: apply P02 form policy, reconcile and re-qualify history

**Status: PROPOSED.** The owner runs this on the operating database after recording approval. Nothing in this repository has applied it there. It was rehearsed twice on restored copies of the operating database on 11 November 2026 (see [Rehearsal results](#rehearsal-results)).

**Scope:** migration `202611110100_form_policy_source.sql`; a one-time replay (`p02-history-requalification-v2`) of every retained, checksum-verified API-Football fixture response that (1) reconciles overdue fixtures whose retained response after kickoff shows a terminal status and (2) offers finished regulation-time results to history qualification (defect D-01 in [P02](../../architecture/unified-redesign-2026-11-10/roadmap.md)); then a paced rebuild of context reports. The runbook does not change forecasts, forecast artifacts, published read reports, models or provider acquisition.

## Stop conditions

Stop and go to [Rollback](#rollback) when any of these happens:

- a preservation hash differs from the step 1 capture;
- the dry run or apply reports `missing_files`, a checksum mismatch or `APPLY_ERROR`;
- the apply's reconciled fixture set or qualified count differs from the dry run;
- the restore test in step 1 fails.

## Preconditions

1. The branch build that contains the migration, `football.product.history_requalification` v2 and the v1/v2 report fallback is deployed to the API host but not yet restarted. The fallback serves existing reports until they are rebuilt.
2. The retained raw responses under `FOOTBALL_DATA_ROOT` are present. The replay verifies each file's SHA-256 against `source_snapshots.manifest_sha256` and stops on a mismatch.
3. No sync or report job is running. Pause the scheduler from the admin console and wait for active work to finish.
4. An owner decision event approving this runbook for the operating database exists.

## 1. Back up and prove the backup restores

1. Take a manual backup through `/admin/backup` (see [recovery](../../recovery.md)) and record its identifier and receipt.
2. Take a logical dump with the server's own `pg_dump` (the host client may be older than the server) and record its checksum:

   ```bash
   docker compose exec -T -e PGOPTIONS="-c default_transaction_read_only=on" postgres pg_dump -U "$POSTGRES_USER" -Fc -Z 1 "$POSTGRES_DB" > .local/p02/rollout/operating-before.dump
   shasum -a 256 .local/p02/rollout/operating-before.dump > .local/p02/rollout/operating-before.dump.sha256
   ```

3. Restore the dump into a scratch database and compare it with the source. The restore is verified only when the table counts and the step 1.4 hashes match on both:

   ```bash
   docker compose exec -T postgres createdb -U "$POSTGRES_USER" football_p02_restore_check
   docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d football_p02_restore_check --no-owner < .local/p02/rollout/operating-before.dump
   ```

4. Set `run_start` to the current time and capture the preservation hashes on the operating database and on the restore check:

   ```bash
   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -v run_start="'<run_start>'" -f scripts/p02/preservation.sql
   ```

   Keep the output with the backup identifier. Drop the scratch database after the comparison.

## 2. Migrate

```bash
make migrate
```

Rehearsal: 32 ms. `goose down` followed by `goose up` restores the previous objects exactly.

## 3. Dry run, then apply

```bash
.tools/bin/uv run python -m football.product.history_requalification --database-url "$DATABASE_URL" --data-root "$FOOTBALL_DATA_ROOT" --checkpoint .local/p02/rollout/requal-dry.json --dry-run --time-limit 3600
```

The dry run executes the whole replay in one transaction and rolls it back, so its counts are the counts the apply will produce. Check that `missing_files` and `reconciliation.missing_files` are empty, `reconciliation.errors` is empty, and the outcome is close to the rehearsal allowing for drift since the dump. Record the dry-run output; the apply must report the same `APPLIED_FROM_RETAINED_TERMINAL_RESPONSE` count, `applied_fixture_ids_sha256` and `qualified`. The unapplied outcome buckets can grow slightly between the two runs, because more fixtures pass kickoff plus 4 hours. Then apply:

```bash
.tools/bin/uv run python -m football.product.history_requalification --database-url "$DATABASE_URL" --data-root "$FOOTBALL_DATA_ROOT" --checkpoint .local/p02/rollout/requal.json --time-limit 43200
```

The reconciliation phase runs once and is recorded in the checkpoint. Each snapshot of the qualification phase is its own transaction followed by a checkpoint, so a stopped run resumes when rerun with the same checkpoint. The run is complete when the output has `"complete": true`.

What the replay changes and why it is safe:

- **Reconciliation** updates a fixture only when it is still unresolved more than 4 hours after kickoff, its latest retained API-Football response was acquired after kickoff, that response shows a terminal status (`FT`, `AET`, `PEN`, `AWD`, `WO`, `CANC`, `ABD`, `PST`), and the stored row is not newer than that response. Everything else is counted under a typed outcome and left as it is. The update cites the retained snapshot and keeps its acquisition time.
- **Qualification** adds a history row only when the retained response shows the same score that is stored. New decisions are stamped with the replay time and are append-only, so no earlier knowledge cutoff of a forecast gains facts. A team/kickoff collision skips that one row and records it in `fixture_identity_ingestion_conflicts` with stage `HISTORY_QUALIFICATION` for identity review.

## 4. Verify

1. Rerun the preservation script with the same `run_start`. Every row must be unchanged.
2. Run the integrity audit to a new output directory:

   ```bash
   .tools/bin/uv run python -m football.product.integrity_audit --database-url "$DATABASE_URL" --out .local/p02-audit/<date>-operating --time-limit 7200
   ```

   In `domains.reconciliation_correctness.api_football_regulation_90_without_history_by_cause`, `NOT_IN_IDENTITY_REVIEW` must be 0.
3. Run the affected-forecast inventory (`integrity_audit.affected_forecasts` with `decided_from = run_start`), record its SHA-256, and attach it to the [re-evaluation proposal](../../governance/p02-forecast-reevaluation-proposal.md). Do not change any forecast.

## 5. Rebuild context reports and restart

Restart the API on the branch build and resume the scheduler. `refresh-public-reports` drains the context-report worklist and runs the scheduled detection and repair (`maintain_history`). Fixtures not yet rebuilt keep serving their v1 report with `form: null` and `RECENT_FORM_POLICY_UNKNOWN`.

Bring upcoming fixtures forward first:

```sql
SELECT football.enqueue_product_context_report_refresh(fixture_id)
FROM football.product_fixtures
WHERE kickoff_at BETWEEN statement_timestamp() - interval '1 day' AND statement_timestamp() + interval '14 days';
```

Then backfill historical reports in paced batches. Each call queues up to N fixtures whose latest report has no form object (newest kickoff first) and drains the queue for the given time; published reports are immutable, so a rebuild only adds a record:

```bash
.tools/bin/uv run python -m football.product.cli refresh-context-reports --enqueue-pre-policy 20000 --drain-seconds 3300
```

Repeat until `backfill.pre_policy_after` is 0. Run it when the scheduler is quiet or accept that the scheduled worker shares the queue; the worker keeps half of each batch for fixtures near kickoff.

## Rollback

- **Before step 3 completes:** `goose down` one version removes the v2 source, the scope table and the trigger. The branch API keeps serving v1 reports.
- **After step 3:** new history rows, decisions and reconciled fixture states cannot be removed selectively without breaking the append-only decision log. Restore the step 1 dump (or the admin backup), verify it with the preservation script, then redeploy the previous build.
- **During step 5:** stop the backfill. Rebuilt reports are additional immutable records and the API serves the newest current one; nothing needs undoing.
- Forecasts, artifacts and published reports are never rewritten by this runbook, so no rollback of them is needed.

## Rehearsal results

Second rehearsal, replay v2, on a fresh restore of the operating database taken on 11 November 2026 ([evidence](../../evidence/p02-remediation-rehearsal-2-2026-11-11.json)); replay v1 is in the [first rehearsal evidence](../../evidence/p02-remediation-rehearsal-2026-11-11.json).

| Measure | Result |
| --- | --- |
| Dump / restore | 2.4 GB in 3 min 20 s / 19 min 56 s; restore verified by identical preservation hashes on both databases |
| Dry run / apply | 65 min / 63 min; same reconciled fixture set (hash) and same qualified count |
| Snapshots read | 614 (548 fixture-shaped, 66 other), no missing or mismatched files |
| Overdue API-Football fixtures reconciled | 949 (920 `FT`, 21 `AWD`, 4 `WO`, 2 `PEN`, 1 `AET`, 1 `PST`) |
| Unreconciled overdue API-Football fixtures | 405 not terminal at last observation, 326 never observed after kickoff, 7 stored row newer than evidence |
| Results qualified | 14,542 (13,595 from dated requests, 921 from the ad hoc recovery response) |
| API-Football `REGULATION_90` still without history | 487, all duplicate identities in review (483 already in history through the duplicate) |
| Overdue results, all providers | 2,238 before, 1,322 after |
| Context reports rebuilt from the worklist | 10,459 in 579 s, 0 failures |
| Historical backfill sample | 3,000 in 124 s, 0 failures |
| Preservation hashes (forecasts 18,750; artifacts 9,990; reports 310,487; decisions 875,104; snapshots 83,360; review rows 2,038) | unchanged |
| Global audit `p02-integrity-audit-v4` | 257,823 fixtures, 257,822 reports current, 0 untraceable served form symbols |

Results still without history after the replay are expected. Extra-time and shootout results are not forecast-eligible. Sources without a score duration (football-data.co.uk, openfootball, PitchAPI and unmapped imports with `UNKNOWN` basis) have no qualification path. Identity collisions wait for review. Overdue fixtures without retained terminal evidence need a new provider observation ([P09-01 plan](../../architecture/unified-redesign-2026-11-10/p09-01-historical-completeness-plan.md)).
