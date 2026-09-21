# Immediate Backlog

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

Order this backlog through the verified decision/capability state; do not run blocked research, overwrite status, or assume proposed APIs exist. See [adoption checklist](../reconciliation/adoption-checklist.md).

---

## 20. Immediate implementation backlog

This backlog references the phase and contract sections instead of restating their complete deliverables.

### 20.1 Engineering foundation

Execute before an authoritative evaluation run:

1. Reconcile current committed `docs/project-status.json` and the existing 20 September owner decision without overwriting either; preserve the Sprint 2 failure and frozen-target firewall. Draft a **distinct, not-yet-approved** minimal Rust simulation authorization proposal.
2. Write architecture decisions for the modular deployment, module dependencies, storage, durable jobs, artifact registry, API versioning, and deployment strategy.
3. Establish the reproducible local environment, locked dependencies, seeded fixtures, and one-command validation suite.
4. Implement the raw-data, identity, correction, quarantine, migration, and point-in-time snapshot foundations.
5. Add idempotent ingestion and backfill jobs with checkpoints, retry policy, dead-letter handling, and replay controls.
6. Add CI gates, artifact checksums, build provenance, security and license scans, migration dry runs, and deterministic fixed-model scoring.
7. Instrument logs, metrics, traces, dashboards, and initial SLOs; prove backup restoration and rollback in staging.
8. Establish cost attribution and budgets for provider calls, storage, training, evaluation, simulation, and forecast serving.

### 20.2 Research and product sequence

Proceed only as each preceding gate resolves:

1. Freeze Evaluation V2 policy, corpus rules, references, metrics, and target firewall.
2. Qualify competition-season coverage and implement `FeatureAvailabilityV1` plus same-kickoff tests.
3. Reproduce reference models on a non-frozen development corpus and prove training-serving parity.
4. Run only the existing authorized single minimal Phase 3A xG hypothesis; request new owner decisions for the broader xG/xGA, opponent-adjustment, or game-state experiments.
5. Run travel/load, H2H, lineup, squad-transition, goalkeeper, and pre-shot candidates one family at a time in the Section 12.6 order.
6. Build `FixtureDisplayTagsV1` as a non-blocking post-forecast sidecar and prove forecast parity under every tag state.
7. Implement `ForecastRevisionV1` and evaluate supported horizons without overwriting earlier forecasts.
8. Freeze and request authorization for the authoritative Evaluation V2 run; do not use Sprint 2's protected 280 targets.
9. Once separately authorized, build/qualify the minimal Rust parity and convergence harness before any new simulation-backed production enablement; advanced scenarios remain independently gated.
10. After separately approved activation, require `SimulationValidationArtifactV1` PASS for every new production fixture forecast by default (except an explicitly approved and labelled analytic-only fallback), and independent real-outcome evidence before any predictive promotion. Do not delay the already-authorized analytic Phase 3A research waiting for Rust.

### Frontend API integration

Status: PROPOSED

1. Audit existing fixture, forecast, simulation and capability APIs.
2. Reconcile implementation against the proposed public OpenAPI.
3. Register frontend API requirements FE-API-001 through FE-API-006.
4. Identify reusable endpoints before proposing new routes.
5. Review public metadata and simulation-summary fields for disclosure.
6. Approve and version compatible contract additions.
7. Implement missing fixture-listing and forecast-lifecycle capabilities.
8. Add contract, authorization, immutability and publication-state tests.
9. Verify frontend integration against the actual API.
10. Record implementation evidence and production enablement decisions.

Dependencies:

- verified repository API inventory;
- approved public schema;
- authoritative capability registry;
- approved forecast publication policy;
- simulation engine acceptance and activation where applicable.

This workstream may define interfaces and develop mock-driven UI
without claiming blocked production capabilities are enabled.

Frontend API implementation does not authorize new predictive models,
research experiments or Rust production activation.
