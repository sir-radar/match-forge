# Local storage cleanup, 13 November 2026

Dated record of the deletion that followed the
[storage audit](storage-audit-2026-11-13.md). The owner instructed, in the session,
that obsolete MatchForge-owned local files be deleted without making another backup,
and confirmed the database dumps separately. Evidence:
[local-storage-cleanup-2026-11-13.json](../evidence/local-storage-cleanup-2026-11-13.json)
lists every deleted path with its size.

## Result

| Measure | Before | After |
| --- | ---: | ---: |
| Host free space (`/System/Volumes/Data`) | 361.1 GB | 509.3 GB |
| `.local` | about 150 GB | 27.5 GB |

148.2 GB of disk was reclaimed. The deleted files measured 134.1 GB; the difference
is space APFS released on its own.

| Category | Deleted |
| --- | ---: |
| R3 and Architecture V2 investigation output under `.local/remediation` (top-level summaries kept) | 77.2 GB |
| 17 operating database dumps and their run folders (`p02`, `forecast-readiness-execution`, `data-status-remediation`, `data-recovery-current`, `backups`, `storage-rollout` dumps, two backup subfolders, the 11 November protection payload) | 41.1 GB |
| Two data-root copies and the finished 10 November restore drill (`foundation/operating-ntc-restore`) | 9.8 GB |
| Other generated output (`shadow-v4/phase-14`, `foundation/scope-investigation`, protection supplement, `p02-audit`, `issue02-unblocking`, `identity-recovery`, a benchmark, `data-recovery-followup`) | 4.6 GB |
| Go build and golangci-lint caches | 1.5 GB |

## Checks before deletion

- **Operating references.** Every file path registered in `football` resolves under
  `FOOTBALL_DATA_ROOT` (`.local/football-data`) or `.local/sync-runs`. No deleted
  path is referenced by code, scripts, `.env` or the backup configuration.
- **Data copies.** All 112,092 and 115,316 files of the two copies matched the
  active data root (or `.local/reports/sprint2`) by SHA-256.
- **Dumps.** `product_provider_resource_observations` is the one mutable table that
  stores provider payloads. In each of the 17 dumps, every payload row is still in
  `football` by primary key. Dumps from before 11 October predate the table. The other
  payload tables are append-only or derived.
- **Use.** No process had a deleted path open immediately before its deletion. No Go
  or lint process was running when the caches were removed.

## Kept

The operating data root and sync-run logs; the Sprint 2 reports and recovered
originals covered by backup `02376823`; the backup inventory and receipts; the running
API, web releases and rollback copies; the StatsBomb, R03 and R04 acquisitions and the
pitchapi research inputs; 26 raw provider files in `provider-wide-acquisition/acquired`;
the logs the running services write; `go-mod-cache` and `uv-cache` (downloads);
`target`, `web/node_modules`, `.venv` and `.tools` (in use).

Backup `02376823` is unaffected: every location it covers is still present. The
dumps were rollback points older than that backup; returning to those exact states
is no longer possible. Future accumulation is handled by the five-hour lifecycle in
PRs 218–220 once its rollout is approved.
