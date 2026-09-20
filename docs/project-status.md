# MatchForge current project status

[`project-status.json`](project-status.json) is the tracked current project
status. Run `make project-status-check` to verify it.

Immutable evidence records gate and evaluation facts. `project-status.json`
references that evidence and records the current execution state. Local
`PLAN.md` remains an ignored roadmap mirror and is not repository evidence.

## ProjectStatusV2 additions

- `owner_decisions` must reconcile every `docs/evidence/owner-decision-*.json`
  record: validation fails when a recorded owner decision is missing from the
  tracked status, or when a listed decision has no record.
- `closed_routes` records terminally closed routes with their outcome and
  evidence; the referenced evidence must mention the route.
- `phase_3.research` expresses research-only authorization independently from
  phase authorization and model promotion; with Sprint 2 `FAIL`, phase 3 stays
  `BLOCKED`/unauthorized while bounded research may be authorized by a
  reconciled owner decision.
