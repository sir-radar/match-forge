# Owner decision: accept PitchAPI V1 failure and design domain-stratified V2

Decision ID: `ACCEPT_PITCHAPI_V1_FAIL_AND_DESIGN_DOMAIN_STRATIFIED_V2_V1`

Recorded: `2026-09-24T15:42:23Z`

Status: `APPROVED`

The owner permanently accepted `PITCHAPI_RETROSPECTIVE_EVALUATION_V1` as
`FAIL — OBSERVATIONAL_COMPATIBILITY_GATE`. Its thresholds, evidence,
configuration, manifests, reports and `PITCHAPI_SNAPSHOT_V1` remain immutable.
V1 must not run.

The owner authorized design and offline implementation only for the separate
`PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2`. This includes a development-only
xG treatment comparison and the cross-provider overlap design/review. It does
not authorize a final challenger fit, evaluation, Rust simulation, API call,
provider contact, snapshot mutation, spend, promotion or production use.

StatsBomb `EVALUATION_V2` remains independent and byte-for-byte unchanged.
