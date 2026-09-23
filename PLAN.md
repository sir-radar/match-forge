# MatchForge implementation plan

> Revision: 22 September 2026 — added proposed prediction-improvement research candidates to the 21 September repository reconciliation.
> Status: **TRACKED PROPOSED ROADMAP**. This plan records sequencing and constraints. It does not authorize application code, change a frozen result, or create an owner decision.
> Authority order: checked-in repository evidence and immutable evaluation records → approved owner decision events → versioned approved contracts → this proposed plan → research proposals. Where they conflict, stop and reconcile rather than overwriting evidence.

## 1. Mission and scope

MatchForge is a provider-neutral football forecasting and simulation platform that produces reproducible, coherent and calibrated probability distributions. This plan governs **sequence, ownership, dependencies, authorization and release gates**; detailed model research, contracts, API proposals and runbooks live in linked documents. No proposed feature is a production commitment.

The product aims to model changing attack/defence strength, qualified xG/xGA and other point-in-time context, uncertainty, coherent match/score/goal/BTTS/clean-sheet distributions and separately approved corner products. Residualized H2H is a challenger, not a shortcut. Derby and unpredictability remain **display-only**. All published forecast revisions preserve their predecessors.

## 2. Preserved evidence and permissions

Repository status and retained evidence record: Phase 1B `PASS`; Phase 2B `PASS`; Sprint 2 baseline immutable `FAIL` / `RETAIN_FAIL_AND_STOP`; `DCV3_SHARED_MATCH_PACE_MIXTURE_V1` `TERMINAL_ROUTE_FAIL` at the `60/10` fold (`kappa = 0` boundary); the frozen **280 Sprint 2 targets remain inaccessible** to new routes; no promotion occurred. Do not rewrite or rerun that evidence. See [current status](docs/status/current-state.md).

Owner decision `RETAIN_SPRINT2_FAIL_CLOSE_SHARED_PACE_AND_AUTHORIZE_PHASE3_RESEARCH_V1`, recorded on **20 September 2026**, authorizes **only one bounded, minimal leakage-safe Phase 3A xG goal-model research hypothesis** using qualified approved Tier-A data and Evaluation V2 **policy/corpus design and pre-registration**. Overall Phase 3 remains blocked; broader xG/xGA feature families are **not** included. An authoritative Evaluation V2 run needs its **own** decision after all policy, corpus, references and thresholds are frozen. Rust implementation, simulation evaluation, production activation and expanded scenarios need distinct authorizations. Do not request the recorded narrow decision again or broaden its scope.

## 3. Hard invariants

1. Every training/replay/serving feature is versioned, sourced and demonstrably available at the historical knowledge cutoff. Preserve immutable observations, publication/correction times, missingness and quarantine. Batch equal-kickoff fixtures.
2. Replay, training and production share the same versioned feature implementation. Use chronological evaluation and independent out-of-sample calibration against **real outcomes**.
3. Generate a coherent joint distribution and validated parameters **before** Rust sampling. Never let a simulator infer team strength, repair calibration, train a model or change probabilities because of sampling noise.
4. Seal an immutable forecast candidate, compute reproducible probability/artifact hashes, then run separately authorized Rust validation. After separately approved activation, a **new production fixture forecast requires a linked `SimulationValidationArtifactV1` with `PASS` by default**. Only a separately owner-approved, explicitly labelled `ANALYTIC_ONLY` exception may bypass this production gate. Historical artifacts and the already authorized analytic Phase 3A research are not retroactively gated.
5. Simulation establishes parity, numerical integrity and Monte Carlo convergence—not predictive calibration. Calibrated predictive quality requires held-out real matches, proper scoring rules and reliability analysis.
6. Attach optional enrichment **after publication**. Derby, unpredictability, risk bands, model disagreement and other tags cannot influence feature matrices, model parameters, calibration, simulation inputs, revisions or probability post-processing. Enrichment failure cannot invalidate a valid forecast or alter its hashes.
7. Each research family requires pre-registration, independent authorization for its scope, leakage-safe ablation and an explicit decision. No frozen failure becomes a pass through retesting or threshold changes.
8. Research acceptance, simulation acceptance, predictive promotion and production enablement are distinct approvals. Never infer any from roadmap text. Versioned public APIs do not expose internal diagnostics or provenance by default.

## 4. Authoritative artifact and publication boundaries

```text
qualified providers → immutable raw → identity/quarantine → point-in-time snapshots
  → shared feature library → approved model → validated parameters
  → coherent out-of-sample calibrated distribution → SEALED candidate + hashes
  → [separately authorized] Rust sampler → validation evidence PASS
  → atomic/recoverable publish of unchanged ForecastArtifactV1 + linked validation
  → optional ForecastEnrichmentV1 sidecar → public API projection
  → monitoring, audit and post-match evaluation (separate artifacts)
```

The **analytic forecast candidate** can be scientifically complete internally before simulation; it is not necessarily **production publishable**. Once the mandatory Rust route is enabled, publishing requires validation `PASS` and eligible capability unless an approved analytic-only exception exists. The forecast and validation are separately immutable; optional enrichment cannot be a publication dependency. See [artifact boundaries](docs/architecture/artifact-boundaries.md), [forecast contract](docs/contracts/forecast-artifact-v1.md), [simulation contract](docs/contracts/simulation-validation-v1.md), [publication state machine](docs/simulation/publication-state-machine.md), and [enrichment parity](docs/contracts/forecast-enrichment-parity-v1.md).

## 5. Architectural and ownership policy

Start with a modular monolith and durable, independently scalable workers. Keep Python accountable for statistical modelling/calibration and the separately authorized Rust core accountable for deterministic sampling and numerical verification; reconcile actual Go/Python/Rust interfaces before change. Cross-module boundaries are typed and versioned. Additional deployables require documented scaling, fault isolation or ownership evidence. See [module boundaries](docs/architecture/module-boundaries.md) and [owners and dependencies](docs/governance/ownership-and-dependencies.md).

Exactly one system owns each concern: adapters own provider semantics; resolver owns identities; frozen manifest owns evaluation membership; feature library owns transforms; registries own model/calibrator state; forecast artifact owns forecast probabilities; Rust validation artifact owns simulation evidence; enrichment sidecar owns tags; decisions/registers own authorization; capability registry owns enablement; OpenAPI owns public fields. The frontend does not invent provenance or simulation approval.

### Frontend-driven API requirements

The frontend design may identify additional public API capabilities
needed to deliver the approved MatchForge product experience.

Record these requirements in:
`docs/frontend/api-requirements.md`.

Requirements must be reconciled against the actual repository before
an endpoint or field is described as implemented or verified.

Approved API additions must:

- preserve immutable forecast and simulation artifact contracts;
- expose only authorized public data;
- respect capability and competition-tier availability;
- preserve access to previously published forecasts;
- distinguish unpublished candidates from published forecasts;
- remain backward-compatible or use an explicitly versioned migration;
- pass contract, authorization, publication-state and regression tests.

Frontend requirements may propose new API capabilities but cannot
authorize model research, simulation activation, predictive promotion
or production enablement.

The versioned OpenAPI contract remains the source of truth for public
response fields.

Implementation sequencing and acceptance criteria are maintained in
the roadmap and engineering documentation.

## 6. Research portfolio and evaluation

Maintain simple goals-only/dynamic attack-defence references. Test one independently authorized challenger family at a time: minimal Phase 3A xG first (scope already recorded); subsequently, only under new permissions, xG/xGA and opponent/game-state adjustments, travel/rest, dynamic strength, residual H2H/matchups, lineups/squad context, goalkeeper post-shot, pre-shot threat, horizons/revisions and ensembles. Derby and diagnostic tag validity are separate descriptive-only workstreams. H2H counterfactuals and complex simulation scenarios require their own gates. No candidate is automatically promoted for complexity or a favourable single slice.

Authoritative Evaluation V2 needs a **new, separately approved** frozen policy, independent corpus/target firewall, source and cutoff semantics, same-kickoff grouping, chronological folds, calibrator windows, primary proper scores, reliability metrics, segments, paired uncertainty, practical threshold, stopping rule and compute budget. Do not fill unset values with defaults. The 280 frozen targets are excluded. See [research portfolio](docs/governance/feature-portfolio.md), [feature research](docs/models/feature-research.md), [Evaluation V2](docs/evaluation/evaluation-v2-policy.md), [calibration](docs/models/calibration-policy.md), [experiment register](docs/governance/experiment-register.md) and [promotion gates](docs/evaluation/promotion-gates.md).

### Prediction-improvement candidates

This inventory makes existing research directions and further proposals visible in one place. It does **not** authorize implementation, data access, evaluation, promotion or production use. The priority order below is a proposal, not a frozen experiment order. Beyond the existing narrow xG research permission, each candidate needs qualified point-in-time data, a bounded pre-registered comparison against the same simple reference, chronological out-of-sample evidence, calibration and segment checks, and a separate owner decision. Do not combine untested candidates or reuse the frozen Sprint 2 targets.

**Already in the research portfolio or supporting specifications:**

1. Broaden qualified Tier-A data to multiple seasons and competitions before claiming generalizable xG gains; retain source lineage, publication times and missingness.
2. Test the already authorized **single minimal prior-only xG-for** hypothesis first, within its exact approved scope. Its remaining blocking fields must be resolved before implementation or fitting.
3. Under new scope approval, compare xG-for with xG-for plus xGA and opponent-adjusted xG/xGA; keep shot volume, chance quality and game-state adjustments as separately tested additions.
4. Test game-state-adjusted xG/xGA using prior matches' score state, red cards and reliable 11v11 intervals; no target-match events may enter a pre-match forecast.
5. Test dynamic attack/defence or state-space strength against the existing time-decayed goals-only reference.
6. Test objective rest, congestion, travel and manager-transition inputs with coverage and missingness reported.
7. Test predicted/confirmed lineups, player strength and squad turnover as distinct, point-in-time candidates; preserve uncertainty in unconfirmed lineups.
8. Test shrunk goalkeeper post-shot performance only where xGOT, keeper identity and historical coverage qualify.
9. Test pre-shot territory and possession progression—such as box entries, deep completions and field tilt—against the xG/xGA reference.
10. Test ensembles only after constituent models show independent out-of-sample value; fit weights on a separate prior calibration window.
11. Evaluate forecast horizons, information-driven revisions and horizon-specific calibration without overwriting earlier forecasts.
12. Test residualized, decayed and shrunk H2H from prior out-of-sample forecasts; raw H2H is not a production shortcut.

**Additional proposals requiring their own decisions:**

1. General hierarchical partial pooling across teams, competitions and seasons, including promoted teams and sparse early-season histories. Compare with existing team/competition priors; quantify whether borrowing strength helps rather than assuming it does.
2. Carry uncertainty in estimated attack, defence, xG and lineup inputs into the joint score distribution. Compare held-out calibration, proper scores and interval coverage with point-estimate forecasts.
3. Calibrate the **whole score distribution** or its generating parameters, not independently adjusted 1X2 and binary outputs. Derive all markets from the final coherent distribution and test both calibration and sharpness.
4. Qualify provider-specific xG semantics and, only if cross-provider training is needed, test a versioned harmonization with mapping uncertainty. Never merge raw xG values merely because providers use the same label.
5. Record timestamped bookmaker consensus as an **external benchmark** for evaluation and missing-information diagnostics only. Raw odds remain excluded from baseline model features; predictive use would require a separate policy and owner decision.
6. Test competition-format context separately for league, knockout and two-leg fixtures, including aggregate-score state where known before kickoff. Define 90-minute, extra-time and shootout targets separately; do not mix their outcomes.
7. Test competition- and time-varying home advantage using qualified neutral venue, attendance, behind-closed-doors, shared-stadium, surface or altitude history. Derby and rivalry tags remain display-only.
8. Test governed structural-break handling for manager, squad, tactical, promotion or relegation changes against fixed time decay; estimate change signals only from information available at the forecast cutoff.
9. If score-distribution diagnostics justify it, register one alternative dependence-aware score model, such as bivariate Poisson, against Dixon–Coles/NB2. This must not reopen the terminal failed shared-match-pace route under another name.
10. Run prospective shadow scoring and drift monitoring on untouched future forecasts. Drift triggers review and a newly authorized retraining or recalibration decision, never automatic promotion or live probability edits.

Suggested dependency order: independent qualified corpus and Evaluation V2 freeze → minimal xG-for → separately authorized hierarchical/dynamic strength and xGA/opponent adjustments → coherent full-score calibration and parameter uncertainty → qualified lineup/player context → ensemble. The other candidates enter only through their own evidence-backed proposals. Rust sampling and display tags may validate or explain a forecast but do not improve its underlying predictive probabilities by themselves.

## 7. Mandatory Rust policy (conditional on authorization and acceptance)

The minimum Rust implementation samples an **already approved coherent distribution** with independent recorded seeds and produces reproducible evidence for analytic parity, event-specific confidence intervals, convergence across batches, tails, normalization, precision and resource/cost budgets. Initial reference counts of 1,000/10,000/100,000 are engineering starting points, **not pass thresholds**. Record `PASS`, `FAIL` or `INCONCLUSIVE`; a timeout or unresolved tail must never be called `PASS`. For simulation-capable promotion candidates, require representative simulation evidence **plus separate real-outcome evaluation and owner approval**. Advanced timing, cards, lineups, corners and H2H scenarios are separately scoped.

See [mandatory validation](docs/simulation/mandatory-validation.md), [authorization proposal](docs/governance/simulation-authorization-proposal.md) and [simulation failure runbook](docs/operations/runbooks/simulation-failure.md). No section here authorizes implementation or activation.

## 8. Gated execution sequence

| Gate                         | Delivery                                                                                                                                                                                                                                                                 | Approval/exit condition                                                  |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| G0 — reconcile               | Compare supplied documentation with actual code, `docs/project-status.json`, owner events, current artifacts, interfaces and tests; preserve failures; draft separate simulation decision.                                                                               | Verified provenance and scope; no changed history.                       |
| G1 — foundation              | Provider/data qualification, identity, raw/correction lineage, point-in-time views, same-kickoff grouping, versioned feature parity, idempotent jobs, migration/replay/security and recovery controls.                                                                   | Reproducible fixtures and operating gates; no invented passed statuses.  |
| G2 — Evaluation V2 design    | Freeze independent corpus, firewall, policy, references, metrics, thresholds, tests; dry-run on non-authoritative samples.                                                                                                                                               | **Distinct owner authorization** before authoritative evaluation.        |
| G3 — bounded research        | Execute _only_ the already authorized narrow Phase 3A hypothesis; register ablation and evidence. Expand to any additional family only after new scope approval.                                                                                                         | Chronological evidence; accept/reject/defer event.                       |
| G4 — optional families       | Sequential, individually gated portfolio: H2H, tags, dynamic/context, lineup/squad, keeper/threat, revisions and ensembles.                                                                                                                                              | Data qualification, pre-registration, no regression and owner decisions. |
| G5 — minimal Rust validation | Once separately authorized, reconcile scaffold and implement accepted score sampler, parity suite, immutable sidecar, explicit failure states and publish linkage. Can run alongside foundational probability work; **not prerequisite for Phase 3A analytic research**. | Engine acceptance and **separate** production activation decision.       |
| G6 — release                 | Approved model/calibrator, coherent forecast, Rust `PASS` per newly published production fixture (or approved labelled fallback), API projection, observability, shadow, cost and rollback.                                                                              | Promotion and enablement recorded as separate events.                    |

This is a **dependency graph, not a claim that phases are already completed**. Detailed source deliverables remain in [implementation phases](docs/roadmap/implementation-phases.md) and [immediate backlog](docs/roadmap/immediate-backlog.md).

## 9. Definition of done — five distinct objects

- **Sealed analytic candidate:** eligible feature snapshot, resolved identity, approved model/calibrator for intended tier, coherent distribution, missingness, provenance and reproducible hashes. Internal completion ≠ production release.
- **Simulation validation:** independently authorized engine and threshold policy, matching candidate hash, validated seeds/batches/parity/convergence/tails/resources, immutable evidence with `PASS` (otherwise `FAIL` or `INCONCLUSIVE`). Simulation never edits candidate bytes.
- **New production forecast:** eligible capability and release approval, sealed candidate plus linked simulation `PASS` published atomically/recoverably, or separately approved and visibly labelled analytic-only exception. Old published artifacts remain retrievable if new validation fails.
- **Optional enrichment:** computed only from already published forecast and cutoff-eligible side evidence; `forecast_effect=false`; unchanged forecast and validation hashes. Failure is nonblocking.
- **Predictive promotion:** authorized untouched historical evaluation against actual outcomes, passing statistical/segment/operational gates and owner decision. Numerical convergence alone is insufficient.

Full [definition-of-done checklist](docs/engineering/definitions-of-done.md).

## 10. Change and safety instructions

Apply this roadmap through scoped repository changes. Do not overwrite `docs/project-status.json`, decision events, approved API contracts, registries, Rust code, or tests without the required authorization and compatibility review. Compare existing names and interfaces, use additive migrations where required, and run the relevant diff and tests. Verify artifact hashes and protected-corpus access before and after applicable changes. Use [reconciliation checklist](docs/reconciliation/adoption-checklist.md), [capability registry](docs/operations/capability-registry.md), [decision template](docs/governance/decision-record-template.md), [rollback policy](docs/operations/rollback-policy.md) and [API compatibility policy](docs/api/compatibility-policy.md). The proposed OpenAPI file does **not** assert that its endpoints currently exist.

## 11. Document map

Use [documentation index](docs/README.md) as the canonical map. Archived [supplied original plan](docs/references/supplied-plan-2026-09-21.md) remains available for line-by-line comparison; it is not a second authority. This compact plan deliberately does not repeat detailed schema fields or experiment recipes.
