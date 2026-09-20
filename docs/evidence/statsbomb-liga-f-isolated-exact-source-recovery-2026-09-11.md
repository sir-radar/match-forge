# StatsBomb Liga F isolated exact-source recovery — 2026-09-11

Status: `SELECTED_REPLICATION_CORPUS_QUALIFICATION_FAILED`

The isolated recovery preserved the historical truncated manifest and its
quarantined bytes unchanged. A new isolated data root and PostgreSQL database
published fresh source manifests from the pinned StatsBomb revision
`4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`.

All 480 required detail resources passed path-bound identity, selected-match
membership, Git blob, SHA-256, and existing parser validation. The isolated
detail manifest SHA-256 is
`d1c13b1b5b11f94e4022beb71e7a52d19a209460ab2ac20501a78c535b6bd6d2`.
The isolated detail source snapshot is
`01a089cc-db5f-7f42-bf7a-419f8eaec2d8`.

Canonical publication produced 240 matches and dataset
`f5cb2724-6400-540d-aa12-44ba25f27369`. Its immutable dataset-byte integrity
check passed. Lifecycle, kickoff, and corner-label claims each produced 240
records and each verified idempotently on a repeat run.

Ticket 08 failed without creating forecasts or analyzing outcomes. Under the
existing point-in-time contract (`minimum_team_history=10`,
`minimum_competition_history=100`), the 240-match corpus yields 102 excluded
warm-up targets and 138 structurally eligible targets, not the frozen required
100 and 140. The qualification route stops here.

The machine-readable record is
`statsbomb-liga-f-isolated-exact-source-recovery-2026-09-11.json`.
