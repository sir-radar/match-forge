# Current state

**Verified against:** `docs/project-status.json`, immutable research evidence, and owner decision `MVP_PRODUCT_DELIVERY_ACTIVE` on 29 September 2026. Machine-readable status and append-only evidence remain authoritative if this summary becomes stale.

MVP implementation is complete; live settlement evidence remains pending. MatchForge uses the retained rolling-goals Poisson reference as `MVP_FORECAST`. A fresh, outcome-blind 1,572-target corpus now satisfies the full-coverage V2 re-evaluation floors, but V2A/V2B have not been run. This does not authorize V6, H2H fitting, confirmation, calibration work, or another experiment.

| Subject | Verified value | Required treatment |
| --- | --- | --- |
| Phase 1B | `PASS` | Preserve the referenced gate evidence. |
| Phase 2B | `PASS` | Preserve the referenced gate evidence. |
| Sprint 2 baseline | Immutable `FAIL` / `RETAIN_FAIL_AND_STOP` | Do not relabel, rerun under changed thresholds, or overwrite. |
| Sprint 2 evaluation targets | Frozen 280 | New routes must not access them. |
| `DCV3_SHARED_MATCH_PACE_MIXTURE_V1` | `TERMINAL_ROUTE_FAIL` at `60/10`, lower `kappa = 0` boundary | Closed. No continuation or promotion. |
| Phase 3 | Overall `BLOCKED`; one narrow Phase 3A research exception | Research permission is not a phase pass or production permission. |
| PitchAPI V1 | `FAILED` | Preserve historical failure. |
| PitchAPI V2 | `BLOCKED_PRE_EXECUTION_MODEL_NON_TRANSFERABILITY` | Preserve without execution. |
| PitchAPI V3 | `PROTOCOL_EVALUATION_FAILURE_RUST_PARITY` | Permanently closed. |
| PitchAPI V4 | `PROTOCOL_EVALUATION_FAILURE_CALIBRATION_BOUNDARY` | Permanently closed; never rerun. |
| PitchAPI V5 | `COMPLETE` / `REFERENCE_RETAINED` | Valid evaluation. Challenger had better predictive scores but failed 14 frozen calibration gates. |
| V5 challenger | `EVALUATED_REJECTED_CALIBRATION` | No promotion, recalibration on V5, refit, or retry. |
| V5 targets | `SPENT_FOR_MODEL_SELECTION` | Reproduction and post-hoc description only; never fresh confirmation evidence. |
| Calibration research | `PITCHAPI_V5_CALIBRATION_POSTHOC_RESEARCH_V1` descriptive diagnosis complete | Successor research hypothesis exists but no model is admitted. Development-only implementation needs owner approval. |
| StatsBomb Evaluation V2 | Independent and unchanged | Do not merge its result into PitchAPI V5. |
| Full-coverage V2 clean re-evaluation | `READY_FOR_MATCHFORGE_FULL_COVERAGE_CHALLENGERS_V2_REEVALUATION_V1` | Use only the frozen 1,572-target corpus and preserved 2,198-ID firewall. Qualification did not run V2A/V2B or change the champion. |
| Production capability | No enablement is recorded in `docs/project-status.json` | Do not infer production enablement from a roadmap, proposal, or research decision. |

## Current authorized work

1. Preserve the completed MVP while collecting pending live settlement evidence.
2. Keep H2H display-only with zero model weight.
3. Do not acquire research data, fit/evaluate an H2H candidate, execute confirmation, build V6, or start another forecasting experiment.
4. Run the clean V2A/V2B re-evaluation only as a separate owner-directed task using `MATCHFORGE_FULL_COVERAGE_V2_FRESH_DEVELOPMENT_CORPUS_V1`.

The status and owner decision records agree. V5 is the first valid completed PitchAPI model comparison; its favorable predictive deltas do not override its frozen calibration rejection.
