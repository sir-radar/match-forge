# Storage consolidation and Admin-controlled cleanup — 12 November 2026

Dated working report for the storage consolidation task that follows
[PR #194](https://github.com/sir-radar/match-forge/pull/194). Each stage is
appended when it is committed. Nothing here authorizes deleting an existing
resource; see [storage lifecycle operations](storage-lifecycle.md) for the
standing procedure.

While this task ran, a separate P02 rollout (context-report backfill and global
integrity audit) and a `fotmob-sync` were writing to the operating database. This
task used a separate worktree, ran only catalog and read-only queries against the
operating cluster, applied no migration, restarted no service and deleted nothing.

## Stage A — existing implementation

| Check | Result |
| --- | --- |
| PR #194 | Merged into `main` as `5ac98fb` on 12 November. CI on the PR head: `Classify changes` and `Deterministic checks` passed. Review decision was still `REVIEW_REQUIRED` at merge. |
| PR #193 (P0) | Merged. Its evidence ([storage protection](storage-protection-2026-11-11.md)) is unchanged: external encrypted copies, 159 declared gaps, `full_recovery: false`. |
| Go storage, Admin and command suites on `main` | `go test ./internal/storage/... ./internal/app/... ./cmd/storage/...` passed. |
| Operating database migrations | Latest applied version is `202611110100` (from the open P02 remediation branch). The storage migrations `202611110400_storage_lifecycle` and `202611110500_competition_noop_updates` are **not applied**; `football.storage_resources` does not exist. |
| Running API | `.local/bin/football-api` on port 8080 was built from the P02 branch, not from `main`. It has no storage endpoints. |
| Storage policy | `MATCHFORGE_STORAGE_POLICY` is empty, so scheduled reviews are disabled. |

What PR #194 delivered, and its state:

| Capability | State |
| --- | --- |
| Registry tables, immutable reviews and receipts, job-owned capacity reservations | Implemented; not deployed to the operating database |
| Capacity admission with recovery headroom | Implemented; used by the storage command only |
| Evidence archive pack/verify/read/restore with deduplicated blobs | Implemented and tested; operating use not started |
| Disposable fixture database launcher with OID-bound teardown | Implemented |
| Scheduled dry-run review through the existing runner | Implemented; disabled by empty policy |
| Admin `/admin/storage` | Read-only dashboard. No resource explorer, no database view, no actions |
| Quarantine, deletion, restore of existing resources | **Absent.** A trigger rejects `QUARANTINED` and `DELETED` states; `storage_reviews.dry_run` and `reclaimed_bytes=0` are enforced by `CHECK` |
| Authoritative database identity | **Absent.** Every database is marked protected with the same generic blocker; nothing distinguishes the operating database from rehearsal copies |

Gaps against this task, in order of dependency:

1. No authoritative-resource identity, so a deletion path cannot fail closed on it.
2. No per-resource classification beyond a blanket `protected=true`.
3. No deletion adapters, approvals that permit execution, quarantine or restore.
4. No resource explorer, database view, or bulk actions in the Admin UI.
5. Migrations and the policy are not deployed, so nothing runs in operation.
