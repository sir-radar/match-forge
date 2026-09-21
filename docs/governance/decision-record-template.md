# Decision record template

> Template only: copying this document does **not** create or approve a decision. Store signed/authorized events at a verified existing repository location; do not overwrite or renumber existing events.

```yaml
decision_id: TBD_UNIQUE_ID
title: TBD
status: PROPOSED # APPROVED | REJECTED | SUPERSEDED
created_at: TBD_UTC
decided_at: null
owner: TBD_VERIFIED_ID
approvers: []
related_phase: TBD
related_experiment_ids: []
related_artifact_ids: []
supersedes_decision_id: null
scope: TBD
```

## Decision and reason

State proposal, evidence and alternatives, chosen option and why; explain unknowns and contrary evidence. Distinguish a narrow **research** authorization from evaluation authorization, engine implementation, predictive promotion and production enablement.

## Explicit non-decisions

List forbidden adjacent activities and historic records unaffected (in particular Sprint 2 `FAIL`, its 280 target firewall and older artifacts). Define expiry/competition/forecast-horizon/data-tier boundaries.

## Invariants, impact and dependencies

Record point-in-time restrictions; artifact/contract/feature/API versions; code module owner; simulator/calibration separation; hash parity; security/licensing implications; resource/cost caps; prerequisite decisions and downstream gated events.

## Evidence and verification

Repo revision, approved policy and corpus hashes, experiment IDs, test reports, paired metrics where applicable, sign-off evidence, and CI/replay command output. Unknown evidence must remain `TBD`, not assumed passed.

## Rollback and follow-up

Describe disablement/suspension and version rollback without deleting immutable forecasts or rewriting decisions. Use additive superseding events when changing scope. Action table: `action | owner | due | verification artifact`.
