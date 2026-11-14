# MatchForge documentation index

**Root [PLAN.md](../PLAN.md) is the compact proposed execution roadmap.** It sequences work and sets release gates; it does not authorize anything by itself. Supporting docs preserve the original technical research and separate immutable forecasts, mandatory Rust evidence, optional enrichment, evaluation authority and public delivery. Repository evidence and owner decisions are higher authority than any roadmap.

## Start here

- [AGENTS.md](../AGENTS.md) and [CLAUDE.md](../CLAUDE.md): engineering rules and the order in which sources win a conflict.
- [Current project status](project-status.json) (machine-readable, checked by `make project-status-check`; contract in [ADR 0004](adr/0004-project-status-v2-owner-decisions.md)) and the [readable summary](status/current-state.md).
- [Documentation lifecycle](#documentation-lifecycle) before adding, finishing or retiring documentation.

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
- The original 21 September plan, including its phase deliverables, is archived in [supplied-plan-2026-09-21.md](references/supplied-plan-2026-09-21.md). Comparison material only.

## Architecture / data

- [Architecture](architecture.md), [data platform architecture](data-platform-architecture.md), [data model](data-model.md), [temporal model](temporal-model.md)
- [Artifact and publication boundaries](architecture/artifact-boundaries.md)
- [Explicit owner and dependency register](governance/ownership-and-dependencies.md)
- [Source acquisition](source-acquisition.md), [competition rules](competition-rules.md)
- Ingestion and storage: [canonical ingestion](canonical-ingestion.md), [event datasets](event-datasets.md), [data validation](data-validation.md), [ingestion reports](ingestion-reports.md), [kickoff claims](kickoff-claims.md), [lifecycle claims](lifecycle-claims.md), [recovery](recovery.md), [CLI](cli.md)
- [Entity crosswalk summary](entity-crosswalk-summary.md)

## Contracts

- [Immutable forecast](contracts/forecast-artifact-v1.md), [canonical hashes](contracts/canonical-hashing-v1.md), [Rust evidence](contracts/simulation-validation-v1.md)
- [Optional enrichment](contracts/forecast-enrichment-v1.md), [parity checks](contracts/forecast-enrichment-parity-v1.md)
- [Live match context](contracts/live-match-context-v1.md), [contextual goal model](contracts/contextual-goal-model-v1.md)
- [Source-derived feature contracts](contracts/): rivalry, expected performance, H2H, cutoff availability, matchup, travel/load, lineup, revision, squad transition, goalkeeper and pre-shot threat. Inspect individual files in the directory.

## Models, evaluation and experimentation

- [Backtesting](backtesting.md), [Sprint 2 walk-forward and scoring](backtesting.md#sprint-2-walk-forward-and-scoring), [Sprint 2 phase gate](sprint2-phase-gate.md)
- [Model governance](model-governance.md), [Sprint 2 baseline contracts](model-governance.md#sprint-2-baseline-contracts)
- [Evaluation V2 freeze/metrics and authorization](evaluation/evaluation-v2-policy.md)
- [Phase 3A minimal xG draft pre-registration](governance/phase3a-minimal-xg-preregistration.md)
- [Portfolio dependency table](governance/feature-portfolio.md), [experiment ledger template](governance/experiment-register.md)
- [Decision record template](governance/decision-record-template.md), [decision events directory](governance/decision-events/README.md), [minimal Rust authorization proposal](governance/simulation-authorization-proposal.md), [P02 forecast re-evaluation proposal](governance/p02-forecast-reevaluation-proposal.md), [Phase 3A xG-for and Evaluation V2 freeze proposal](governance/phase3a-xg-for-evaluation-v2-freeze-proposal.md), [PitchAPI V5 calibration successor package](governance/pitchapi-v5-calibration-successor-decision-package.md) (superseded)
- PitchAPI protocol policies: [retrospective V1](evaluation/pitchapi-retrospective-evaluation-v1-policy.md), [domain-stratified V2 metrics](evaluation/pitchapi-domain-stratified-evaluation-v2-metrics.md), Rust policies for [V2](simulation/pitchapi-domain-stratified-v2-rust-policy-proposal.md), [V3](simulation/pitchapi-domain-stratified-v3-rust-policy.md) and [V4](simulation/pitchapi-domain-stratified-v4-rust-policy.md)

## Simulation, delivery and operations

- [Publication state machine](simulation/publication-state-machine.md), [failure runbook](operations/runbooks/simulation-failure.md), [P02 history re-qualification runbook](operations/runbooks/p02-history-requalification.md)
- [OpenAPI for the MVP API](api/openapi.yaml), [compatibility/privacy](api/compatibility-policy.md), [frontend API requirements](frontend/api-requirements.md)
- [Capabilities and enablement](operations/capability-registry.md), [rollback](operations/rollback-policy.md), [monitoring](operations/forecast-monitoring.md)
- [P0 storage protection and recovery evidence](operations/storage-protection-2026-11-11.md)
- [Storage cleanup proposal](recovery-cleanup-proposal.md) (P0 proposal; the storage lifecycle below is what was built)
- [Storage lifecycle operations, capacity policy and approval-only resource manifest](operations/storage-lifecycle.md)
- [Storage lifecycle rollout, 13 November 2026](evidence/storage-lifecycle-rollout-2026-11-13.json): release `878cd0d`, migrations through `202611130300`, policy active
- [Local storage cleanup, 13 November 2026](operations/local-storage-cleanup-2026-11-13.md): 134.1 GB deleted, 148.2 GB reclaimed, [evidence](evidence/local-storage-cleanup-2026-11-13.json)
- [Storage audit and dispositions, 13 November 2026](operations/storage-audit-2026-11-13.md): remaining databases, host resources and open owner decisions, [evidence](evidence/storage-audit-2026-11-13.json)
- [Remaining non-operating databases: review, 12 November 2026](operations/remaining-database-review-2026-11-12.md): 23 compared, 18 reviewed, [evidence](evidence/remaining-database-unique-rows-2026-11-12.json)
- [Storage consolidation and Admin-controlled cleanup, 12 November 2026](operations/storage-consolidation-2026-11-12.md)
- [Rehearsal databases with unique rows: review, 12 November 2026](operations/rehearsal-database-review-2026-11-12.md)
- [Football-Data.co.uk manifest path digests, 12 November 2026](operations/fduk-manifest-path-digests-2026-11-12.md): 47 legacy snapshots, [evidence](evidence/fduk-manifest-path-digests-2026-11-12.json), proposed raw-file bindings and guard
- Storage operating rollout, 12 November 2026: [owner decision](evidence/owner-decision-authorize-storage-operating-rollout-2026-11-12.json), [evidence](evidence/storage-operating-rollout-2026-11-12.json); candidate database deletion: [owner decision](evidence/owner-decision-approve-storage-candidate-deletion-2026-11-12.json), [evidence](evidence/storage-candidate-deletion-2026-11-12.json); recovery-scope migration `202611120200` ratified as applied: [owner decision](evidence/owner-decision-ratify-recovery-scope-migration-2026-11-12.json); 161 recovery-scope dispositions applied: [owner decision](evidence/owner-decision-apply-recovery-scope-dispositions-2026-11-12.json), [evidence](evidence/recovery-disposition-application-2026-11-12.json); recoverable backup after dispositions: [owner decision](evidence/owner-decision-authorize-recoverable-cli-backup-2026-11-12.json), [evidence](evidence/recoverable-backup-verification-2026-11-12.json); governed recovery activation and `VERIFIED_GOVERNED_SCOPE` backup: [owner decision](evidence/owner-decision-authorize-governed-scope-activation-2026-11-12.json), [evidence](evidence/governed-backup-verification-2026-11-12.json); source manifest binding migration `202611120300` applied: [owner decision](evidence/owner-decision-apply-source-manifest-binding-migration-2026-11-12.json); 47 Football-Data.co.uk raw-file bindings applied: [owner decision](evidence/owner-decision-apply-fduk-raw-file-bindings-2026-11-12.json); path-digest guard migration `202611120400` applied: [owner decision](evidence/owner-decision-apply-path-digest-guard-migration-2026-11-12.json)
- Recovery-scope disposition rehearsal on a restored copy, 12 November 2026 (not an owner decision): [evidence](evidence/recovery-disposition-rehearsal-2026-11-12.json)
- Football-Data.co.uk raw-file binding and path-digest guard rehearsal on a restored copy, 12 November 2026 (not an owner decision): [evidence](evidence/fduk-binding-rehearsal-2026-11-12.json)

- [Pre-P03 acquisition audit](evidence/pre-p03-acquisition-audit-2026-11-13.md), [recovery verification](evidence/pre-p03-recovery-verification-2026-11-14.md), [PR #230 integration](evidence/pre-p03-pr230-integration-2026-11-14.md), [operating rollout](evidence/pre-p03-operating-rollout-2026-11-14.json), [recovery batches and identity](evidence/pre-p03-recovery-batches-and-identity-2026-11-14.json), [identity remediation](evidence/pre-p03-identity-remediation-2026-11-14.json) and [result recovery handoff](architecture/unified-redesign-2026-11-10/PRE_P03_PROVIDER_AND_RESULT_RECOVERY_HANDOFF.md)

## Engineering standards

- [Backend](backend-engineering.md) and [frontend](frontend-engineering.md) standards, [testing](testing.md), [test fixtures](test-fixtures.md), [CI](ci.md)
- [Governed commit invariants](engineering/governed-commit-invariants.md), [foundation hardening](foundation-hardening.md)
- [Git delivery](git-delivery.md), [PR template](pr-template.md), [review checklist](review-checklist.md), [writing style](writing-style.md), [model routing](engineering/model-routing.md), [optional code intelligence](engineering/code-intelligence.md)
- [ADRs](adr/0001-python-managed-runtime-pin.md): [0002](adr/0002-go-127-golangci-analysis-scope.md), [0003](adr/0003-use-commit-pinned-source-acquisition.md), [0004](adr/0004-project-status-v2-owner-decisions.md), [0005](adr/0005-unified-architecture-evolution.md)

## Current status and retained reports

See [current state](status/current-state.md) for MVP, identity resolution and V4
status. Three dated reports still support open findings or direct historical
references: [codebase remediation](CODEBASE_REMEDIATION_REPORT.md),
[V4 implementation](V4_IMPLEMENTATION_REPORT.md) and
[V4 Issue 2 qualification](V4_ISSUE_02_QUALIFICATION_REPORT.md).
The [retirement decision](evidence/owner-decision-retire-dated-reports-2026-11-13.json)
identifies the Git revisions for the removed reports.

## Source archives

- [Research bibliography](references/research-basis.md)
- [Exact supplied PLAN archive](references/supplied-plan-2026-09-21.md), [exact Astra feedback archive](references/astra-feedback-2026-09-21.md)

Sections of the original plan that were once copied into separate files (module boundaries, data programme, feature research, calibration, promotion gates, mandatory Rust validation, test matrix, operational controls, definitions of done, feasibility, exclusions, phase list and backlog) were retired on 13 November 2026. They were word-for-word copies of the archive above and authorized nothing. Read the archive section when you need that design history.

## Documentation lifecycle

Keep the documentation small and current. Every rule here is checked by `make docs-check` where a machine can check it; the rest is a PR review item in the [PR template](pr-template.md#documentation).

1. **Plan.** Update the canonical document for the area (this index names it). Put scratch notes, agent output and generated reports in `.local/tmp/` (git-ignored). The [storage runbook](operations/storage-lifecycle.md#build-outputs-caches-and-temporary-directories) records the safeguards required before enabling five-hour cleanup for that directory. Do not add root Markdown files, dated progress notes or a second copy of a plan.
2. **Build.** Record progress in the PR description, not in new files. Edit the existing plan in place.
3. **Verify and roll out.** Keep validation, rollback and recovery evidence that an owner decision or `project-status.json` needs, as new files under `docs/evidence/`. Do not retire documents for work that is still rolling out.
4. **Finish.** In the PR that completes a feature: confirm it is merged, tested and (where applicable) deployed; move the lasting facts (what, why, where in the code, configuration, limits, PR links) into the canonical document as a short section; delete the feature's plans, checklists and reports; fix every link; and list the retired files in the PR description.
5. **Maintain.** When a finished feature changes, edit its section and remove the superseded text in the same PR.

Keep immutable evidence, decision events, source archives, contracts, schemas, migrations and test fixtures. Before retiring a report referenced by project status or evidence, verify each dependency and record the owner decision. Point current guidance at the owning document. Preserve historical citations at a verified Git revision when the evidence already identifies that revision. Keep any path that an immutable record still needs to resolve directly.

**Ownership:** Each specialized contract owns field-level rules; root plan owns intent, sequence and release gates; registered evidence/events govern whether a capability is actually authorized/active.
