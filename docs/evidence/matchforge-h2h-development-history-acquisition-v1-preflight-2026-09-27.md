# MatchForge H2H development-history acquisition preflight

## Authorized scope

Acquire only Premier League, La Liga, and Serie A 2023/24 as `DEVELOPMENT_HISTORY_ONLY`. The fixed 1,270 development targets remain unchanged. No Bundesliga history, new targets, confirmation data, fitting, evaluation, promotion, deployment, or V6 work is authorized.

The latest locally sealed PitchAPI catalog lists all three requested seasons. Provider entitlement is still tested fail-closed by the actual acquisition request.

## Frozen request budget

| Request | Count |
|---|---:|
| Catalog | 1 |
| Season manifests | 3 |
| Match shot resources | 1,140 |
| Expected total | 1,144 |
| Retry allowance | 23 |
| Hard task ceiling | 1,167 |

Requests run serially with at least one second between starts, a 30-second request timeout, and a 30-minute wall-clock ceiling. No provider contact, paid upgrade, or catalog expansion is authorized.

## Frozen storage budget

The equivalent three current-season groups occupy 72,112,628 bytes for raw and normalized primary-plus-backup resources. The frozen expected total is 83,886,080 bytes (80 MiB), including manifests and reports. The hard ceiling is 536,870,912 bytes (512 MiB). The output is a new immutable snapshot at `.local/pitchapi-h2h-development-history-v1`; the existing development snapshot is not modified.

## Qualification and stop rules

Each season must retain exact provider fixture identity, kickoff, teams, result, shots, expected goals, penalty and own-goal flags, shot situation, canonical mappings, request lineage, and raw/normalized hashes. Non-finished fixtures are quarantined before shot acquisition. Missing, malformed, ambiguous, or semantically invalid admitted data fails qualification.

Coverage is recomputed only for the existing 1,270 targets using the frozen 730-day, five-meeting history limit and two-meeting usability rule. The research qualifies only with at least 600 targets having 2+ usable meetings, 300 having 3+, and at least three competitions each having 150 targets with 2+.

The acquisition stops as `PROVIDER_OR_RIGHTS_BLOCKED` if the exact authorized provider scope is unavailable under the current entitlement. Other acquisition or integrity failures return `ACQUISITION_FAILED`. Valid data that misses the frozen coverage floors returns `H2H_DEVELOPMENT_HISTORY_INSUFFICIENT`.
