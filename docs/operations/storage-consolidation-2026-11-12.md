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

## Stage B — authoritative operating database

The operating database is **`football`** in the Compose PostgreSQL cluster
(container `football-forecasting-postgres-1`, port 55433):

| Property | Value |
| --- | --- |
| Cluster system identifier | `7679328148388241450` |
| Database OID | `16384` (created 29 August 2026) |
| Size at observation | 15,880,787,647 bytes |
| Latest applied migration | `202611110100` |
| Consumers | 11 sessions at observation: the API on port 8080, the P02 rollout backfill and integrity audit, `fotmob-sync` |

Every operating consumer reaches it through `DATABASE_URL` in `.env`
(`127.0.0.1:55433/football`): the Go API, Python workers and CLI, the Work
Orchestrator functions (`football.work_items`), model governance and forecast
serving. No other database had a connection.

Protection is bound to the cluster system identifier and OID, never to the name.
The new migration (Stage D) records it append-only in
`football.storage_protections` with role `AUTHORITATIVE_OPERATING_DATABASE`
when the API first starts against it, allows one such row per cluster, and
refuses every storage operation on that identity in SQL. If the connected
database ever differs from the registered identity, all database deletion is
disabled (fail closed).

Other PostgreSQL clusters on this host are outside the API's reach and are not
merged or managed:

| Cluster | Content | Status |
| --- | --- | --- |
| `football-gate-a-postgres-1` (Sprint 1 Gate A experiment compose) | `football_prototype`, 12.7 MB | Separate experiment; unresolved ownership, negligible size |
| `matchforge-global-audit-pg` (created 11 November) | `audit`, 17.9 MB | Used by the global-history-audit worktree; unresolved |

The Docker volume `crypto-analyser_postgres_data` (923 MB, unattached) does not
belong to MatchForge and was not touched.

Target: one authoritative operating database plus independently justified
supporting databases. Legitimate exceptions today are the `postgres`
maintenance database and the three P02 databases while that rollout is open.

## Stage C — database inventory and consolidation decisions

The cluster holds **44 databases (176.2 GB)**: the operating database (15.9 GB)
and 43 others (160.3 GB). The 11 November audit counted 42; two P02 databases
were created since.

Method ([evidence](../evidence/storage-database-consolidation-2026-11-12.json),
script [`storage_database_inventory.py`](../../scripts/storage_database_inventory.py)):
read-only connections compared the primary keys of 27 canonical tables
(competitions, seasons, teams, players, matches, events, product read models,
identity admissions and decisions, provider mappings, forecasts, model artifacts,
source resources and snapshots, observation artifacts, read reports) against
the operating database, by 64-bit fingerprints (collision bound below 10⁻⁵ per
database). For the databases without unique identities, two further checks
found no populated table missing from the operating schema and no unique keys in
17 model-governance and participation tables. Row contents with the same key
were not compared. The run took 26 minutes and wrote nothing.

| Classification | Databases | Size | Meaning |
| --- | ---: | ---: | --- |
| Authoritative | 1 | 15.9 GB | `football` |
| Required | 4 | 30.7 GB | `postgres`; `football_p02_restore_check` (rollback restore for the running P02 rollout); `football_p02_rehearsal` and `_2` (evidence for open PR #191) |
| Needs reconciliation | 2 | 2.8 GB | `football_phase3a_serie_a_20260922`, `football_liga_f_recovery_20260910`: unique football history absent from operating (620 matches, 2.19 million events, 1,155 players from isolated StatsBomb work) |
| Needs review | 26 | 73.5 GB | Rehearsal and test databases holding rows absent from operating, mostly decision logs, provider mappings and observation artifacts generated by the rehearsal itself |
| Disposable, pending owner decision | 1 | 9.4 GB | `football_v4_integration_20261110`: no unique data found, but earlier documents ask to preserve it until separately reviewed |
| Disposable | 10 | 43.9 GB | `football_fr_teamname_restore_20261110`, `football_fr_context_restore_20261109`, `football_fr_scope_restore_20261109`, `football_fr_native_reference_20261109`, `football_architecture_v2_phase0_20261016`, `football_r3_final_baseline_20261015`, `football_v4_qualification_r02_20261101`, `football_r3_geography_guard_20261014`, `football_r3_status_test_20261015`, `football_pretraining_test` |

Unresolved: none of the 44 databases failed comparison.

No data was reconciled into the operating database. The unique rows found are
not evidence of valid missing data on their own: in the 26 review databases they
are decision, mapping and artifact rows that each rehearsal generated with its
own identifiers, and the operating database later produced its own versions.
Copying them would duplicate decisions. The two StatsBomb databases are the
exception: they hold genuine match and event history. Bringing it into operating
storage needs the existing canonical admission controls and an owner decision on
scope; the 11 November audit found their raw snapshots duplicated under
`.local/football-data/raw`, which would make them reconstructable rather than
unique.

Expected savings from the 10 disposable databases: 43.9 GB of
`pg_database_size` inside the PostgreSQL volume, plus 9.4 GB if the owner
releases the v4 integration database. Host savings depend on the Docker VM
returning freed blocks and are measured only after deletion. Nothing was
deleted in this stage.

Consumers and roles were checked in `.env`, the P02 runbook and tracked
evidence. Four disposable databases are cited by dated evidence
(`football_fr_teamname_restore_20261110`, `football_architecture_v2_phase0_20261016`,
`football_v4_qualification_r02_20261101`, and the v4 integration database).
Those documents record what was true on their dates and stay valid after
deletion; the deletion record itself becomes the follow-up evidence.

## Stage D — Admin-controlled resource management

Delivered in this branch: migration `202611120100_storage_resource_management`,
the Go resource manager (PostgreSQL, filesystem and Git worktree adapters,
database comparison, plans, fenced execution, interruption recovery), eight
Admin endpoints, and the Storage Management resource explorer. The procedure is
in [storage lifecycle operations](storage-lifecycle.md#resource-management).

Safety properties covered by tests on disposable databases, temporary
directories and temporary Git repositories:

- The authoritative database is protected without actions, cannot enter a
  plan, is refused for a forged plan, is refused by the database trigger on a
  direct SQL insert, and its protection row cannot be deleted.
- An unverifiable authoritative identity protects every database.
- Renaming a protected database or directory keeps its protection (OID and
  inode binding).
- A protection recorded after preview makes the plan stale; one recorded after
  admission blocks the pending operation and the database survives.
- Connected databases, dirty, unpushed or evidence-holding worktrees,
  symlinks, protected paths and directories in use are never eligible.
- Mixed batches keep independent eligible items and list blocked ones.
- Deletion, quarantine and restore of synthetic databases and directories
  succeed with verified absence and measured bytes. Path traversal, nested
  paths and a swapped inode are refused.
- Owner dispositions bind to an exact evidence digest and lapse when the
  evidence changes.
- Destructive endpoints require the owner credential.

Defect fixed on the way: PR #194's worktree discovery called
`git worktree list -z`, which Git 2.34 on this host rejects, so every review's
worktree inventory failed.

## Stage E — restored-database migration and browser verification

Not activated in operation. The operating database is unchanged at
`202611110100`; the running API was not rebuilt or restarted, because operating
migrations and deployment need the owner's authorization and the P02 rollout was
writing at the time.

| Check | Result |
| --- | --- |
| Migrations on a restored operating copy | A throwaway clone of `football_fr_teamname_restore_20261110` (operating as of 10 November, migration `202611100100`) migrated to `202611120100` in 1.9 s with all five pending migrations. The clone was dropped afterwards. |
| API against that copy (port 8090, no `.env`) | Registered the copy as authoritative, classified 45 databases and 12 worktrees, refused the authoritative database (403 without owner credential, 409 when forced into a plan), compared and deleted a synthetic database: verified absent, 7,911,103 bytes measured, matched by the cluster size drop. |
| Browser | Storage Playwright specs pass on desktop Chrome and iPhone 13 emulation, including axe WCAG 2.2 AA and 320 px reflow. The full e2e suite was not representative here because server rendering reached the throwaway API instead of the suite's mocks; CI runs it. |
| Repository checks | Go unit and disposable-database suites, `golangci-lint`, `go vet`, web lint, typecheck and 236 unit tests pass. |

Browser findings fixed: a StrictMode remount left the panel's mounted flag
false, the initial load used a timer that background tabs throttle, the
inventory endpoint could report a finished comparison before its evidence was
included, and absolutely positioned screen-reader text escaped horizontally
scrolling tables (`.table-scroll` is now positioned).

Activation steps once authorized, in order: merge this branch after P02 lands,
take the existing pre-change backup, apply migrations
(`202611110400`, `202611110500`, `202611120100`) with goose, rebuild and restart
the API, then open Storage Management and confirm the authoritative database
shows OID `16384`. Rollback for the schema is forward-only; the new tables are
additive and unused by other code, so the previous API binary keeps working
against the migrated database.

## Stage F — recovery gaps

All 159 declared gaps are explained and none of them is missing football data
([evidence](../evidence/storage-recovery-gaps-2026-11-12.json)). Nothing was
recovered because no original exists, and no registration was changed.
`FULL_RECOVERY` stays false.

| Gaps | Classification | Evidence |
| ---: | --- | --- |
| 89 | Synthetic test registration with a placeholder checksum | Registered checksums are one repeated hex character (`ccc…`, `fff…`, `555…`); their snapshots are `example/open-data` with `git_sha` `bbbb…`, `manifest_sha256` `aaaa…` and `acquired_at` 2026-01-01, created 29 August–5 September by test runs against the operating database |
| 69 | Synthetic test registration derived from those snapshots | 26 model artifacts, their 26 artifact files, 13 baseline forecasts and 4 Sprint 2 evaluation runs, all built only from `example/open-data` snapshots; no runtime model registration exists |
| 1 | Manifest never written | OpenFootball snapshot `7389bfe6-…` registered `openfootball/e6744429…/catalog.json`; its `manifest_sha256` is the SHA-256 of the path string (verified). The code at `246e24ba` registered the path but never wrote a file. Its 291 source resources are present. |

The 31 impossible checksum and length pairs are all synthetic: 30 two-byte
resources registered as `ccc…` and one one-byte dataset file registered as
`555…`.

Searches, all read-only: the three MatchForge data copies by registered path
(0 of 126 present); 31,271 same-named files across `.local`, `/private/tmp`
task directories, worktrees and mounted volumes, hashed (0 matches); and every
snapshot in the external Restic repository by content blob for all 72 distinct
checksums (0 matches; files under 512 KiB are stored as one blob whose ID is
their SHA-256).

Remediation needs owner decisions, not file recovery:

1. Retire the 158 synthetic registrations from the operating recovery scope
   through the existing artifact-retirement events
   (`202609051000_artifact_retirement_events`), preserving the rows and this
   evidence. Do not invent files or checksums for them.
2. Record a governed correction for the OpenFootball snapshot stating that its
   manifest checksum is a path digest with no file, or regenerate a real
   manifest under a new registration.
3. Re-run the recovery inventory. Only then can the next backup be
   classified as full recovery, and only if no other dependency is missing.

Until then each storage resource is judged on its own dependencies: these gaps
block nothing except the resources that register them.

## Stage H — automated maintenance

Implemented, not enabled. The existing storage schedule (daily dry-run review
and verified backup) gains narrowly scoped automatic cleanup that runs only when
the reviewed policy contains an `automatic_cleanup` rule: purge expired
quarantine or delete aged children of an owner-declared disposable root, bounded
per run and rate-limited to the review interval. Databases, worktrees and
review-class roots are excluded by validation and selection. The operating API
has no policy configured (`MATCHFORGE_STORAGE_POLICY` is empty), so nothing
runs. Tests cover selection bounds, root scoping, validation and an end-to-end
run that deletes only the aged disposable child, spares the protected and fresh
ones and respects the interval.

Recommended first policy once deployed: managed roots for regenerable output
only (for example task `node_modules`, `.next`, `target` and `.venv` trees
outside the primary checkout, and `.local/backup-staging`), class `disposable`,
with the 9 November audit's evidence directories listed as `protected_paths`.
The evidence trees under `.local` (about 131 GB) should be a `review` root so
each directory needs its own owner disposition.
