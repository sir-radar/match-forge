# SimulationValidationArtifactV1 — immutable numerical evidence

**Status: PROPOSED; engine build, test policies and production activation not authorized by the recorded 20 September research event.** This contract does not retroactively invalidate historical analytic forecasts.

## Required fields

```text
schema_version, validation_id, forecast_id
forecast_artifact_hash, forecast_probability_hash
parameter_snapshot_id, parameter_input_hash, distribution_policy_id
simulation_policy_id, engine_name="rust", engine_build_id, engine_commit
platform_fingerprint, numerical_precision_policy, created_at, completed_at
seed_schedule_id, base_seed_commitment, batch_seed_ids, independence_assumptions
batch_count, attempts, eligible_sample_count, per_batch_sample_counts
supported_events, excluded_events_and_reasons
analytic_reference_ids, per_event_parity_metrics, tolerance_policy_id
per_event_confidence_intervals, half_widths, convergence_metrics
score_tail_metrics, normalization_checks, market_coherence_checks
elapsed_ms, peak_memory_bytes, compute_cost, budget_policy_id
status: PASS | FAIL | INCONCLUSIVE
failure_reason_codes, audit_run_id, validation_artifact_hash
```

Record actual sample counts, not the requested count; include algorithm/version, effective draws and cancellation/timeouts. Sample output may live in separately hashed blob(s); this artifact references them. It never stores a calibrated replacement probability in the forecast record.

## Exact status semantics

- `PASS` **only if** engine is accepted and authorized for fixture/data tier/product, hash binding matches sealed candidate, deterministic seed replay and required reference fixtures pass, all eligible event-specific analytic-parity, confidence-half-width, convergence, normalization, tail, numeric and time/cost limits pass under **frozen** policy. Unqualified corners/scenarios cannot be claimed supported.
- `FAIL` for a demonstrably violated invariant, broken input/hash linkage, impossible probability/coherence, invalid seed implementation or reproducible parity/tail failure.
- `INCONCLUSIVE` for timeout, resource exhaustion, insufficient rare-event samples, unavailable analytic comparison where mandatory, unknown engine state, cancellation or unproven precision/coverage. Do not equate with `FAIL` as a scientific result or `PASS` for release.

## Required reproducibility

Use independent recorded seed schedules and event-specific pre-registered stopping criteria. Development 1,000, routine 10,000 and detailed 100,000 are **initial engineering counts**, not fixed tolerances or proof of convergence. Preserve seed/batch results and engine build. Specify bit-for-bit reproducibility scope (same build/platform) and approved tolerance across different platforms. Parity should compare Rust frequencies with the **already sealed** model distribution; never use frequencies to tune the model on that fixture.

## Publication proof

The publisher must verify: candidate/hash still match; validation policy, engine, feature/model/calibrator and capability are approved; status is `PASS`; publication transaction binds the two immutable IDs and is idempotent. An analytic-only exception instead requires an owner-approved exception policy ID and conspicuous `ANALYTIC_ONLY` delivery label; no made-up validation ID. Invariants and status changes go to new records, not overwritten evidence.

Numerical parity/convergence cannot establish out-of-sample **predictive** calibration; that requires held-out real outcomes and separate authorized evaluation/promotion.
