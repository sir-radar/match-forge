# Minimal Rust simulator authorization proposal

**Status: PROPOSED / NOT APPROVED.** The 20 September Phase 3A decision does not authorize this. This file is an input for the owner, not permission to code, run protected evaluation, enable production or change earlier artifacts.

## Requested scope (stage A only)

Reconcile existing `rust/simulation-core` and Python/Go interfaces. Define a versioned, coherent calibrated forecast/parameter input, minimal deterministic seeded score sampler (no independent team-strength fitting), reference fixtures, analytic parity/convergence/tail tests, reproducible input and output hashes, bounded workers/cancellation, validation sidecar and state-machine integration **in non-production/test environments**. Select numerical tolerances, event support and compute/latency limits in an independently frozen policy *before* tests.

## Explicitly not requested

No Sprint 2 target access/rerun, no broader Phase 3 research, no authoritative Evaluation V2 run, no model/calibrator changes, no automatic probability repair, no advanced cards/substitutions/lineup/corners/H2H scenarios, no public API rollout, no production enablement and no analytic-only exception. Predictive promotion remains a different decision based on real outcomes.

## Acceptance evidence required for a later stage B decision

Versioned parameter schema and engine build; cross-language golden hashes; independent-seed fixture parity and event-specific half-widths; tail/coherence; repeated run determinism; idempotency and fault injection; sample/latency/memory/cost budget; `PASS`/`FAIL`/`INCONCLUSIVE` contract tests; code reviews, security/licensing, and existing integration compatibility. Approval for production activation is a **later, separate decision**.

## Approval placeholders

`owner: TBD; decision_id: TBD; signed_at: TBD; approved_scope: TBD; policy_hash: TBD`. Until filled by the actual owner event, do not mark this proposal approved.
