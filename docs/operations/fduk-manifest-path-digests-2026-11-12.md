# Football-Data.co.uk manifest path digests — 12 November 2026

Dated findings for 47 `football_data_uk` source snapshots whose `manifest_sha256` is the
SHA-256 of the `manifest_path` string instead of a checksum of file bytes. This is a
separate deliverable from the recovery-scope dispositions in
[recovery](../recovery.md#recovery-scope-dispositions) (160 synthetic retirements and one
OpenFootball correction). It does not block their rollout. Nothing here authorizes a
migration or a write to the operating database; each needs its own owner decision.

Evidence: [`fduk-manifest-path-digests-2026-11-12.json`](../evidence/fduk-manifest-path-digests-2026-11-12.json)
(SHA-256 `e912287d773cdad3ff2098a3fdd88a68d1184db5395a5cdc6c3ac1085f197da2`), exported by
`python -m scripts.source_manifest_path_digest_audit` in a session with
`default_transaction_read_only=on`. The operating database was at migration
`202611120200`. No registration, file or backup changed.

## Findings

| Check | Result |
| --- | --- |
| Path-digest snapshots by provider | `football_data_uk` 47 of 68, `openfootball` 1; no other provider |
| Created | 30 September to 7 October 2026, all `status = validated`, `source_kind = REAL_PROVIDER` |
| Writer | `HistoricalBackfillStore.ensure_snapshot` registered `sha256(manifest_path)` |
| Fix | Commit `55a7e35d` (13 October) writes `HistoricalSourceManifestV1` files and registers revision `manifest-v1:<revision>:<manifest bytes sha256>`. The 20 later Football-Data.co.uk snapshots use it; the first was created on 14 October. |
| What `manifest_path` names | The raw provider file itself, named by its content checksum, for example `football_data_uk/2010-2011/<sha256>.zip`. No separate manifest document exists or was intended. `source_revision` equals that checksum. |
| `RAW_FILE_PATH_DIGEST_RESOURCE_BOUND` | 45 snapshots. Each has one `source_resources` row whose `sha256` and `size_bytes` equal the bytes at `manifest_path` on disk. |
| `RAW_FILE_PATH_DIGEST_SIBLING_BOUND` | 2 `https://…/fixtures.csv` snapshots with no resource rows. Each shares provider, path and revision with exactly one `http://…/fixtures.csv` snapshot whose resource matches the file bytes. |
| Unverified | 0 |
| Backup and restore | Not blocked. `source_manifest_reference` and `legacy_source_path` in `scripts/recovery_files.py` already resolve each path to the raw file and verify it with the resource checksum. The snapshot registration itself is captured as a path identity with no byte checksum. |

Rows that reference the 47 snapshots:

| Table and column | Rows |
| --- | ---: |
| `provider_mapping_history.source_snapshot_id` | 242,514 |
| `match_provider_mappings.source_snapshot_id` | 241,442 |
| `product_team_match_history.source_snapshot_id` | 235,923 |
| `team_provider_mappings.source_snapshot_id` | 1,028 |
| `product_identity_admissions.source_snapshot_id` | 927 |
| `source_resources.source_snapshot_id` | 45 |
| `competition_provider_mappings.source_snapshot_id` | 44 |
| `product_source_result_conflicts` (incoming / existing) | 8 / 2 |

No table references the 45 resource rows. Re-registering or deleting these snapshots would
touch about 720,000 dependent rows, so the registrations stay as they are.

## Why the OpenFootball correction does not fit

`source_manifest_corrections` (`MANIFEST_NEVER_WRITTEN_PATH_DIGEST`) records that a manifest
file was never written: the OpenFootball `catalog.json` does not exist. Here the file at
`manifest_path` exists and is fully verified by a registered resource checksum. Recording
these as "never written" would be false, so they need their own correction kind.

## Proposed correction

Migration `202611120300_source_manifest_raw_file_bindings` adds the append-only table
`football.source_manifest_raw_file_bindings` with binding kind
`MANIFEST_PATH_IS_RAW_RESOURCE`. One row per snapshot binds:

- the snapshot's `manifest_path` and path-digest `manifest_sha256`, as registered;
- one `source_resources` row, with its `sha256` and `size_bytes` copied and checked;
- the evidence file and its SHA-256, the owner decision reference, the record time and the
  code commit.

The database accepts a row only when the snapshot matches the row, its revision is not
`manifest-v1:` and equals the resource checksum, the path is named by that checksum, and the
resource's checksum and size match. A snapshot may bind another snapshot's resource only when
it has no resources of its own and both share provider, path and revision. A binding and a
never-written correction for the same snapshot are mutually exclusive. Rows cannot be updated,
deleted or truncated. The snapshot and resource rows are not changed and no checksum is
supplied.

`python -m scripts.source_manifest_bindings --decision-reference <ref> --code-commit-sha <sha>`
validates the pinned evidence and prints the count (47). `--apply` writes to
`DATABASE_URL`; a retry with the same decision verifies the existing rows. Applying the
migration or the bindings to the operating database needs a separate owner decision.

Recovery code does not read the bindings yet. A follow-up could let
`source_manifest_reference` capture a bound snapshot with the resource checksum and size
instead of a path identity.

## Proposed guard

Migration `202611120400_source_snapshot_path_digest_guard` is independent of the binding
migration. A trigger rejects an insert into `football.source_snapshots`, or an update of its
manifest columns, when `manifest_sha256` equals the SHA-256 of `manifest_path`. Existing
legacy rows stay readable and their status can still change. Two integration fixtures that
model pre-guard legacy rows now seed them with `session_replication_role = replica`, as other
fixtures already do for seeding.

## Owner decisions needed

1. Whether to apply `202611120300` and record the 47 bindings on the operating database.
2. Whether to apply the `202611120400` guard. It does not depend on the first decision.
