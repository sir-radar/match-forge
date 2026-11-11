# Current state

**Verified against:** `docs/project-status.json` (`updated_at` 2026-11-10), immutable research evidence, and the owner decisions it lists. If this summary and the machine-readable status disagree, `project-status.json` and the append-only evidence win; fix this file.

MVP implementation is complete and live settlement evidence is still pending. MatchForge publishes the retained rolling-goals Poisson reference as `MVP_FORECAST`. Model research is paused for the MVP (`MODEL_RESEARCH_PAUSED_FOR_MVP`) and the champion has not changed. No capability, model promotion, Rust simulation gate or Architecture V2 cutover is enabled by any roadmap, proposal or research decision.

## Research and gate state

| Subject | Verified value | Required treatment |
| --- | --- | --- |
| Phase 1B | `PASS` | Preserve the referenced gate evidence. |
| Phase 2B | `PASS` | Preserve the referenced gate evidence. |
| Sprint 2 baseline | Immutable `FAIL` / `RETAIN_FAIL_AND_STOP` | Do not relabel, rerun under changed thresholds, or overwrite. |
| Sprint 2 evaluation targets | Frozen 280 | New routes must not access them. |
| `DCV3_SHARED_MATCH_PACE_MIXTURE_V1` | `TERMINAL_ROUTE_FAIL` at `60/10`, lower `kappa = 0` boundary | Closed. No continuation or promotion. |
| Phase 3 | Overall `BLOCKED`; one narrow Phase 3A research exception | Research permission is not a phase pass or production permission. |
| PitchAPI V1 | `TERMINAL_FAIL_NO_EXECUTION` | Preserve the historical failure. |
| PitchAPI V2 | `BLOCKED_PRE_EXECUTION_MODEL_NON_TRANSFERABILITY` | Preserve without execution. |
| PitchAPI V3 | `TERMINAL_FAIL_RUST_PARITY` | Permanently closed. |
| PitchAPI V4 | `TERMINAL_PROTOCOL_EVALUATION_FAILURE` (calibration boundary) | Permanently closed; never rerun. |
| PitchAPI V5 | `COMPLETE` / `REFERENCE_RETAINED` | Valid evaluation. The challenger scored better but failed 14 frozen calibration gates. |
| V5 challenger | `EVALUATED_REJECTED_CALIBRATION`; route `PITCHAPI_TRANSFERABLE_NPXG_CHALLENGER_V1` `CLOSED` | No promotion, recalibration on V5, refit, or retry. |
| V5 targets | `SPENT_FOR_MODEL_SELECTION` | Reproduction and post-hoc description only; never fresh confirmation evidence. |
| `TRANSFERABLE_ROLLING_NPXG_FOR_AGAINST_DIXON_COLES_V2` | `CLOSED` (`DEVELOPMENT_REJECTED_PERMANENTLY_CLOSED`) | No continuation. |
| H2H incremental signal, context feature evaluation, multimodel challengers | `COMPLETE_DEVELOPMENT_REJECTED`, `COMPLETE_DEVELOPMENT_REJECTED`, `COMPLETE_RETAIN_CHAMPION` | H2H stays display-only with zero model weight. |
| StatsBomb Evaluation V2 | `AWAITING_PROVIDER_RESPONSE`; independent and unchanged | Do not merge its result into PitchAPI V5. |
| Full-coverage V2 re-evaluation | `V1_1` and `V1_2` `FAIL_CLOSED_PROTOCOL_VIOLATION`; `V1_3` `PREEXECUTION_DATA_INTEGRITY_BLOCK` with no logical executions | Next action is an owner decision. Do not run V2A/V2B or relabel these results. |
| Production capability | No enablement is recorded in `docs/project-status.json` | Do not infer production enablement from a roadmap, proposal, or research decision. |

## Rust simulation

`rust_simulation_authorized` is `false` in the recorded status. The V3, V4 and V5 execution decisions authorized frozen, protocol-scoped Rust builds (112,460 simulations per forecast) as evaluation evidence only; V5 recorded Rust parity `PASS`. That is not the separate owner decision the minimal Rust simulator proposal asks for, and no new production forecast depends on simulation validation today. See [PLAN.md](../../PLAN.md#7-mandatory-rust-policy-conditional-on-authorization-and-acceptance).

## Architecture programmes

| Programme | Recorded state | Note |
| --- | --- | --- |
| Architecture V2 | `IN_PROGRESS`, current phase 37 | `R3_DEFERRED_ARCHITECTURE_MIGRATION`; no production cutover or legacy retirement recorded. |
| Identity resolution | `PASS_WITH_WARNINGS`, phase 10 | No production cutover or legacy retirement. |
| V4 programme | `BLOCKED_WITH_EVIDENCE`, phase 23 | Blocked phases 02, 07, 08, 10, 18, 19, 21; no model promotions. |
| Codebase remediation | `PASS_WITH_WARNINGS` | Operating rollout and external evidence limits remain open. |
| Unified architecture investigation | `PASS_WITH_WARNINGS`; planning only | [Redesign docs](../architecture/unified-redesign-2026-11-10/README.md) are recommendations. `implementation_of_proposed_architecture_authorized` is `false` in this status file until an implementation task records otherwise. |
| Unified architecture P02 (data integrity) | `NOT_RUN`; implementation `IN_PROGRESS` | Owner decision `AUTHORIZE_UNIFIED_P02_DATA_INTEGRITY_IMPLEMENTATION_V1` ([record](../evidence/owner-decision-authorize-p02-data-integrity-2026-11-11.json)) authorizes tickets P02-01 and P02-02 on `ft/p02-data-integrity`. No operating write, acquisition, identity admission or model promotion is authorized. Every other proposed phase stays unauthorized. |

## Current authorized work

1. Preserve the completed MVP while collecting pending live settlement evidence.
2. Keep H2H display-only with zero model weight.
3. Do not acquire research data under a research route that is closed, fit or evaluate an H2H candidate, execute confirmation, build V6, or start another forecasting experiment without a new owner decision.
4. Provider acquisition follows the standing decision in [source acquisition](../source-acquisition.md#project-use-policy), with provider terms and account limits recorded separately.
5. Treat the [post-redesign roadmap](../../MatchForge_Post_Redesign_Extensible_Football_Product_Implementation_Plan_v2_2026-11-09.md) and the unified redesign as follow-on planning under [PLAN.md](../../PLAN.md). Each needs its own task authorization.
