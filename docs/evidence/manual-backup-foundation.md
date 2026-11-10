# Manual backup foundation implementation

Authorized scope: P00-01, P00-02, P01-01, P01-02 and manual Admin backup with
30-day reminders. Implementation branch: `ft/manual-backup-foundation`.
Operating activation, migrations, model changes, source acquisition, destructive
retention and cleanup remain unauthorized. No active Wayfinder map is involved.

## Planning handoff

All four investigation commits (`f86aec1`, `39a4b21`, `f254008`, `34a552f`)
are ancestors of main `01eed6c`, merged through
[PR #183](https://github.com/sir-radar/match-forge/pull/183). Existing baseline,
followup, final-read, correction and compression receipts and final aggregate log
match their recorded SHA-256 checksums. ADR 0005 now accepts Option B for the
owner-selected scope; the investigation's historical proposed text stays intact.
The companion F0–F11 plan and Probability Filter scope remain independent.

## P00-01 — operating release truth

Read-only observation: 10 November 2026, 10:33:54 UTC. Command:

```sh
set -a; . ./.env; set +a; . ./scripts/toolchain.sh
uv run --locked python -m scripts.foundation_release --output .local/foundation/release.json
```

- API is operating (`healthz=ok`, `readyz=ready`), but commit, lock checksum and
  worktree identity are `unknown`; version is `dev`. Deployed commit is unproven.
- PostgreSQL 18.6, database `football`; schema owners `football` and
  `pg_database_owner`. Extensions: btree_gist 1.8 and plpgsql 1.0.
- Latest applied migration: `202611100100`; `202611100200` is pending. No
  operating migration ran. Goose has versions, not applied historical SQL hashes;
  current repository checksums are captured without claiming historical parity.
- Runtime registry has zero registrations. 18,162 forecast records reference
  approved champion `e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4`
  across the existing baseline and rolling10 algorithms. The checked-in champion
  hash matches. No model or forecast changed.
- All 13 stage routes remain LEGACY. V2 code/test evidence is experimental,
  not operating adoption.
- FotMob and PitchAPI each have one running sync and a current provider lease.
  One historical-acquisition lease expired on 6 November; no reclaim was attempted.
  Operational scheduling is 30 seconds; history scheduling is disabled.
- Diagnostics use a repeatable-read, read-only transaction with statement/lock
  limits and rollback. HTTP GETs are separately timed observations.

Focused verification: two release/migration tests, Ruff and strict mypy passed.
The initial diagnostic was denied localhost access by the sandbox; the authorized
read-only retry passed. Full aggregate is deferred until final code changes.

## P00-02 — resource baseline and proposed budgets

Read-only sample started at 10:35:23 UTC. Private receipt:
`.local/foundation/resources.json`. It records `sysctl`, `vm_stat`, `ps`,
`docker stats --no-stream`, `shutil.disk_usage`, four bounded PostgreSQL queries
and five consecutive GETs for each path below. No load generator or provider
request ran. The final console summary failed to encode a PostgreSQL Decimal;
the JSON receipt had already been written successfully and was inspected directly.

| Measurement | Actual observation |
| --- | --- |
| Host | 17,179,869,184 bytes RAM; eight logical CPUs |
| Internal filesystem | 994,662,584,320 total; 263,648,190,464 free bytes |
| Operating DB | 14,027,781,823 bytes, including indexes/TOAST |
| WAL | 117,440,512 bytes; point sample, not a growth rate |
| PostgreSQL container | 2.71% sampled CPU; 287.3 MiB RAM |
| Redis container | 3.09% sampled CPU; 6.922 MiB RAM |
| DB activity | Two active, seven idle connections at observation |
| Temp counters | 52,225 files / 944,104,966,563 cumulative bytes; not simultaneous workspace |
| `/version` | 108 bytes; p50 0.694 ms, p95/p99 25.47 ms |
| Today's fixtures | 109,453 bytes; p50 16.83 ms, p95/p99 172.35 ms |
| Sync Admin | 63,599 bytes; p50 2,567.84 ms, p95/p99 4,134.36 ms |

Percentiles use nearest rank over only five samples; p95/p99 are the sample
maximum, not a production SLO. Concurrent existing workers affect these readings.
Database-wide block/transaction counters cannot attribute queries to a request;
per-request query counts and provider fairness latency remain UNVERIFIED. Current
workers and queue ages are retained in the release/resource receipts, without
claiming fairness from a point sample. Current Admin polling is 2.5 seconds while
active, 60 seconds idle and 120 seconds hidden; polling does not authorize backups.

Reuse the earlier 4,036,851-file inventory (SHA-256
`2497ab2521c81252ceef8276c32207a0b132699922f46850d7d3505887563a39`), not a new
recursive scan. Its 123.8 GB logical files, PostgreSQL and Docker populations
overlap; they are never summed into a recovery estimate. No comparable growth
time series exists. `/Volumes` contains only Macintosh HD and Recovery; external
drive capacity, filesystem, encryption and repository growth remain unverified.

Initial release proposals: one manual backup at a time, one pg_dump worker, two
Restic CPUs/readers, low process priority, and a 20% destination free-space
planning reserve. Preflight must include dump staging plus exact referenced file
sizes and independent restore workspace. No missing dependency may be omitted to
meet a budget. Peak RAM, full-scope backup/RTO and destination growth must be
measured before operating activation; these proposals are not passing targets.
Thirty-day manual backups cannot achieve the previously desired 24-hour RPO.

## P01-01 — snapshot and file recovery

The existing baseline command now supports `--complete-recovery`, reusing its
snapshot export, table digest and cutoff helpers. Recovery capture retains
database globals, a full dump, Git application archive and the exact registered
file set. Incomplete capture cannot become a passing recovery record. The old
baseline workflow remains compatible. Procedures and scope are in `docs/recovery.md`.

Executed focused checks: 19 baseline/file tests passed; Ruff formatting, lint and
complexity plus strict mypy passed for new recovery modules. The disposable
integration test passed in 14.19 seconds. It proves full table/migration and
historical-cutoff parity, original-source bytes after the source root is moved,
checksum corruption rejection, and isolated restoration. A separate networkless
PostgreSQL container replayed globals and the dump with original ownership;
only the test's own container/volumes and random databases were removed.

Earlier test failures exposed lost credentials in the restored connection,
a misclassified inline history column and PostgreSQL's temporary init-server
readiness. These were fixed directly; checks were not skipped or weakened.
The ordinary `verify-restore` drill deliberately does not apply global roles to
the existing cluster; fresh-cluster global restoration is a separate procedure.
No full operating backup or operating restore has run. Missing original sources,
unregistered custom roots and hardware verification remain fail-closed blockers.
