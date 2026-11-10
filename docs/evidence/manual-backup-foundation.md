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
