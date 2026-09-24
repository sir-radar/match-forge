# PitchAPI domain-stratified V2 preregistration readiness

Status: `BLOCKED — EXECUTION NOT AUTHORIZED`

The owner-frozen policy is
`PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2` at SHA-256
`e4dfbf6a5133fba4806de80e6a79ccc878670531bb695e5509776dca082c1da1`.
The policy file remains byte-for-byte unchanged from commit
`73996bb6fbaf0def76c10bb1f79c2f3fc303e111`.

The final current-inventory alias reconciliation passes with no exclusions.
The exact evaluation capacity remains 712 targets: 216 Bundesliga 2022/23,
216 Bundesliga 2023/24 and 280 Ligue 1 2022/23. The only history threshold is
`TEAM_PRIOR_APPEARANCES >= 10`; no competition-history threshold applies.

Raw PitchAPI xG is frozen. The rejected development transform changed log loss
by `-0.006867` and Brier score by `+0.001783`, so it failed the joint selection
rule and is not applied.

## Readiness matrix

| Requirement | Status | Evidence/hash | Blocks execution? |
| --- | --- | --- | --- |
| V2 policy frozen | PASS | `e4dfbf6a5133fba4806de80e6a79ccc878670531bb695e5509776dca082c1da1` | No |
| V1 preserved as FAIL | PASS | `docs/evidence/pitchapi-snapshot-v1-readiness-2026-09-24.json`; compatibility report `19d5cbbcbcc9c1f4dc6410a20223f3dd682d47841c1b216130615a2f71c2c9b8` | No |
| Snapshot immutable | PASS | snapshot `435bc3760cd3790e9f79cfc48801da0289fa73dbd30b02e63dc84468fd5a74ea`; document `b390a335b8c2cb94a1cdbfe220d78b02cdd812eeee2144c97e02cf42b59487f5` | No |
| Exact targets at least 500 | PASS | corpus `42d229ddbdc8a1349115c2cb258d970b82083265f64cadf6050b7a2f46b8f9a4`; 712 targets | No |
| Final alias reconciliation | PASS | `0ffe5660872a081ae262c6045825b0e1db4e775093cd213a02cd9947ffa47716` | No |
| Firewall | PASS | `bb5e9899fc73acda3d1f1f67e27ad4004ee83867b30ceb3b74e2e870303e14d2` | No |
| Protected-data separation | PASS | alias report and firewall above; zero overlap | No |
| Raw xG treatment frozen | PASS | canonical development result `dd19de6ae0a54a849d2dfb3c496b6c2934b63b27b2b57842674c6b749aa9e798` | No |
| Metrics frozen | PASS | `3381842ea8c548435bb18dd04ef4d29da2b564a393b50057ff2bc8f488c3f995` | No |
| Aggregation frozen | PASS | policy and metric specification above | No |
| Rust policy frozen | OWNER REVIEW REQUIRED | proposal `8154e8b78b307dd25e7167ad00f2a310f012b1474580a82795e72acd5ce3a9ee`; engine not implemented | **Yes** |
| Reference and challenger frozen | NOT READY | challenger math approved; implementation, fit and both artifact IDs absent | **Yes** |
| Final complete preregistration hashed | NOT READY | preparation artifact `87a1017542467f99ccf39a884fe74eede6ecd9423fe85e8835e3e02bb453ef80`; required execution identities are null | **Yes** |
| Repository verification | PASS | `make check`: 509 Python tests, Rust test, Go tests, Ruff, strict mypy (204 files), Clippy, Go vet/golangci-lint, migration/shell/static checks, builds and ProjectStatusV2 | No |

## Model boundary

The final model is not frozen. `PHASE3A_MINIMAL_XG_FOR_V1` has approved
mathematics only: `MATCHFORGE_NPXG_FOR_LAST10_V1`, one shared
`beta_xg_for` in `[0,1]`, and raw PitchAPI xG. No reference implementation,
challenger implementation or fitted artifact is authorized or fixed.

The next development decision must authorize only:

1. one exact compatible goals-only reference and its reproduction evidence;
2. implementation of the already approved one-parameter challenger;
3. fitting and all model decisions on Bundesliga 2021/22 only;
4. synthetic/property, point-in-time, artifact round-trip and deterministic
   replay tests; and
5. freezing the reference/challenger artifact hashes, code commit,
   configuration and dependency identities.

Bundesliga 2022/23, Bundesliga 2023/24 and Ligue 1 2022/23 outcomes must remain
unavailable for those decisions.

## Remaining owner decisions

First, approve or amend the Rust policy proposal and separately authorize its
offline implementation and non-evaluation validation. Also authorize the exact
development-only model work above. When those artifacts pass and a complete
preregistration with no null execution identity is hashed, execution can be
requested.

Exact execution authorization text, with the verified final values substituted
for every bracketed field, is:

> APPROVED. I confirm `PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2` remains frozen
> at policy SHA-256
> `e4dfbf6a5133fba4806de80e6a79ccc878670531bb695e5509776dca082c1da1`.
> I approve the complete preregistration artifact `[FINAL_PREREGISTRATION_SHA256]`,
> Rust policy `[APPROVED_RUST_POLICY_SHA256]`, Rust engine build
> `[RUST_ENGINE_BUILD_SHA256]`, compatible reference artifact
> `[REFERENCE_ARTIFACT_SHA256]`, challenger artifact
> `[CHALLENGER_ARTIFACT_SHA256]`, execution code commit `[EXECUTION_GIT_SHA]`
> and execution configuration `[EXECUTION_CONFIGURATION_SHA256]`. I authorize
> exactly one execution of `PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2` over the
> frozen 712-target corpus, subject to every preregistered fail-closed and stop
> condition. This authorization includes the mandatory Rust validation run and
> outcome scoring required by V2. It does not authorize API calls, provider
> contact, snapshot mutation, rule changes, retries after a terminal condition,
> promotion, production use, changes to `PITCHAPI_RETROSPECTIVE_EVALUATION_V1`,
> or changes to StatsBomb `EVALUATION_V2`. Stop after producing the immutable
> evaluation evidence and return the result for owner disposition.

The bracketed values cannot be supplied honestly until the two blocking work
packages are separately approved, implemented and frozen.

## StatsBomb isolation

The following StatsBomb identities were rechecked and remain unchanged:

- `docs/evaluation/evaluation-v2-policy.md`:
  `90812c0119e84a5bef94e8726ba9f4a984c33f8a6bb655603c68738994a345b3`;
- corpus owner decision:
  `164b459089f54ba2023f92457579e400f78f183b88db50cc8620cf4a70a2e6b1`;
- Phase 3A corpus proposal:
  `4e7f880fa20b038e226473f860608e61180505f6c741660b6243d726cddb0b24`.

No StatsBomb communication, data change or evaluation action was performed.
