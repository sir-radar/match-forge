# ForecastArtifactV1 — sealed probability source of truth

**Status:** proposed contract for *future* artifacts. No migration of historical forecast bytes or claim of live deployment. Full exact field typing/precision must be reconciled with existing repository schemas before adoption.

## Required immutable fields

| Field | Meaning |
| --- | --- |
| `schema_version`, `forecast_id`, `fixture_id` | Contract and immutable identity. |
| `issued_at`, `knowledge_cutoff`, `forecast_horizon` | UTC instant and approved horizon; cutoff is not inferred from issue time. |
| `supersedes_forecast_id` | Nullable reference to immutable predecessor. |
| `model_id`, `calibration_id`, `dataset_snapshot_id`, `feature_snapshot_id`, `parameter_snapshot_id` | Approved versioned lineage; tier and eligibility recorded. |
| `probability_distributions` | Coherent result, home/away goals, explicit exact-score matrix and tail, total goals, BTTS, clean sheets and supported approved market lines. |
| `expected_goals`, `uncertainty`, `data_quality_status` | Honest expected quantities, intervals and missingness/quality. |
| `canonical_probability_hash`, `artifact_hash`, `hash_policy_version` | Reproducible independent hashes; no self/cross-sidecar cycles. |
| `code_revision`, `created_by_run_id` | Reproducibility and audit. |

For an unsupported product, record support status in the separately approved product policy; never output fabricated zero. Corners need their independently qualified contract, distinct source/dependence assumptions and promotion gate.

## Invariants

- Resolve identities, historical cutoff and point-in-time features first. The approved model/calibrator must be eligible for fixture, data tier, competition and horizon.
- The distribution must be finite, nonnegative, normalized under documented tail semantics and algebraically coherent: e.g. 1X2, BTTS and totals derive from the same score distribution or an independently **evaluated** coherent joint model. A 1X2-only calibration breaking score coherence fails; Rust is not a reconciliation layer.
- A **sealed candidate** records its bytes/hashes and has no post-seal mutation. Simulation reads it, adds separate evidence, and can only approve/reject publication—not edit it.
- On publication, the artifact is immutable; a correction/revision receives a **new ID** with predecessor and new eligible information, not an in-place update. Original remains retrievable.
- Exclude derby/unpredictability/risk display tags, post-match shocks, closing odds, future lineups, unqualified H2H and any enrichment fields from feature inputs or probability outputs unless a **new distinct authorized feature family** explicitly permits an otherwise non-display source; under this plan the tags remain strictly display-only.

## Publication versus candidate completion

A candidate is complete once validation of inputs, distributions, provenance and hashes passes. **After independently approved mandatory Rust activation**, new simulation-backed production publication requires linked `SimulationValidationArtifactV1` `PASS`, atomically associated with **the same sealed hash**, plus eligible production capability. The approved analytic-only fallback is an explicit separate exception; it cannot claim Rust validity. Optional enrichment is not a prerequisite.

See [hashing](canonical-hashing-v1.md), [simulation artifact](simulation-validation-v1.md), [publication](../simulation/publication-state-machine.md), [enrichment](forecast-enrichment-v1.md) and [public schema](../api/openapi.yaml).
