# PitchAPI domain-stratified V3 terminal failure

Protocol: `PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V3`

Run ID: `pitchapi-domain-stratified-v3-2026-09-26`

Result: `PROTOCOL_EVALUATION_FAILURE`

The one authorized V3 execution stopped fail-closed during mandatory Rust
simulation. Rust returned:

```text
PARITY_FAILURE: score:1-4 analytic probability is outside parity interval
```

No rerun was performed. V3 must not be resumed or rerun without a new owner
decision, and any investigation must use a new protocol or version.

## Frozen identities

- Owner authorization: `5a894552a6d95f0cfada64acb6e2dd835273c68cbf2827258e85283d2febe7a3`
- Policy: `791c5db96db55cc569424f3f28f290d0b8fdbd49dc9c3f6166bac711dc2f6220`
- Preregistration: `af30d63e6a1f6293b5f8d5bf6df2524f4ed1f87cf65d41a6ab4bb0f4473fa9d1`
- Execution configuration: `bdce335b01c1132a66b5eca6897850573211eb4cb53601f3e46015990d7dcca4`
- Snapshot: `435bc3760cd3790e9f79cfc48801da0289fa73dbd30b02e63dc84468fd5a74ea`
- Corpus: `42d229ddbdc8a1349115c2cb258d970b82083265f64cadf6050b7a2f46b8f9a4`
- Firewall: `bb5e9899fc73acda3d1f1f67e27ad4004ee83867b30ceb3b74e2e870303e14d2`
- Alias reconciliation: `0ffe5660872a081ae262c6045825b0e1db4e775093cd213a02cd9947ffa47716`
- Reference artifact: `e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4`
- Challenger artifact: `314e1e0891ffaae6d7fe3885f5bf7e9087bed4b02bdc323e685ee49c11f0675a`
- Rust policy: `682ebf08298dbe7aa5078d2e5b0922b5c43e8dee05be8ea89781bce97eed7ebf`
- Rust release build: `4f4709b38c8d6c72e93c433074fed3d7788eb4018cfddfe67f73ae5f438e209c`
- Executor source: `5cc54bad9ceff5ca9e7ac4b449268a93d92c5a36`

All identities matched before execution and still matched after failure. Snapshot
preflight confirmed exactly 712 structural targets: 216, 216, and 280 across
the three frozen domains. The snapshot was not mutated, and no PitchAPI API
call or provider contact occurred.

## Results

The mandatory Rust result is `FAIL`. Successful evaluation evidence was not
published, so these preregistered outputs are `NOT_PRODUCED`:

- primary joint-score matrix log loss for reference and challenger;
- primary delta and bootstrap interval;
- all 1X2 log-loss, Brier, RPS, and total-goal CRPS results;
- Bundesliga 2022/23, Bundesliga 2023/24, and Ligue 1 2022/23 results;
- equal-weight macro-domain aggregate;
- fixed 216/216/280 target-weighted aggregate;
- calibration;
- heterogeneity;
- descriptive metrics.

Published target-result count is 0. The 712-target count is a passed structural
preflight count, not a completed evaluation count. The challenger did not
satisfy the frozen V3 success criteria because protocol failure made those
criteria unassessable.

## Findings

- `PASS`: frozen identity preflight.
- `PASS`: exact structural target count of 712.
- `FAIL`: mandatory Rust simulation.
- `NOT_COMPLETED`: deterministic Rust replay.
- `NOT_PRODUCED`: preregistered evaluation metrics.
- `PASS`: exactly one logical execution attempt; no rerun.
- `PASS`: no post-outcome tuning.
- `PASS`: no provider API activity or snapshot mutation.
- `PASS`: PitchAPI V2 remains unexecuted and StatsBomb Evaluation V2 remains unchanged.

## Evidence

- Machine evidence SHA-256: `ef954113b229ae4d52cd2d67a2d3e56b3405f4fb712199ce6a649f4347b4060f`
- Executor failure receipt SHA-256: `8a9ac7834b9e4aedbdc30855e863fe74be14caeb18ae87a52c2b52457d664ebf`

## Scientific limitations

The run failed before complete target-level evidence was published. No model
comparison, domain result, uncertainty estimate, calibration result, or
heterogeneity inference is valid from this attempt. No post-outcome tuning or
other substantive change was made.

## Required owner decision

Choose whether to close V3 as a terminal protocol failure or authorize a new
protocol/version to investigate the Rust parity failure. Do not rerun V3.
