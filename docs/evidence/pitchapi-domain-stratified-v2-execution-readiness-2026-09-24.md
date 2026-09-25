# PitchAPI domain-stratified V2 execution readiness

Status: `PASS — AWAITING OWNER EXECUTION AUTHORIZATION`

No evaluation target was simulated. No evaluation outcome was loaded or
inspected. No PitchAPI API call or provider contact occurred.

## Simulation-count derivation

The target family contains 62 indicators. With familywise alpha `0.05`,
Bonferroni per-indicator alpha is `0.05 / 62`. The two-sided normal quantile is:

```text
z = Phi^-1(1 - 0.05 / (2 * 62)) = 3.350570901301503
```

For worst-case Bernoulli probability `p = 0.5` and target half-width
`h = 0.005`, the normal starting count is:

```text
ceil(z^2 / (4 * h^2)) = 112,264
```

The frozen policy uses exact two-sided Clopper–Pearson intervals, not the
normal approximation. Counts must divide into four equal batches. At the
worst-case central count:

```text
n = 112,456; k = 56,228; half-width = 0.005000023326954345  FAIL
n = 112,460; k = 56,230; half-width = 0.004999934331017614  PASS
```

Therefore 112,460 is the smallest multiple of four meeting the frozen
precision requirement. Any lower allowed count fails. Each batch contains
28,115 draws. At `p = 0.5`, expected standard error is about `0.001491` and
marginal normal 95% half-width is about `0.002922`.

## Frozen implementations

- Execution code commit: `6b0e32ee94d5e910a3fbe8096c2fc5192adfa49b`.
- Rust policy: `8154e8b78b307dd25e7167ad00f2a310f012b1474580a82795e72acd5ce3a9ee`.
- Rust source tree: `6dc327ec8b6c652cad8ad582eaaf33a5949204e2`.
- Release binary: `36a0a04f89faafbea07243a18efb0f79c13b8f3591cff5af22f756d45f32aa87`.
- Reference artifact: `54d209dc5d409c589750822871944f1b1175ae95883c9c83b92be1c729f5ddba`.
- Challenger artifact: `5fab3347523ade3918b17f7cd38400a6a54f92b54adee3da61aa28fdb5d9d973`.
- Execution configuration: `8cf592c471d543c874c83ab12e11942e4de74453f49f3a8d4949d636667b8285`.
- Final preregistration: `eec2b9362b72779a44da87e8ddf3055b22bd3573a3d52b6f62e97d72c31068f4`.

Both models used exactly 216 eligible Bundesliga 2021/22 development matches.
The challenger fitted the one approved coefficient as
`beta_xg_for = 1.1471034440351443e-14`, an allowed near-zero no-effect result.
The reproduction artifact records `evaluation_scope_loaded = false`. Reload
equivalence and deterministic repeat fitting pass.

## Rust validation and feasibility

Rust and independent Python reference calculations agree on SplitMix64 words,
base and batch seeds, atom selection, and all event reductions. Serial and
four-worker replay produce identical canonical output and hashes. The release
validation CLI's synthetic golden output SHA-256 is
`b8893247723f573dcaac6310c6e0800df9d7de78f5f0bd97f21e45e1347086aa`.

Synthetic full-corpus-equivalent benchmark (`80,071,520` draws):

- one worker: `11.042615291 s`, `7,251,137 simulations/s`;
- four workers: `4.649521708 s`, `17,221,453 simulations/s`;
- both checksums: `880786720`;
- four-worker maximum resident set size: `2,146,304 bytes`;
- projected CPU work from measured four-worker run: `18.12 CPU-seconds`;
- ordering and hashes: unchanged by worker count.

No practical runtime constraint approaches the frozen 64 CPU-hour, 24-hour,
or 16 GiB execution budgets. Optimization is not required.

## Final readiness matrix

| Requirement | Status | Evidence |
| --- | --- | --- |
| V2 policy frozen | PASS | `e4dfbf6a5133fba4806de80e6a79ccc878670531bb695e5509776dca082c1da1` |
| V1 remains FAIL | PASS | retained terminal V1 evidence |
| Snapshot immutable | PASS | `435bc3760cd3790e9f79cfc48801da0289fa73dbd30b02e63dc84468fd5a74ea` |
| 712 targets frozen | PASS | corpus `42d229ddbdc8a1349115c2cb258d970b82083265f64cadf6050b7a2f46b8f9a4` |
| Alias reconciliation | PASS | `0ffe5660872a081ae262c6045825b0e1db4e775093cd213a02cd9947ffa47716` |
| Firewall | PASS | `bb5e9899fc73acda3d1f1f67e27ad4004ee83867b30ceb3b74e2e870303e14d2` |
| Protected-data separation | PASS | zero overlap |
| Raw xG frozen | PASS | `dd19de6ae0a54a849d2dfb3c496b6c2934b63b27b2b57842674c6b749aa9e798` |
| Reference model frozen | PASS | artifact hash above |
| Challenger frozen | PASS | artifact hash above |
| Rust policy approved | PASS | policy hash above |
| Rust implementation frozen | PASS | source and binary hashes above |
| Rust parity | PASS | cross-language golden vectors |
| Rust stability | PASS | serial/parallel replay and synthetic benchmark |
| Execution configuration frozen | PASS | configuration hash above |
| Preregistration complete and hashed | PASS | preregistration hash above |
| Full repository verification | PASS | `make check`; 513 Python tests plus Rust, Go, Ruff, mypy, Clippy, builds, static checks, JSON and ProjectStatusV2 |

StatsBomb protected hashes remain unchanged:

- evaluation policy: `90812c0119e84a5bef94e8726ba9f4a984c33f8a6bb655603c68738994a345b3`;
- corpus owner decision: `164b459089f54ba2023f92457579e400f78f183b88db50cc8620cf4a70a2e6b1`;
- Phase 3A corpus proposal: `4e7f880fa20b038e226473f860608e61180505f6c741660b6243d726cddb0b24`.

Remaining blocker: owner execution authorization only.

## Exact required owner authorization

> APPROVED. I confirm `PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2` remains frozen
> at policy SHA-256
> `e4dfbf6a5133fba4806de80e6a79ccc878670531bb695e5509776dca082c1da1`.
> I approve the complete preregistration artifact
> `eec2b9362b72779a44da87e8ddf3055b22bd3573a3d52b6f62e97d72c31068f4`,
> Rust policy
> `8154e8b78b307dd25e7167ad00f2a310f012b1474580a82795e72acd5ce3a9ee`,
> Rust engine build
> `36a0a04f89faafbea07243a18efb0f79c13b8f3591cff5af22f756d45f32aa87`,
> compatible reference artifact
> `54d209dc5d409c589750822871944f1b1175ae95883c9c83b92be1c729f5ddba`,
> challenger artifact
> `5fab3347523ade3918b17f7cd38400a6a54f92b54adee3da61aa28fdb5d9d973`,
> execution code commit `6b0e32ee94d5e910a3fbe8096c2fc5192adfa49b` and
> execution configuration
> `8cf592c471d543c874c83ab12e11942e4de74453f49f3a8d4949d636667b8285`.
> I authorize exactly one execution of
> `PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2` over the frozen 712-target corpus,
> subject to every preregistered fail-closed and stop condition. This
> authorization includes the mandatory Rust validation run and outcome scoring
> required by V2. It does not authorize API calls, provider contact, snapshot
> mutation, rule changes, retries after a terminal condition, promotion,
> production use, changes to `PITCHAPI_RETROSPECTIVE_EVALUATION_V1`, or changes
> to StatsBomb `EVALUATION_V2`. Stop after producing the immutable evaluation
> evidence and return the result for owner disposition.
