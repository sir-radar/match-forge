# MatchForge documentation index

**Root [PLAN.md](../PLAN.md) is the compact proposed execution roadmap.** It sequences work and sets release gates; it does not authorize anything by itself. Supporting docs preserve the original technical research and separate immutable forecasts, mandatory Rust evidence, optional enrichment, evaluation authority and public delivery. Repository evidence and owner decisions are higher authority than any roadmap.

## Start here

- [AGENTS.md](../AGENTS.md) and [CLAUDE.md](../CLAUDE.md): engineering rules and the order in which sources win a conflict.
- [Current project status](project-status.json) (machine-readable, checked by `make project-status-check`), its [notes](project-status.md) and the [readable summary](status/current-state.md).
- [Adoption checklist](reconciliation/adoption-checklist.md) before starting any roadmap task.

## Authority order

1. Current repository-owner requirements; applicable `AGENTS.md` files.
2. Resolved owner decisions and append-only decision events; `project-status.json` and immutable evidence.
3. Approved ADRs, policies, schemas, migrations and versioned contracts.
4. [PLAN.md](../PLAN.md) and its follow-on roadmaps (below).
5. Repository documentation, then research proposals.

Every file marked *proposed* under `docs/` is a proposal, not an approval. A stale roadmap statement never overrides a newer owner decision.

## Roadmaps

- [PLAN.md](../PLAN.md): the control-plane roadmap and gate sequence.
- [Post-redesign product roadmap (F0–F11)](../MatchForge_Post_Redesign_Extensible_Football_Product_Implementation_Plan_v2_2026-11-09.md): follow-on product work. It sits under PLAN.md's gates and needs its own task authorization.
- [Unified architecture investigation](architecture/unified-redesign-2026-11-10/README.md): planning recommendations from 10 November, with its [roadmap](architecture/unified-redesign-2026-11-10/roadmap.md), the proposed [P09-01 historical-completeness plan](architecture/unified-redesign-2026-11-10/p09-01-historical-completeness-plan.md) and [ADR 0005](adr/0005-unified-architecture-evolution.md).
- [Full phase deliverables](roadmap/implementation-phases.md) and [immediate backlog](roadmap/immediate-backlog.md): sections extracted from the original plan.

## Architecture / data

- [Architecture](architecture.md), [data platform architecture](data-platform-architecture.md), [data model](data-model.md), [temporal model](temporal-model.md)
- [Artifact and publication boundaries](architecture/artifact-boundaries.md)
- [Module layout and source-of-truth ownership](architecture/module-boundaries.md)
- [Explicit owner and dependency register](governance/ownership-and-dependencies.md)
- [Provider qualification and data programme](data/data-programme.md), [source acquisition](source-acquisition.md), [competition rules](competition-rules.md)
- Ingestion and storage: [canonical ingestion](canonical-ingestion.md), [event datasets](event-datasets.md), [data validation](data-validation.md), [ingestion reports](ingestion-reports.md), [kickoff claims](kickoff-claims.md), [lifecycle claims](lifecycle-claims.md), [recovery](recovery.md), [CLI](cli.md)
- [Entity crosswalk summary](entity-crosswalk-summary.md)

## Contracts

- [Immutable forecast](contracts/forecast-artifact-v1.md), [canonical hashes](contracts/canonical-hashing-v1.md), [Rust evidence](contracts/simulation-validation-v1.md)
- [Optional enrichment](contracts/forecast-enrichment-v1.md), [parity checks](contracts/forecast-enrichment-parity-v1.md)
- [Live match context](contracts/live-match-context-v1.md), [contextual goal model](contracts/contextual-goal-model-v1.md)
- [Source-derived feature contracts](contracts/): rivalry, expected performance, H2H, cutoff availability, matchup, travel/load, lineup, revision, squad transition, goalkeeper and pre-shot threat. Inspect individual files in the directory.

## Models, evaluation and experimentation

- [Backtesting](backtesting.md), [model governance](model-governance.md), [Sprint 2 backtesting contract](sprint2-backtesting-contract.md), [walk-forward target plan](walk-forward-target-plan.md), [Sprint 2 phase gate](sprint2-phase-gate.md)
- Baselines: [team Elo](team-elo.md), [Dixon–Coles](dixon-coles.md), [corner models](corner-models.md), [corner labels](corner-labels.md)
- [Evaluation V2 freeze/metrics and authorization](evaluation/evaluation-v2-policy.md), [promotion gates](evaluation/promotion-gates.md)
- [Research programme and model ladder](models/feature-research.md), [calibration](models/calibration-policy.md)
- [Phase 3A minimal xG draft pre-registration](governance/phase3a-minimal-xg-preregistration.md)
- [Portfolio dependency table](governance/feature-portfolio.md), [feasibility notes](governance/feasibility-matrix.md), [experiment ledger template](governance/experiment-register.md)
- [Decision record template](governance/decision-record-template.md), [decision events directory](governance/decision-events/README.md), [minimal Rust authorization proposal](governance/simulation-authorization-proposal.md), [P02 forecast re-evaluation proposal](governance/p02-forecast-reevaluation-proposal.md)
- PitchAPI protocol policies: [retrospective V1](evaluation/pitchapi-retrospective-evaluation-v1-policy.md), [domain-stratified V2 metrics](evaluation/pitchapi-domain-stratified-evaluation-v2-metrics.md), Rust policies for [V2](simulation/pitchapi-domain-stratified-v2-rust-policy-proposal.md), [V3](simulation/pitchapi-domain-stratified-v3-rust-policy.md) and [V4](simulation/pitchapi-domain-stratified-v4-rust-policy.md)

## Simulation, delivery and operations

- [Mandatory validation policy](simulation/mandatory-validation.md), [publication state machine](simulation/publication-state-machine.md), [failure runbook](operations/runbooks/simulation-failure.md), [P02 history re-qualification runbook](operations/runbooks/p02-history-requalification.md)
- [OpenAPI for the MVP API](api/openapi.yaml), [compatibility/privacy](api/compatibility-policy.md), [superseded original API illustration](api/future-api-illustration.md), [frontend API requirements](frontend/api-requirements.md)
- [Capabilities and enablement](operations/capability-registry.md), [rollback](operations/rollback-policy.md), [monitoring](operations/forecast-monitoring.md)
- [P0 storage protection and recovery evidence](operations/storage-protection-2026-11-11.md)
- [Storage lifecycle operations, capacity policy and approval-only resource manifest](operations/storage-lifecycle.md)
- [Storage consolidation and Admin-controlled cleanup, 12 November 2026](operations/storage-consolidation-2026-11-12.md)
- [Football-Data.co.uk manifest path digests, 12 November 2026](operations/fduk-manifest-path-digests-2026-11-12.md): 47 legacy snapshots, [evidence](evidence/fduk-manifest-path-digests-2026-11-12.json), proposed raw-file bindings and guard
- Storage operating rollout, 12 November 2026: [owner decision](evidence/owner-decision-authorize-storage-operating-rollout-2026-11-12.json), [evidence](evidence/storage-operating-rollout-2026-11-12.json); candidate database deletion: [owner decision](evidence/owner-decision-approve-storage-candidate-deletion-2026-11-12.json), [evidence](evidence/storage-candidate-deletion-2026-11-12.json); recovery-scope migration `202611120200` ratified as applied: [owner decision](evidence/owner-decision-ratify-recovery-scope-migration-2026-11-12.json)
- Recovery-scope disposition rehearsal on a restored copy, 12 November 2026 (not an owner decision): [evidence](evidence/recovery-disposition-rehearsal-2026-11-12.json)

## Engineering standards

- [Backend](backend-engineering.md) and [frontend](frontend-engineering.md) standards, [testing](testing.md), [test matrix](engineering/test-matrix.md), [test fixtures](test-fixtures.md), [CI](ci.md)
- [Engineering controls](engineering/operational-controls.md), [five definitions of done](engineering/definitions-of-done.md), [governed commit invariants](engineering/governed-commit-invariants.md), [foundation hardening](foundation-hardening.md)
- [Git delivery](git-delivery.md), [PR template](pr-template.md), [review checklist](review-checklist.md), [writing style](writing-style.md), [model routing](engineering/model-routing.md), [optional code intelligence](engineering/code-intelligence.md)
- [ADRs](adr/0001-python-managed-runtime-pin.md): [0002](adr/0002-go-127-golangci-analysis-scope.md), [0003](adr/0003-use-commit-pinned-source-acquisition.md), [0004](adr/0004-project-status-v2-owner-decisions.md), [0005](adr/0005-unified-architecture-evolution.md)

## MVP product and dated reports

Dated reports record what was true when they were written. Do not edit them to match later state; the current state is in [status](status/current-state.md).

- MVP: [completion audit](MVP-COMPLETION-AUDIT.md), [data coverage](MVP-DATA-COVERAGE.md), [external prediction sources](MVP-EXTERNAL-PREDICTION-SOURCES.md), [historical backfill](MVP-HISTORICAL-BACKFILL.md), [operational providers](MVP-OPERATIONAL-PROVIDERS.md), [research pause and resume](MVP-RESUME-RESEARCH.md)
- Audits and remediation: [codebase audit](CODEBASE_AUDIT_REPORT.md), [remediation](CODEBASE_REMEDIATION_REPORT.md), [identity resolution](IDENTITY_RESOLUTION_IMPLEMENTATION_REPORT.md)
- V4: [implementation](V4_IMPLEMENTATION_REPORT.md), [identity admission recovery](V4_IDENTITY_ADMISSION_RECOVERY_REPORT.md), [issue 2 qualification](V4_ISSUE_02_QUALIFICATION_REPORT.md), [issue 2 unblocking](V4_ISSUE_02_UNBLOCKING_REPORT.md), [issue 3 provider expansion](V4_ISSUE_03_PROVIDER_EXPANSION_REPORT.md), [issue 4 access recovery](V4_ISSUE_04_ACCESS_RECOVERY_REPORT.md)
- Immutable evidence and owner-decision records live in `docs/evidence/` (not listed one by one). Add new evidence as new files; never rewrite existing ones.

## Auditing and source preservation

- [How to integrate without losing prior progress](reconciliation/adoption-checklist.md); [change log / Astra mapping](reconciliation/change-log.md)
- [Explicit exclusions](governance/exclusions.md), [research bibliography](references/research-basis.md)
- [Exact supplied PLAN archive](references/supplied-plan-2026-09-21.md), [exact Astra feedback archive](references/astra-feedback-2026-09-21.md)

**Ownership:** Each specialized contract owns field-level rules; root plan owns intent, sequence and release gates; registered evidence/events govern whether a capability is actually authorized/active. Legacy source extracts are design reference and must not override a newer approved contract.
