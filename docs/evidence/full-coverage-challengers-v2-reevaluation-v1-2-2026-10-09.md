# Full-coverage V2 replacement holdout

Protocol: `MATCHFORGE_FULL_COVERAGE_CHALLENGERS_V2_REEVALUATION_V1_2`

Disposition: `FAIL_CLOSED_PROTOCOL_VIOLATION`

The corrected Git/hash preflight passed, all frozen V2 artifacts reproduced
byte-for-byte, and the tracked execution state was consumed before outcome access.
The replacement HOLDOUT contains 500 fresh targets: 404 champion-eligible and 96
champion-ineligible targets across three competition domains.

Evaluation stopped while constructing the first point-in-time snapshot. Retained
canonical history contains two fixture IDs for the same teams and kickoff from one
OpenFootball snapshot, under different competition identities. The Elo contract
correctly rejected this impossible history with `one team cannot play two matches
at the same timestamp`.

No V2A/V2B metrics, coverage result, winner, or per-domain result is published.
The consumed replacement HOLDOUT was not rerun. Independent evaluation is not
available, production promotion is not justified, and the production champion was
not changed.
