# MatchForge governed context feature evaluation V1

Status: `INSUFFICIENT_QUALIFIED_COVERAGE`

The production baseline remains `transferable-rolling-goals-poisson-v1`. The H2H
prerequisite is not available: its earlier immutable development result is
`DEVELOPMENT_REJECTED` on 379 scored targets. Its Joint LL delta was
`+0.00009958598319782521` with paired 95% interval
`[-0.00000010761151504806502, +0.00020443573841225147]`.

The local point-in-time context store contains zero availability observations, zero
lineup observations, zero coach observations, and zero lineup-accuracy rows. Therefore
`PredictedLineupV1` cannot be reconstructed and compared with later confirmed lineups.
All lineup accuracy, confidence, injury, suspension, formation, and replacement metrics
are unavailable rather than treated as zero.

No immutable, authorized, unspent development target corpus is available for the new
family decisions. The spent PitchAPI V5 targets, the 712 multimodel model-selection
outcomes, and other protected or spent targets were not loaded. Rest/congestion was not
scored against those outcomes. No qualified venue-coordinate development corpus exists.

Family results:

- H2H: `DEVELOPMENT_REJECTED` from the existing Step 3 result.
- Availability/lineup: `INSUFFICIENT_QUALIFIED_COVERAGE`.
- Rest/congestion: `INSUFFICIENT_QUALIFIED_COVERAGE`.
- Manager: `INSUFFICIENT_QUALIFIED_COVERAGE`.
- Travel: `INSUFFICIENT_QUALIFIED_COVERAGE`.

The neutral `MATCHFORGE_CONTEXTUAL_GOAL_MODEL_V1` artifact includes no feature families,
coefficients, or scaler parameters. Missing context leaves baseline forecast coverage
unchanged. No context family is active in `predictive_input_snapshot_sha256`; context
updates therefore remain context-only.

No independent evaluation corpus is available. Production promotion is not justified,
and the current champion is unchanged.
