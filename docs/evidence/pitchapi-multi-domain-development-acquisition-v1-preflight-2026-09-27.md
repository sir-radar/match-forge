# PitchAPI multi-domain development acquisition preflight

## Frozen scope

Authorization: `PITCHAPI_MULTI_DOMAIN_DEVELOPMENT_ACQUISITION_V1`.

The exact development-only groups are Bundesliga 2024/25, Bundesliga 2025/26,
Premier League 2024/25, La Liga 2024/25, and Serie A 2024/25. Provider league
IDs must be resolved once from `GET /v1/leagues` by exact competition name,
country code, and advertised season. Missing or ambiguous scope stops the run.
No substitution is allowed.

## Frozen request and storage budget

| Item | Count |
| --- | ---: |
| Catalog | 1 |
| Season manifests | 5 |
| Match-shot resources | 1,752 |
| Expected requests | **1,758** |
| Retry allowance | **36** |
| Hard request ceiling | **1,794** |

Requests are serial, start at least one second apart, time out after 30 seconds,
and retry a path at most once. A second rate-limit response, authentication
failure, unavailable required scope, missing resource, or exhausted ceiling
stops the run.

Prior snapshot V1 used 80,111,128 logical primary-plus-backup bytes for 1,298
matches. Linear scaling gives about 108 MiB for 1,752 matches. Frozen expected
storage is 120 MiB; hard ceiling is 1 GiB. The new root is
`.local/pitchapi-multi-domain-development-v1`; `PITCHAPI_SNAPSHOT_V1` is not
modified.

## Provider entitlement basis

PitchAPI's [official reference](https://pitchapi.dev/), observed 2026-09-27,
describes one free plan
with every catalog league, every endpoint, history back to 2021, unlimited
requests, no payment, and a fair-use burst guard. This preflight still treats
the live catalog and each exact resource as authoritative. Any entitlement or
rights failure stops the route. Immutable retention is authorized by the owner
for this private, non-commercial research snapshot.

## Preserved boundary

No model fitting, calibration, admission, evaluation, V6, confirmation,
promotion, deployment, paid upgrade, provider contact, StatsBomb acquisition,
or V5 target reuse is authorized.
