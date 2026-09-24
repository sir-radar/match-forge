# PitchAPI snapshot V1 acquisition and readiness — 2026-09-24

Status: `FAIL — OBSERVATIONAL COMPATIBILITY GATE`

Controlled acquisition completed. `PITCHAPI_SNAPSHOT_V1` and its verified
backup are retained immutably under `.local/`. No evaluation, model fitting,
Rust simulation, provider contact, or spend occurred.

## Acquisition

| Scope | Role | Matches | Shots | Team-history exclusions | Exact history-eligible targets |
| --- | --- | ---: | ---: | ---: | ---: |
| Bundesliga 2021/22 | Development | 306 | 7,961 | 90 | 216 |
| Bundesliga 2022/23 | Evaluation | 306 | 7,825 | 90 | 216 |
| Bundesliga 2023/24 | Evaluation | 306 | 8,523 | 90 | 216 |
| Ligue 1 2022/23 | Evaluation | 380 | 9,350 | 100 | 280 |
| Total |  | **1,298** | **33,659** | **370** | **928** |

Evaluation-only exact target count before compatibility is
`216 + 216 + 280 = 712`. Acquisition used 1,302 attempts: four season
manifests and 1,298 shot resources. Retries: 0. Rate-limit responses: 0. The
separate ten-attempt remainder was not used.

Logical primary-plus-backup size is 80,111,128 bytes (76.4 MiB). Snapshot
filesystem allocation, including staging evidence, is 97,840 KiB (95.5 MiB),
below both the 500 MiB expectation and 6 GiB hard ceiling.

## Compatibility result

Schema normalization, finite/range, missingness, period semantics, situation
semantics, penalty sample/range/IQR, penalty cross-scope shift, and calibration
sample size pass. Every penalty xG is `0.7884`; all four penalty samples exceed
20.

Every scope fails both frozen calibration coefficient limits:

| Scope | Non-penalty sample | Intercept | Slope | Result |
| --- | ---: | ---: | ---: | --- |
| Bundesliga 2021/22 | 7,877 | -0.600659 | 0.644283 | `FAIL` |
| Bundesliga 2022/23 | 7,716 | -0.568459 | 0.647358 | `FAIL` |
| Bundesliga 2023/24 | 8,422 | -0.438329 | 0.736078 | `FAIL` |
| Ligue 1 2022/23 | 9,207 | -0.833386 | 0.586395 | `FAIL` |

Frozen hard limits are `abs(intercept) <= 0.25` and slope `[0.80,1.20]`.
Independent BFGS optimization reproduced the fitted coefficients.

Overall KS has one hard failure and one warning: Bundesliga 2021/22 versus
Ligue 1 2022/23 has `D=0.101600` (`FAIL`); Bundesliga 2023/24 versus Ligue 1
2022/23 has `D=0.094869` (`WARN`). Four other overall pairs pass. Seventeen
situation-conditioned comparisons exceed `D > 0.10`, led by FreeKick
Bundesliga 2021/22 versus Ligue 1 2022/23 at `D=0.219107`.

Final gate result: 25 hard findings and 11 warnings. The 80%-strict and
120%-loose threshold sensitivities both fail. Every leave-one-scope-out result
fails. Thresholds were not changed after acquisition.

Therefore none of the 712 history-eligible evaluation targets is admitted as
final evaluation evidence. This result does not prove or disprove an identical
hidden upstream model; it only shows that the frozen scopes are not
observationally compatible under the preregistered V1 criteria.

## Identity and firewall

```text
Snapshot ID:              9eb89b53-1a29-5dcd-bc9b-24f0320b3c8d
Snapshot SHA-256:         435bc3760cd3790e9f79cfc48801da0289fa73dbd30b02e63dc84468fd5a74ea
Snapshot document:       b390a335b8c2cb94a1cdbfe220d78b02cdd812eeee2144c97e02cf42b59487f5
Backup inventory:        8de3262591ddddf399ab048ca12751bc99fdc31a005e0620b6892735fa3a8924
Configuration:           4b90fdccf678480ab53e0d5c637b76d8535ae114ad5c8b835c9675d4ae984318
Processing Git commit:   1c9ac4243c99a05a0141972dab3dd46c5706fc9d
Corpus manifest:         42d229ddbdc8a1349115c2cb258d970b82083265f64cadf6050b7a2f46b8f9a4
Firewall manifest:       bb5e9899fc73acda3d1f1f67e27ad4004ee83867b30ceb3b74e2e870303e14d2
Compatibility report:    19d5cbbcbcc9c1f4dc6410a20223f3dd682d47841c1b216130615a2f71c2c9b8
```

Role isolation, strict prior-kickoff construction, same-kickoff batching, and
protected-scope intersection pass. Development/evaluation match intersection
is zero. Final corpus admission still requires cross-provider canonical-overlap
review, but compatibility failure already blocks admission and execution.

## Required next owner decision

Accept the failed compatibility disposition and stop
`PITCHAPI_RETROSPECTIVE_EVALUATION_V1`, or authorize design of a new, separately
preregistered protocol. Do not alter V1 thresholds to rescue these scopes.
Evaluation execution cannot be authorized under V1.
