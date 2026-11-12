# Remaining non-operating databases: review, 12 November 2026

After the 11 rehearsal databases in
[PR 214](https://github.com/sir-radar/match-forge/pull/214) were deleted, 23
non-operating databases (about 58 GB) were still in the cluster. None of them had a
Storage Management comparison, so all 23 were `REVIEW_REQUIRED`. On owner instruction
all 23 were compared from the Admin page on 12 November (every comparison
`SUCCEEDED`). This review explains the unique rows in 18 of them. Every review query
ran with `default_transaction_read_only=on`.

Evidence: [remaining-database-unique-rows-2026-11-12.json](../evidence/remaining-database-unique-rows-2026-11-12.json).

## Comparison results

| Result | Databases | Size |
| --- | --- | --- |
| `ELIGIBLE` (no unique rows) | `football_p02_restore_check`, `football_v4_integration_20261110`, `football_fduk_binding_rehearsal_20261112` | 28.9 GB |
| Genuine unique history, not reviewed here | `football_phase3a_serie_a_20260922`, `football_liga_f_recovery_20260910` | 2.8 GB |
| Reviewed below | 18 databases | 28.4 GB |

`football_fduk_binding_rehearsal_20261112` is eligible, but it is the restore point
cited by the source-manifest binding migration applied on 12 November. Keep it until
that migration has run cleanly. The two history databases hold 620 matches, about
2.19 million events and 1,155 players from isolated StatsBomb work that the operating
database does not have. They need reconciliation or a separate owner decision.

## Method

Each row absent from `football` by primary key was matched by natural key: fixture for
history decisions; report kind, scope and horizon for read reports; fixture and model
for forecasts; semantic hash, then provider match, for mapping decisions; artifact
hash, then source record, for observation artifacts, with a separate check that the
observation's raw source bytes are in `football.source_resources`; provider, identity
and revision for source snapshots; content hash for source resources; provider and
provider id for mappings. For the two experimental acquisition databases, every raw
resource and observation file was also checked on disk by SHA-256 file name.

## Findings

| Group | Databases | Size | Unique rows | Finding |
| --- | --- | --- | --- | --- |
| Operating equivalent | `football_p02_rehearsal_2`, `football_p02_rehearsal`, `football_architecture_v2_shadow_20261016` | 28.0 GB | 3,446,105 | All P02 history decisions (29,339), read reports (263,149) and mapping decisions (20) match by natural key. The 3.15 million shadow observations were derived from raw bytes that `football` retains. The 3 forecasts are explained below. |
| Derived from operating raw source | `football_v4_phase14_shadow_20261101`, `football_v4_unblocking_r02_20261102`, `_r02_replay_`, `football_v4_identity_recovery_projection_20261102` | 0.13 GB | 84,640 | Observation artifacts only; every raw source is in `football`, so they can be regenerated. |
| Experimental acquisitions | `football_v4_access_r04_20261102`, `football_v4_expansion_r03_20261101` | 0.18 GB | 220,099 | `EXPERIMENTAL_ONLY` fetches (R04: fbref, sofascore, clubelo; R03: espn, flashscore, soccerway, understat, whoscored). All 3,337 raw resources and 213,425 observation files are on disk under `.local/shadow-v4/`, so the databases are registries only. |
| Synthetic test fixtures | 3 `v4_identity_recovery*`, 3 `r3_contract*`, `r3_final_test`, `r3_scoped_history`, `restore_test_3f302f…` | 0.16 GB | 1,094 | Placeholder teams ("Home 6"), the "Calendar test" competition, fabricated pitchapi ids (`l_Grow02`, `l_Cach01-2099`), StatsBomb snapshot `2222…`, recovery-test files. Not football data. |

**3 forecasts** in `football_p02_rehearsal` (`MVP_FORECAST`) were generated inside the
rehearsal on 11 November for fixtures that kicked off that day. `football` never
forecast those fixtures (two are now `AWARDED`, one `FINISHED`). No operating read
report and no repository document contains their IDs or semantic hashes. They are
rehearsal output, not issued forecasts.

## Proposal

- Record a `UNIQUE_DATA_NOT_REQUIRED` disposition, then delete, for 17 databases
  (about 28.3 GB). The evidence file holds the proposed text for each, bound to its
  comparison `evidence_sha256`.
- Delete `football_p02_restore_check` and `football_v4_integration_20261110` (18.1 GB).
  Both are already eligible.
- Keep `football_v4_access_r04_20261102` (151 MB) until the R04 handoff in
  `docs/project-status.json` (`provider_access_recovery.required_next_action`) closes.
  Its files stay on disk, but this database is the only registry linking them.
- Do not delete the files under `.local/shadow-v4/`. They are the retained copy of the
  experimental acquisitions.

Comparisons expire after seven days or when a database's physical size drifts.
Recording dispositions and deleting are separate owner approvals. Nothing was recorded
or deleted in this review.
