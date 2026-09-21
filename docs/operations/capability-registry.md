# Capability and promotion registry — proposed schema

**Critical:** the repository does not contain an authoritative runtime capability registry. The table below does **not** assert live capability states. Do not set `EVALUATION_READY`, `PRODUCTION_ENABLED`, `RETIRED`, or any other state from roadmap proposals. Require tracked owner decisions and runtime evidence before populating an authoritative registry.

## Allowed states

`NOT_STARTED`, `RESEARCH_ONLY`, `EVALUATION_READY`, `PROMOTION_CANDIDATE`, `SHADOW_ENABLED`, `PRODUCTION_ENABLED`, `SUSPENDED`, `RETIRED`. During documentation reconciliation use `UNVERIFIED — DO NOT ENABLE` **outside** the executable enum; do not seed the runtime with unknown enum values.

Required record: `capability_id`, name, owner, state, state-event ID/timestamp, model/feature/calibrator/policy IDs as applicable, data tier, approved competitions/horizons/products, evaluation/report/hash, promotion decision ID, engine acceptance and activation IDs if simulation-backed, deployment and rollback versions, enablement timestamp, suspension reason and signed evidence. Use append-only transitions and a derived current state.

## Initial documentation-only inventory

| Capability | Repository evidence or proposal | Runtime state to assign now |
| --- | --- | --- |
| Prior goals-only and dynamic reference implementations | Baseline work and retained evidence exist; runtime state is not recorded | **Do not assign; verify** |
| Single minimal Phase 3A xG hypothesis | Narrow **research-only** authorization recorded | No production inference |
| Wider xG/xGA, H2H, lineup, goalkeeper, threat, ensemble | Proposed research families | No production inference; verify |
| Derby/unpredictability display tags | Display-only proposal | No production inference; verify |
| Minimal Rust engine | Scaffold mentioned, separate authorization pending | **Not authorized for new implementation/activation by prior event** |
| New simulation-validated product | Mandatory *future* product policy | **Not activated by any tracked decision** |
| Automatic post-upset recalibration, derby probability coefficient, tag-induced probability adjustment | Explicitly excluded by the roadmap | Must not be enabled under this plan |

## State transition gates

1. Research → evaluation: scoped decision, frozen independent data, integrity tests and metrics; distinct authoritative-run decision where required.
2. Evaluation → candidate: real-match predictive evidence, reproducible scoring/calibration, segment/uncertainty and ops review. A Rust parity `PASS` does not prove this.
3. Candidate → shadow → production: signed release/promotion and enablement events, approved data/product scope, security/SLO/cost/rollback, and accepted Rust engine + per-forecast `PASS` route for mandatory simulation products.
4. Any state → `SUSPENDED`: leakage/parity failure, significant calibration degradation against registered rule, provider semantic change, missing rollback proof, security/licensing breach or validated simulation failure. Keep historical evidence immutable and record why.
5. Rollback changes future routing only. Never delete published forecasts or retroactively invent validation for old artifacts.
