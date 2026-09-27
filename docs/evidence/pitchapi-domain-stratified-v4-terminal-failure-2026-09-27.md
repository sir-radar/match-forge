# PitchAPI domain-stratified evaluation V4 terminal failure

Protocol: `PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V4`

Result: `PROTOCOL_EVALUATION_FAILURE`

The single authorized V4 execution processed all 712 targets and completed all
1,424 mandatory Rust forecast validations. The evaluation-wide score-matrix
total-variation gate passed. Maximum observed TV distance was
`0.008963756743400754`, below the frozen limit
`0.012794580429261083`. All 1,424 validations returned `PASS`; no diagnostic
event warning fired.

Execution then failed closed while generating preregistered heterogeneity
evidence. Raw npxG included a boundary value, while `calibration_fit` requires
inputs strictly inside `(0,1)`. The exact error was:

`calibration probabilities must be inside (0,1)`

No complete evaluation evidence was published. No valid primary, secondary,
bootstrap, calibration, per-domain, macro, weighted, or heterogeneity result
exists. Rust parity success does not establish predictive performance. The
challenger did not satisfy the frozen V4 success criteria.

The one authorized logical execution is consumed. V4 must not be repaired or
rerun. The next owner decision is whether to authorize a new protocol that
corrects the heterogeneity evidence contract.
