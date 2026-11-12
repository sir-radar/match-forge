# Rehearsal databases with unique rows: review, 12 November 2026

After the verified `RECOVERABLE_ONLY` backup of `football` (snapshot `bb97d6fd`), Storage
Management compared 12 older rehearsal and restore databases with the operating database.
One was eligible and was deleted. The other 11 (about 66 GB) hold rows absent from
`football` by primary key, so Storage Management requires an owner disposition before
deleting them. This review explains those rows. Every review query ran with
`default_transaction_read_only=on`.

Evidence: [rehearsal-database-unique-rows-2026-11-12.json](../evidence/rehearsal-database-unique-rows-2026-11-12.json).

## Method

Each row absent by primary key was matched to `football` by natural key: the fixture for
history decisions, the provider entity for identity admissions and provider mappings, the
canonical and member fixture for resolutions, the provider match for mapping decisions,
and the fixture and model for forecasts. A match means the operating database made its
own decision about the same thing; the rehearsal row is a duplicate with a different ID.

## Findings

| Database | Size | Unique rows | With an operating equivalent |
| --- | --- | --- | --- |
| `football_fr_native_restore_20261109` | 8.6 GB | 438 | 438 |
| `football_fr_native_restore_20261103` | 8.3 GB | 449 | 449 (incl. 13 rehearsal forecasts, below) |
| `football_fr_rollout_restore_20261103` | 8.2 GB | 1,165 | 1,165 |
| `football_fr_execution_20261103` | 8.0 GB | 1,165 | 1,165 |
| `football_ds_populated_7bd6703e…` | 7.8 GB | 1,246 | 1,246 |
| `football_r3_final_rehearsal_20261015` | 4.4 GB | 51,414 | all (144 mapping decisions by provider match) |
| `football_r3_internet_verified_20261015` | 4.4 GB | 94,892 | all (59 by provider match) |
| `football_r3_internet_20261015` | 4.2 GB | 20,055 | all (3 matches covered by openfootball, below) |
| `football_r3_coverage_20261015` | 4.2 GB | 7,577 | all (24 by provider match) |
| `football_r3_identity_20261014` | 3.9 GB | 17,376 | 17,376 |
| `football_r3_completion_20261014` | 3.9 GB | 241,107 | 241,107 |

**13 forecasts** in `football_fr_native_restore_20261103` were generated inside the
rehearsal at 2026-11-03T22:47Z (`MVP_OWNER_AUTHORIZED`). None exists in `football`, none
is referenced by a read report, and the operating database holds its own 40 later
forecasts for the same fixtures. They are rehearsal output, not issued forecasts.

**3 matches** in `football_r3_internet_20261015` are UEFA Champions League 2024-25
fixtures from football-data.org (`524100`, `524102`, `524119`). All three results are in
`football` through openfootball with regulation scores: Liverpool 0-1 PSG, Atlético 1-0
Real Madrid, Inter 4-3 Barcelona. The rehearsal stored 1-5 and 3-4 for the first two,
which equal the regulation score plus the shoot-out penalties, so those rows are wrong as
match goals. Their raw source snapshot (`48a18d7b…`) and resource are retained in
`football`.

## Proposal

Nothing in these 11 databases is operating history or the only copy of a source. Each
can receive an owner disposition in Storage Management and then be deleted through its
preview, owner credential and typed confirmation. The evidence file holds the proposed
disposition text for each database, bound to its comparison `evidence_sha256`.

The running API (`cefc805`) predates the PR 200 digest change, so a disposition can lapse
when PostgreSQL changes a database's physical size. Record each disposition and delete
promptly, or deploy a release that includes PR 200 first. Recording dispositions and
deleting are separate owner approvals.

## Outcome

On owner instruction, the 11 `UNIQUE_DATA_NOT_REQUIRED` dispositions were recorded at
15:22 UTC, bound to the evidence digests above. Storage Management batch `83af97f3`
deleted all 11 between 15:30 and 15:39 UTC (11 operations `SUCCEEDED`, about 66.1 GB
reclaimed). That batch was submitted outside this review session; a preview afterwards
found every resource already absent, and the PostgreSQL catalog confirms it.
