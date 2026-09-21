# Definitions Of Done

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

The source distinguishes sealed candidate, validation, published forecast, enrichment and real-outcome calibration. The concise [PLAN](../../PLAN.md) is the governing roadmap; use this fuller checklist for tickets and acceptance tests.

---

## 21. Distinct definitions of done: forecast, simulation, enrichment, release

**Immutable analytic forecast candidate** is complete when fixture and team identities resolve; cutoff and pre-match feature eligibility pass; missingness and provenance are retained; approved model/calibrator and data tier are identified; coherent distributions, expected goals, intervals, and canonical hash reproduce; and the candidate is sealed. This internal or analytic-only artifact is not evidence that Rust validation ran.

**Simulation validation** is complete separately when an explicitly authorized Rust build reproduces approved inputs using recorded seeds; an immutable `SimulationValidationArtifactV1` links the exact forecast hash; analytic parity, convergence, tails, resource and numerical checks pass; and no forecast probability or calibrator was altered by simulation. Missing/failed/inconclusive validation cannot be represented as PASS.

**New production fixture forecast** is simulation-validated and releasable by default only after both preceding artifacts pass and an owner-approved capability is enabled; publication must be atomic/recoverable and must preserve unchanged forecast bytes. Failed validation prevents new simulation-backed publication, but does not erase the sealed candidate or invalidate any earlier published forecast. Analytic-only fallback requires its own approved, clearly labeled product policy.

**Enrichment** is separately complete when post-forecast tags and diagnostics reproduce with `forecast_effect=false` and preserve forecast and simulation hashes. Enrichment is never mandatory for forecast completion or simulator validation; failure must not block an otherwise valid forecast.

**Predictive calibration** is proven only by chronological comparisons with real held-out match outcomes under an authorized policy, not by the number of simulated games or simulation parity alone.

## 22. Definitions of done

### 22.1 Predictive feature

A proposed feature is complete only when:

- its semantics and source are documented;
- availability time is proved;
- missingness is explicit;
- implementation tests pass;
- the hypothesis and ablation are pre-registered;
- evaluation uses chronological unseen data;
- proper scores, calibration, and segments are reported;
- paired uncertainty is reported;
- complexity and latency are measured;
- the accept/reject decision is recorded;
- failure evidence is retained.

### 22.2 Engineering change

An engineering change is complete only when:

- its owning module, contract impact, and architecture decision are clear;
- database and artifact migrations are backward compatible or have a rehearsed recovery path;
- unit, integration, contract, end-to-end, and relevant property tests pass;
- idempotency, retry, concurrency, and failure behaviour are tested where applicable;
- logs, metrics, traces, dashboards, and alerts cover the new failure modes;
- security, privacy, provider-license, dependency, and cost impacts are reviewed;
- performance stays inside the approved latency, throughput, memory, and storage budgets;
- deployment, rollback, data recovery, and runbook steps are verified in staging;
- documentation and ownership are updated before release.
