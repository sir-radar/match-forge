# Forecast/enrichment immutability and parity test

## Goal

Prove tags and diagnostics are strictly downstream. Run the **same already sealed and, where required, validated/published** forecast through these states: enrichment disabled, empty, only derby, only uncertainty, all eligible tags, policy revision, shuffled reason-code order, changed UI text, failure, timeout, stale policy, partial evidence and concurrent retry.

## Required checks (every case)

1. Re-read immutable forecast bytes and recompute its canonical probability hash and artifact hash: both **exactly equal** baseline (no changes to forecast ID, model/calibrator IDs, expected goals, score matrix/tail, parameters or inputs).
2. Re-read any `SimulationValidationArtifactV1`: unchanged hash, status, input fingerprint, seed schedule and eligible sample count; no second sampling triggered solely by tags.
3. Verify tagged vs untagged public responses have exactly identical **forecast-owned** fields after the approved projection/serialization; only explicitly enrichment-owned response fields may differ. Full HTTP response bytes may differ because request ID, cache headers and sidecars vary.
4. Enforce static dependency/import rules and runtime feature-column allowlists proving no tag/risk field can flow upstream. A matching probability hash alone cannot detect a forecast which mistakenly consumed tags *before* sealing.
5. Verify no writes/updates to immutable forecasts, validation records or published predecessor; new tags produce a new sidecar only.
6. Simulate timeout/unavailable: return original forecast unchanged, hide/mark unavailable the optional enrichment, alert on integrity failures without breaking the valid forecast.

## Failure action

Reject/disable offending enrichment version; preserve forecast and Rust evidence; open high-severity integrity incident with hashes, input snapshots, diff and owner; block re-enablement until regression and owner approval. Never rewrite forecast or quietly repair probabilities.

## Automation

CI contract/property and module-boundary tests, integration tests with fault injection, staging, production canary, and every sidecar-policy/schema change. Include negative control: intentionally inject an upstream tag to verify the taint/dependency test detects the violation.
