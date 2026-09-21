# MatchForge documentation index

**Root [PLAN.md](../PLAN.md) is the compact proposed execution/control-plane roadmap.** Supporting docs preserve the original technical research and separate immutable forecasts, mandatory Rust evidence, optional enrichment, evaluation authority and public delivery. Repository evidence and owner decisions remain higher authority. See [status](status/current-state.md) and [adoption checklist](reconciliation/adoption-checklist.md).

## Architecture / data

- [Artifact and publication boundaries](architecture/artifact-boundaries.md)
- [Module layout and source-of-truth ownership](architecture/module-boundaries.md)
- [Explicit owner and dependency register](governance/ownership-and-dependencies.md)
- [Provider qualification and data programme](data/data-programme.md)

## Contracts

- [Immutable forecast](contracts/forecast-artifact-v1.md), [canonical hashes](contracts/canonical-hashing-v1.md), [Rust evidence](contracts/simulation-validation-v1.md)
- [Optional enrichment](contracts/forecast-enrichment-v1.md), [parity checks](contracts/forecast-enrichment-parity-v1.md)
- [Source-derived feature contracts](contracts/) — rivalry, expected performance, H2H, cutoff availability, matchup, travel/load, lineup, revision, squad transition, goalkeeper and pre-shot threat; inspect individual files in the directory.

## Evaluation and experimentation

- [Evaluation V2 freeze/metrics and authorization](evaluation/evaluation-v2-policy.md)
- [Promotion gates](evaluation/promotion-gates.md)
- [Research programme and model ladder](models/feature-research.md), [calibration](models/calibration-policy.md)
- [Phase 3A minimal xG draft pre-registration](governance/phase3a-minimal-xg-preregistration.md)
- [Portfolio dependency table](governance/feature-portfolio.md), [feasibility notes](governance/feasibility-matrix.md), [experiment ledger template](governance/experiment-register.md)
- [Decision record template](governance/decision-record-template.md), [decision events directory](governance/decision-events/README.md), [minimal Rust authorization proposal](governance/simulation-authorization-proposal.md)

## Simulation, delivery and operations

- [Mandatory validation policy](simulation/mandatory-validation.md), [publication state machine](simulation/publication-state-machine.md), [failure runbook](operations/runbooks/simulation-failure.md)
- [Proposed public OpenAPI](api/openapi.yaml), [compatibility/privacy](api/compatibility-policy.md), [superseded original API illustration](api/future-api-illustration.md)
- [Capabilities and enablement](operations/capability-registry.md), [rollback](operations/rollback-policy.md), [monitoring](operations/forecast-monitoring.md)
- [Full phase deliverables](roadmap/implementation-phases.md), [immediate backlog](roadmap/immediate-backlog.md), [test matrix](engineering/test-matrix.md), [engineering controls](engineering/operational-controls.md), [five definitions of done](engineering/definitions-of-done.md)

## Auditing and source preservation

- [How to integrate without losing prior progress](reconciliation/adoption-checklist.md); [change log / Astra mapping](reconciliation/change-log.md)
- [Explicit exclusions](governance/exclusions.md), [research bibliography](references/research-basis.md)
- [Exact supplied PLAN archive](references/supplied-plan-2026-09-21.md), [exact Astra feedback archive](references/astra-feedback-2026-09-21.md)

**Ownership:** Each specialized contract owns field-level rules; root plan owns intent, sequence and release gates; registered evidence/events govern whether a capability is actually authorized/active. Legacy source extracts are design reference and must not override a newer approved contract.
