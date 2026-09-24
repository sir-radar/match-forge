# Owner decision: freeze PitchAPI domain-stratified evaluation V2

Decision ID: `FREEZE_AND_PREREGISTER_PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2_V1`

Recorded: `2026-09-24T16:03:09Z`

Status: `APPROVED`

The owner froze `PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2` exactly as recorded
in `docs/evaluation/pitchapi-domain-stratified-evaluation-v2-policy-proposal.json`
at SHA-256
`e4dfbf6a5133fba4806de80e6a79ccc878670531bb695e5509776dca082c1da1`.
The file is retained at that exact hash; its original proposal-status field is
historical and this decision supplies the approval state.

The freeze covers protocol rules, raw PitchAPI xG, corpus assignments, the
712-target capacity, metrics, aggregation, source admission, heterogeneity
reporting, failure conditions, final alias reconciliation and preparation of a
Rust validation policy. Material changes require a new protocol version and a
new owner decision.

This decision does not authorize model fitting, evaluation execution, Rust
evaluation simulation, API calls, provider contact, snapshot changes, spending,
promotion or production use. `PITCHAPI_RETROSPECTIVE_EVALUATION_V1` remains
`FAIL — OBSERVATIONAL_COMPATIBILITY_GATE`. StatsBomb `EVALUATION_V2` remains
separate and unchanged.
