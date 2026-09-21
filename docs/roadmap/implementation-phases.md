# Implementation Phases

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Interpretation:** proposed dependencies/deliverables only. Phase 0 must *reconcile* the already recorded narrow Phase 3A authorization, not request it again. The minimal Rust engine may be authorized/built alongside probability infrastructure and is not a retroactive dependency of historical work or the bounded Phase 3A experiment. Each other phase needs its own scope and gate.

---

## 14. Implementation phases

### Engineering foundation across all phases

Engineering is not deferred to Phase 9. Before the first authoritative evaluation, deliver:

- architecture decision records for module boundaries, storage, job execution, and deployment shape;
- a reproducible local environment with seeded development data and one-command test execution;
- versioned database migrations and backward-compatible contract evolution rules;
- CI gates for formatting, linting, type checking, unit, integration, contract, leakage, and deterministic-replay tests;
- an artifact registry for datasets, features, models, calibrators, simulation builds, and API schemas;
- structured logs, metrics, traces, correlation IDs, dashboards, and initial SLOs;
- dependency locking, secret scanning, software-bill-of-materials generation, signed build provenance, and container scanning;
- infrastructure-as-code, staging parity, progressive deployment, rollback, backup, and restore exercises;
- cost budgets for ingestion, storage, training, replay, simulation, and forecast serving.

Every later phase adds its own tests, telemetry, runbook changes, migration impact, and rollback evidence to this foundation.

### Phase 0: reconcile status and authorize the new route

Deliverables:

- update tracked project status to reflect the closed shared-match-pace route;
- preserve the Sprint 2 failure and frozen 280-target firewall;
- reconcile, rather than recreate, the **existing** 20 September owner decision authorizing only bounded Phase 3A minimal xG research and Evaluation V2 policy/corpus design;
- propose a **new and separate** owner decision specifically for minimal Rust simulator implementation and its validation scope; do not infer authorization from this roadmap or from the previous research decision;
- define which phases are research-only and which can affect production;
- approve the initial architecture, ownership table, engineering SLO categories, and cost-accounting method.

Exit gate: status, evidence, and decision events agree.

### Phase 1: qualify the Evaluation V2 data foundation

Deliverables:

- competition-season coverage matrix;
- `TIER_A`/`TIER_A_PLUS`/`TIER_B`/`TIER_C`/`TIER_M` qualification reports;
- point-in-time dataset builder;
- same-kickoff batching;
- provider-semantic tests;
- rivalry registry schema and review workflow;
- immutable feature snapshot format;
- idempotent ingestion/backfill jobs, schema migration policy, and raw-to-snapshot lineage;
- training-serving feature-parity harness and fixed-model scoring test.

Exit gate: at least the minimum frozen corpus can be reproduced with no unresolved critical data issue.

### Phase 2: freeze Evaluation V2

Deliverables:

- versioned policy and corpus manifest;
- target firewall;
- reference implementations;
- metrics and bootstrap implementation;
- calibration and segment-report templates;
- dry run using non-authoritative targets.

Exit gate: explicit owner authorization for the authoritative run.

### Phase 3: xG/xGA expected-performance research

**Authorization boundary:** the 20 September decision permits only one minimal leakage-safe xG goal-model research hypothesis. The broader deliverables below are a proposed portfolio, **not** already authorized; each expanded family requires an explicit decision. Rust simulation is not a prerequisite for that existing minimal analytic research.

Deliverables:

- qualified shot-level xG model or approved provider xG adapter;
- `ExpectedPerformanceSnapshotV1`;
- opponent adjustment;
- multi-window and uncertainty features;
- ablations A-F;
- raw versus game-state-stratified and adjusted ablation;
- `PreShotThreatProfileV1` bounded shot-generation/suppression ablation after the core xG/xGA result;
- chronological evaluation report.

Exit gate: retain or reject the feature family based on frozen thresholds.

### Phase 4: H2H and rivalry research

Deliverables:

- `H2HContextV1`;
- `RivalryDefinitionV1` registry;
- residual replay from historical out-of-sample predictions;
- decay, shrinkage, and pair-random-effect candidates;
- entropy, goal covariance, continuity, and model-versus-H2H discrepancy features;
- `MatchupIntelligenceV1` wrapper with component coverage and uncertainty;
- counterfactual mean, dispersion, and correlation simulation design;
- matched-control derby analysis for display-tag validation only;
- placebo pair analysis;
- ablation report.

Exit gate: H2H candidates are accepted or rejected independently; derby status remains display-only regardless of the descriptive result.

### Phase 5: forecast diagnostics and frontend tags

Deliverables:

- `ForecastRiskAssessmentV1`;
- `FixtureDisplayTagsV1` generated after the immutable forecast;
- OOD, entropy, disagreement, data-risk, and drift components;
- `PostMatchShockLabelV1`;
- risk-band calibration analysis;
- API reason codes;
- frontend badge and warning policy that preserves the complete original forecast.

Exit gate: tags show stable, honest descriptive meaning or the aggregate unpredictability tag is removed in favour of component tags. Forecast parity with tags disabled must pass.

### Phase 6: dynamic team strength and match context

Deliverables:

- state-space or Bayesian dynamic challenger;
- competition and promoted-team priors;
- attack/defence change handling;
- manager/transfer-window change analysis where data supports it;
- comparison with time-decayed Dixon-Coles;
- `TravelAndFixtureLoadV1` with neutral-venue and timezone handling;
- separate rest, travel, congestion, and combined-load ablations;
- competition-strength, promoted-team, and objective priority-context candidates.

Exit gate: predictive and operational gates pass or the simpler reference remains champion.

### Phase 7: lineup and player context

Deliverables:

- availability and selection as separate probabilities;
- top-K lineup scenarios and residual mass;
- predicted versus confirmed forecast artifacts;
- `LineupImpactV1` attack, defence, goalkeeper, and set-piece deltas;
- XI, positional-unit, minutes-together, and formation-continuity features;
- `SquadTransitionV1` and team-plus-player rating ablations;
- `GoalkeeperShotStoppingV1` post-shot ablation where qualified;
- multidimensional player effects with uncertainty;
- strict fallback when lineup data is absent.

Exit gate: lineup-aware forecasts improve the relevant pre-lineup and confirmed-lineup contracts separately.

### Phase 8: mandatory Rust simulation validation and probability products

**Change in sequencing:** do not defer the *minimal Rust parity/validation engine* until after every advanced model family. Once separately authorized, implement its reference distribution contract and acceptance harness alongside foundational probability work, while leaving more complex scenario extensions in Phase 8. This is a new gate for future simulation-backed delivery, not a retroactive dependency of historical or the narrowly authorized Phase 3A research.

Deliverables:

- reconcile existing `rust/simulation-core` and Python/Go interfaces; preserve the repository's existing language ownership and avoid rebuilding working analytical components;
- approved parameter and coherent calibrated distribution contract;
- minimal deterministic Rust score sampler with independent seed schedule and bounded work;
- immutable `SimulationValidationArtifactV1` with input hash, engine version, run counts, convergence, parity, tail tests, and reason codes;
- reference-fixture analytic parity and multi-batch convergence suite;
- strict `PASS` / `FAIL` / `INCONCLUSIVE` gating plus explicit outage handling and idempotent publication;
- later, separately authorized score dependence, scenario uncertainty, and H2H same-seed counterfactual extensions;
- real-outcome chronological comparison only under the authorized evaluation policy; do not label numerical parity as calibration.

Exit gate: Rust engine and artifact validation pass; after separately authorized activation all new production fixture publication defaults to a required PASS, with only an explicitly approved labelled analytic-only fallback. Any predictive improvement claim additionally needs real-outcome evidence and separate promotion authorization.

### Phase 9: production API and monitoring

Deliverables:

- immutable prediction endpoints;
- `ForecastRevisionV1` and explicit supported forecast horizons;
- revision information-value reports and non-overwriting forecast history;
- model/feature/calibration/risk provenance;
- drift and calibration dashboards;
- shadow deployment;
- rollback and recovery proof;
- alerting by competition, model, target, and risk segment.

Exit gate: SLOs, security, monitoring, and rollback tests pass.
