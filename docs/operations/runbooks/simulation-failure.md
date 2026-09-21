# Runbook: Rust simulation failure or unavailability

**Entry:** a sealed candidate cannot get a valid linked simulation `PASS`, parity/coherence fails, Rust times out, a validation artifact hash mismatches or accepted engine/build is unavailable. Applies to **new simulation-required product only after its independent activation**.

1. **Contain:** stop new simulation-required publication for the affected version/competition/horizon; **preserve** sealed candidate, seed batches, failed/inconclusive validation, logs and previous published forecasts. Reject any `RUST_VALIDATED` API payload without exact linked `PASS`.
2. **Classify:** `FAIL` when invariant failed; `INCONCLUSIVE` on timeout, missing samples or unavailable proof; do not re-label either `PASS`. Capture candidate/hash, parameter hash, policy/build, affected fixtures, resource use and reason codes.
3. **Diagnose:** compare with independent analytic reference and versioned golden fixtures; replay same seed/platform and multi-seed batches, inspect score tails, normalization, event coverage, numeric precision, budget exhaustion and publishing transaction/outbox.
4. **Communicate:** new required-product request returns an explicit `SIMULATION_UNAVAILABLE` according to approved public error contract; do not leak internal seeds or private provider provenance. Previously published forecasts continue to respond normally.
5. **Fallback rule:** only a **pre-existing signed** exception policy with valid scope, expiry and owner may permit `ANALYTIC_ONLY`, visibly distinguished from `RUST_VALIDATED`. Do not invent a temporary exception during an incident.
6. **Recover:** revert routing to accepted engine/build or fix as a new version, run reference/parity/convergence/CI/staging tests and confirm publication idempotence and API labels. Resume only after verified owner sign-off/enablement event; do not edit earlier evidence.
7. **Post-incident:** record impact duration, loss/fail/inconclusive counts, affected product/segments, latency/cost, hashes, root cause, validated replay and follow-up work.

**Separate incidents:** enrichment failure should only disable tags; actual predictive calibration drift should trigger authorized rolling review, never be 'fixed' by more simulator draws.
