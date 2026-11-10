# Storage cleanup proposal — approval required

This is a proposal only. No protected file, database, source, artifact, forecast,
backup or original evidence is deleted, rewritten or archived for eviction by the
foundation task. Complete recovery and current reference safety are prerequisites
to any later cleanup. Automatic pruning remains disabled.

Reuse the 10 November inventory and receipts from
`docs/architecture/unified-redesign-2026-11-10/storage-recovery.md`. Their file,
PostgreSQL, Docker and APFS accounting overlaps; proposed savings are not a sum
of independently reclaimable physical bytes. No second four-million-file walk
was performed. Cache/DB sizes below are dated measurements, not current growth
or a deletion decision.

| Candidate | Measured size / possible logical savings | Dependencies and recovery status | Risk and required action |
| --- | --- | --- | --- |
| One duplicate `RETAINED_SEASON_TEAM_IDENTITY_REVIEW.json` report | Each file 1,913,464,815 bytes; at most one file's logical size | Both hashes matched `472c519ecfc9a2592cba008500cd9c237c414211129c4c727c3e75ac3040ae31` in the retained dedup receipt. They occur under the R3 completion's `internet-20261015T103925Z/` root and its `current_impact_round4/` child. Current named-file metadata is rechecked separately. | Protected remediation evidence. Inspect both path consumers, independent backup and current checksums before proposing any path substitution/removal. APFS extent savings are unverified. Explicit owner approval required. |
| Experimental `football_v4_integration_20261110` database | Earlier `pg_database_size`: 9,391,486,655 bytes | Experimental integration/recovery evidence; not the operating database. Current dependencies, restore independence and retention are unresolved. | High risk until its exact evidence consumers and a verified restore are established. No drop is authorized; do not include it in the operating recovery scope merely because it exists. |
| Existing `.local/backups` dumps | Earlier 3,535,155,326 bytes across 13 files | Older recovery points may contain the only original bytes for current missing-source cases. | No blanket deletion. Match manifests, required checksum originals and verified independent recovery before considering a redundant copy. Preserve latest and previous good points. |
| `.local/go-mod-cache` and `.local/uv-cache` | Earlier allocated file bytes: 1,227,657,216 and 1,012,256,768 | Reconstructable dependency caches only if locks, pinned tools and required offline reconstruction remain available. Active build/test processes can hold them. | Bounded later cache cleanup may be suitable after an active-job check and owner approval. Current footprint and real reclaimability must be measured then. |
| Temporary/remediation directories mixed with `.local/remediation` | No safe deletion total established | That 67.14 GB logical category includes protected original/evaluation/rehearsal evidence and live references. Names and age do not prove disposal eligibility. | Separate exact owned temporary files from required evidence using existing manifests and job references. Do not delete or compress originals in place. |

For each later proposed deletion, record the exact resource, current size and
checksum/identity, every consumer/reference, active-job pins, independent verified
recovery point, restore result, expected savings, failure/rollback procedure and
explicit approval. A missing original, unknown reference or last good copy blocks
deletion. Preserve the current champion, historical identities/decisions, source
bytes and published forecasts regardless of space pressure.

For the 1 TB external destination, first measure its actual capacity/free space
and complete selected recovery dataset, then initial and incremental repository
growth. Start with latest plus one earlier independently verified point when
capacity permits. Additional monthly retention has no sustainable numeric answer
until those measurements exist; no fixed count justifies destructive pruning.
