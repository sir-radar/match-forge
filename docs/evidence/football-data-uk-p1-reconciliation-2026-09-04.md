# Football-Data.co.uk Phase 1B P1 reconciliation

Status: local acceptance-database evidence

The P1 score reconciliation policy is
`FootballDataUkPhase1BScoreReconciliationV1`: exact score-pair tolerance,
eligible providers `statsbomb_open_data` and `football_data_uk`, and
`quarantine` escalation. It never selects a provider automatically.

## Real P1 corroboration

All ten context-resolved P1 matches had equal full-time score pairs in the
existing StatsBomb observation and immutable Football-Data row. Each result was
`CORROBORATED`; no reconciliation conflict was created.

| P1 row | Canonical match ID | Corroborated score |
| ---: | --- | --- |
| 1 | `01a051db-5e39-7994-9706-8452d7ebc0fc` | 0-1 |
| 2 | `01a051db-5ccd-7471-9e9e-7c7fb91e6b0e` | 2-2 |
| 3 | `01a051db-67fb-775b-b4c7-bd8592992f98` | 2-2 |
| 4 | `01a051db-637c-703c-accf-e6063aaceb7b` | 4-2 |
| 5 | `01a051db-5d4b-7572-bfdc-a5d3312188ce` | 1-0 |
| 6 | `01a051db-5e8e-70d4-acf9-d9329b005f4e` | 1-3 |
| 7 | `01a051db-5eb2-734c-ae69-4ad61c2c2779` | 0-2 |
| 8 | `01a051db-5db9-7ad5-9c05-308ddfead520` | 2-2 |
| 9 | `01a051db-5ad6-7962-a66d-64a8a4b1b1a4` | 0-1 |
| 10 | `01a051db-5f08-7058-b134-a7c00fde5498` | 0-3 |

## Synthetic discrepancy fixture

The frozen acceptance fixture compared synthetic score pairs `(1, 0)` and
`(1, 1)`. It produced `QUARANTINED`, retained both observation references, and
selected no winner. PostgreSQL conflict ID:
`01a06e50-3756-7836-b66f-92e2c4bc76d9`; conflict SHA-256:
`2f76ac98a735a08a0d0720d6dfb8f9231473ddf81c5e104af3d35e105218aad6`.
An identical retry returned `verified_existing`.

No canonical observation or `CanonicalChangeSetV1` was emitted. Sprint 2
remains `FAIL`; Phase 3 remains blocked.
