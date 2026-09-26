# PitchAPI domain-stratified V3 execution readiness

`PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V3` is frozen and ready for a separate
owner execution decision. It has not been executed. Evaluation outcomes were
not loaded during design or freeze work, no PitchAPI API call was made, and the
snapshot was not modified.

## Frozen identities

- Policy: `791c5db96db55cc569424f3f28f290d0b8fdbd49dc9c3f6166bac711dc2f6220`
- Preregistration: `af30d63e6a1f6293b5f8d5bf6df2524f4ed1f87cf65d41a6ab4bb0f4473fa9d1`
- Execution configuration: `bdce335b01c1132a66b5eca6897850573211eb4cb53601f3e46015990d7dcca4`
- Reference artifact: `e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4`
- Challenger artifact: `314e1e0891ffaae6d7fe3885f5bf7e9087bed4b02bdc323e685ee49c11f0675a`
- Rust policy: `682ebf08298dbe7aa5078d2e5b0922b5c43e8dee05be8ea89781bce97eed7ebf`
- Rust release build: `4f4709b38c8d6c72e93c433074fed3d7788eb4018cfddfe67f73ae5f438e209c`
- Executor source: `5cc54bad9ceff5ca9e7ac4b449268a93d92c5a36`

Structural verification covers all 712 frozen targets and reports zero
unforecastable targets. Synthetic execution verifies atomic publication,
fail-closed preflight behavior, unseen-team forecasts, temporal sealing, and
deterministic Rust replay at one and four workers.

V2 remains frozen and unexecuted as
`BLOCKED_PRE_EXECUTION_MODEL_NON_TRANSFERABILITY`. Its artifacts, policy,
preregistration, and execution configuration retain their recorded hashes.
StatsBomb `EVALUATION_V2` remains unchanged.

## Required owner authorization

Execution requires a new machine-readable owner authorization that sets
`evaluation_execution_authorized` to `true` and binds exactly the V3 protocol,
preregistration, execution configuration, reference artifact, challenger
artifact, and Rust build SHA-256 values above. The prior V2 authorization is
not valid for V3.
