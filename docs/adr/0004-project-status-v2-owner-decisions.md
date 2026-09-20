# ADR 0004: ProjectStatusV2 records owner decisions, closed routes, and research authorization

- Status: Accepted
- Date: 2026-09-20

## Context

`ProjectStatusV1` could not express a Phase 3 research authorization
independently from Sprint 2 failure: with Sprint 2 `FAIL` the validator forced
`phase_3.authorized=false` and `status=BLOCKED`, so the owner decision
`RETAIN_SPRINT2_FAIL_CLOSE_SHARED_PACE_AND_AUTHORIZE_PHASE3_RESEARCH_V1` (retain
the failure, close the shared-pace route, authorize bounded Phase 3A research
only) was inexpressible without hacking around validation. Status also drifted
from newer terminal evidence (PR #100 admission failure) because no check
reconciled evidence-side owner/terminal events against the tracked status.

## Decision

Bump the status contract to `ProjectStatusV2` and keep `docs/project-status.json`
the tracked current-status authority. V2 adds three fields, validated by
`football.project_status`:

- `owner_decisions`: every `docs/evidence/owner-decision-*.json` record must be
  listed here by `decision_id`, and every listed id must have such a record.
  This is the evidence-aware consistency check: a newer owner-decision evidence
  file that the tracked status does not reconcile fails `make
  project-status-check`.
- `closed_routes`: route, outcome (`TERMINAL_ROUTE_FAIL` or `CLOSED`), and an
  evidence reference that must mention the route.
- `phase_3.research`: research-only authorization bound to a reconciled owner
  decision id and a decision reference document that names it. Sprint 2
  failure still forces `phase_3.authorized=false`, `status=BLOCKED`, and
  `blocked_by` including `sprint_2`; research authorization never implies phase
  authorization or promotion.

Sprint 2, its frozen corpus, gate policy, thresholds, and all historical
evidence are unchanged. `RETAIN_FAIL_AND_STOP`, `challenger_authorized=false`,
and `model_promoted=false` are preserved.

## Consequences

- Research authorization is visible in status without implying promotion or
  phase completion.
- Status cannot silently lag a recorded owner decision; reconciliation is
  enforced in CI through `make project-status-check`.
- Future owner decisions add one append-only evidence JSON and one
  `owner_decisions` entry.
- ProjectStatusV1 files are rejected; consumers must read the V2 shape.
