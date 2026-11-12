# Storage audit and dispositions, 13 November 2026

Dated record of the storage audit that follows the
[remaining-database review](remaining-database-review-2026-11-12.md) and the
`VERIFIED_GOVERNED_SCOPE` backup `02376823`. It covers every remaining database and
the host resources around them. All queries ran with
`default_transaction_read_only=on`; the audit recorded, compared, moved and deleted
nothing. Evidence: [storage-audit-2026-11-13.json](../evidence/storage-audit-2026-11-13.json).

## Deletions already made through Storage Management

On 12 November Storage Management deleted 43 databases and 2 worktrees in 45
operations, all `SUCCEEDED`, with 179.9 GB measured. The first 25 are already
recorded ([candidate deletion](../evidence/storage-candidate-deletion-2026-11-12.json),
[rehearsal review](rehearsal-database-review-2026-11-12.md)). The last two batches
were made with the owner credential after the remaining-database review and were
not yet recorded in the repository:

| Batch (UTC) | Databases | Measured | Basis in the storage registry |
| --- | --- | --- | --- |
| 19:40 | `football_v4_integration_20261110`, `football_p02_restore_check`, `football_fduk_binding_rehearsal_20261112` | 30.3 GB | Current comparison `NO_UNIQUE_CANONICAL_IDENTITIES` (eligible without disposition). The binding rehearsal was deleted after migration `202611120300` and the 47 bindings were applied and verified. |
| 20:29 | The 17 databases proposed in the remaining-database review, including both P02 rehearsals | 28.3 GB | Owner disposition `UNIQUE_DATA_NOT_REQUIRED` recorded at 20:28 for each, bound to its comparison digest |

Each operation was verified absent before it was marked `SUCCEEDED`. Per-database
sizes, digests and dispositions are in the evidence file. The brief's "26 rehearsal
databases (~73.5 GB)", `football_v4_integration_20261110`,
`football_fduk_binding_rehearsal_20261112` and the P02 rehearsal and restore
databases are therefore already gone. The P02 rollback dumps remain as files (below).

## Remaining databases

| Database | Size | Classification | Disposition proposed |
| --- | --- | --- | --- |
| `football` (OID 16384) | 16.1 GB | Protected, authoritative | Keep. Permanently protected. |
| `postgres` | 8 MB | Protected, system | Keep. |
| `football_phase3a_serie_a_20260922` | 1.73 GB | Review required: 1,384,145 unique identity rows (380 matches, 1,353,739 events, 699 players) | **Preserve** |
| `football_liga_f_recovery_20260910` | 1.07 GB | Review required: 854,091 unique identity rows (240 matches, 835,429 events, 456 players) | **Preserve** |
| `football_v4_access_r04_20261102` | 0.16 GB | Review required: 210,251 unique rows (3,265 raw resources and snapshots, 203,721 observation artifacts) | **Preserve** until the R04 handoff closes |

No session was open on any non-operating database. The comparisons were made on
12 November and expire after seven days.

### StatsBomb databases: not reconciled into `football`

The two StatsBomb databases hold genuine football history that `football` does not
have. They must not be reconciled into it. Both were built under owner decisions that
require isolation: the Serie A qualification was
[authorized as isolated publication](../evidence/owner-decision-authorize-phase3a-serie-a-isolated-qualification-2026-09-22.md)
for research use, with the normal database used only for read-only identity overlap,
and the [Liga F recovery](../evidence/statsbomb-liga-f-isolated-exact-source-recovery-2026-09-11.json)
was an isolated exact-source recovery. Copying them into the operating database would
break that firewall and needs a new owner decision.

Their sources are intact. Every file listed in the four manifests of each tree was
re-hashed: 1,142 of 1,142 files under `.local/phase3a-serie-a-qualification-20260922`
and 722 of 722 under `.local/football-data-liga-f-recovery-2026-09-10` match, none
missing. The raw data is StatsBomb open data pinned to Git SHA
`4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`, so it can also be fetched again. The
databases, however, hold the isolated canonical identities and dataset lineage built
from those files, and **none of the three databases or their file trees is in the
governed backup**. The 65 retained locations of snapshot `02376823` cover the
Football-Data.co.uk originals, the Sprint 2 reports and the recovered originals only.
They are not independently recoverable as they stand, so none is disposable.

## Host resources

| Resource | Size | Finding | Proposal |
| --- | --- | --- | --- |
| `.local/remediation/matchforge-audit/phases/R3` | 52.1 GB | 40 repeated identity-review JSON rounds (0.9–1.8 GB each, 42.9 GB) from 14–16 October | Pack with `matchforge-storage -action pack` (deduplicated, compressed, verified), verify a restore, then delete the originals. Needs owner approval. |
| `.local/remediation/matchforge-architecture-v2` | 25.0 GB | Architecture V2 phase evidence | Same archive procedure; owner approval. |
| 14 operating `pg_dump` files | 24.5 GB | Pre-change rollback dumps, 30 September to 12 November, each cited by its own record | Keep the 12 November dumps. Decide retention for the older ones, all predating snapshot `02376823`. Owner approval. |
| `.local/football-data` | 11.4 GB | Football-Data.co.uk originals; covered by the governed backup | Keep. |
| `.local/shadow-v4` | 8.8 GB | Retained copy of the R03/R04 experimental acquisitions | Keep with the R04 database. |
| Regenerable caches (`go-cache`, `go-mod-cache`, `uv-cache`, `target`, `web/.next`, `node_modules`) | about 5.5 GB | Build output | Declare as `disposable` managed roots with an `automatic_cleanup` rule. Owner approval. |
| Docker (OrbStack 2.2.5) | 22.6 GB used in the VM | PostgreSQL volume 20.2 GB, images 1.2 GB | The VM keeps nothing of the dropped databases: its filesystem uses 22.6 GB. |
| Unused Docker images | 0.43 GB | `sam/emulation-nodejs14.x` (4 years old), `alpine:3` | Remove with `docker image rm`; no volume or service is affected. Owner approval. |
| `crypto-analyser_postgres_data` volume | 0.92 GB | Unattached, belongs to another project | Outside MatchForge; owner's decision. |
| Docker Desktop `Docker.raw` | 4.8 GB allocated | Left from an earlier Docker Desktop install; OrbStack is the running runtime | Outside MatchForge; owner's decision. |
| `football-gate-a` and `matchforge-global-audit-pg` clusters | 0.15 GB | Unchanged since the [consolidation report](storage-consolidation-2026-11-12.md) | Keep until their owners are resolved. |

The host data volume had 372.9 GB free of 994.7 GB at the audit. Worktrees: the
primary checkout and this task's own worktree only. No test database carries a test
marker without a registration.

## Activity counters on idle databases

Between 21:22:55 and 21:38:48 UTC each idle non-operating database gained 32
committed transactions and about 26,000 returned rows with no client session:
autovacuum workers visit every database each minute. Client sessions, session time,
row writes and temporary files did not change. The five-hour lifecycle policy
therefore measures activity from those, not from transaction or read counters.

## Owner decisions needed

1. Record `PRESERVE` for `football_phase3a_serie_a_20260922`,
   `football_liga_f_recovery_20260910` and `football_v4_access_r04_20261102`, and
   decide whether to add the three databases and their file trees to the governed
   backup scope. Until then they are protected only by being kept.
2. Approve archiving the R3 and Architecture V2 evidence trees (up to 77 GB) through
   the verified pack, restore-check and delete procedure.
3. Decide retention for the 12 operating dumps older than 12 November (19.4 GB).
4. Approve declaring the build caches as disposable managed roots with automatic cleanup.
5. Approve removing the two unused Docker images; decide on the two resources outside
   MatchForge.
6. Approve the five-hour lifecycle policy rollout (migrations `202611130100` and
   `202611130200`, release and policy file) described in
   [storage lifecycle operations](storage-lifecycle.md).
