# Future Api Illustration

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**NOT a current API.** The original payload below is design history only. It mixes internal diagnostic/context fields with public output and is **superseded as the public normative contract** by [proposed OpenAPI](openapi.yaml) and [compatibility rules](compatibility-policy.md). Display tags may be public but risk internals/provenance are access-controlled; `RUST_VALIDATED` is only legal with linked `PASS`.

---

## 15. API contract additions

Illustrative **future** response fragment; fields below do not represent an implemented or already authorized public API, and optional/unpromoted capabilities must be omitted or explicitly marked unavailable:

```json
{
  "schema_version": "v1",
  "request_id": "...",
  "fixture_id": "...",
  "forecast_id": "...",
  "issued_at": "...",
  "knowledge_cutoff": "...",
  "forecast_horizon": "24h",
  "supersedes_forecast_id": null,
  "revision_reason_codes": [],
  "probabilities": {
    "home": 0.44,
    "draw": 0.29,
    "away": 0.27
  },
  "expected_goals": {
    "home": 1.42,
    "away": 1.12
  },
  "context": {
    "h2h_effect_used": false,
    "h2h_effective_sample_size": 2.1,
    "h2h_simulation_variant": null,
    "matchup_intelligence_mode": "DISPLAY_ONLY",
    "lineup_mode": "PREDICTED",
    "lineup_attack_delta": -0.04,
    "lineup_defence_delta": 0.01,
    "travel_load_band": "NORMAL",
    "fixture_congestion_band": "ELEVATED",
    "game_state_adjustment_used": false
  },
  "display_tags": {
    "items": [
      {
        "code": "DERBY",
        "reason_codes": ["SAME_CITY"]
      },
      {
        "code": "UNPREDICTABLE",
        "reason_codes": ["HIGH_MODEL_DISAGREEMENT", "HISTORICALLY_VOLATILE"]
      }
    ],
    "forecast_effect": false,
    "tag_policy_version": "..."
  },
  "forecast_diagnostics": {
    "band": "ELEVATED",
    "reason_codes": ["MODEL_DISAGREEMENT"],
    "predictive_entropy": 0.97,
    "data_quality": "PASS",
    "forecast_effect": false
  },
  "simulation": {
    "mode": "RUST_VALIDATED",
    "validation_artifact_id": "...",
    "validation_status": "PASS",
    "simulation_count": 10000,
    "simulation_engine_version": "..."
  },
  "provenance": {
    "model_id": "...",
    "dataset_snapshot_id": "...",
    "feature_set_id": "...",
    "calibration_id": "...",
    "code_revision": "...",
    "simulation_engine_version": "...",
    "rivalry_registry_version": "...",
    "matchup_intelligence_version": "...",
    "travel_load_version": "...",
    "lineup_impact_version": "...",
    "display_tag_policy_version": "...",
    "risk_model_id": "..."
  }
}
```

Rules:

- `schema_version` follows the published compatibility and deprecation policy;
- `request_id` correlates API logs, traces, worker activity, and support incidents;
- derby and unpredictability categories appear only under `display_tags`;
- every display-tag payload must include `forecast_effect: false`;
- `h2h_effect_used` must show whether the promoted model actually used the signal;
- insufficient H2H history must return low effective sample size, not a fabricated neutral history;
- diagnostic and tag reasons are additive and auditable;
- forecast horizon, issue time, and superseded forecast must be explicit;
- revisions create a new immutable response artifact and carry reason codes for the newly available information;
- no tag may be copied into forecast `context`, a feature snapshot, simulator parameters, calibration inputs, or probability post-processing;
- a simulation-backed response is available only after a linked Rust validation artifact passes; the shown simulation fields are an **illustrative future contract**, not current API capability or authorization;
- `simulation.mode = RUST_VALIDATED` requires `validation_status = PASS`, a valid artifact ID, engine build, and eligible sample count; never fabricate the block when simulation has not run;
- simulation failure/timeout returns an explicit unavailable result for required products. An approved analytic-only fallback uses `ANALYTIC_ONLY` and must not represent itself as validated simulation output;
- simulated frequencies cannot silently overwrite the sealed forecast distribution, and adding simulation evidence cannot alter its canonical probability hash;
- the same `forecast_id` must return identical probabilities whether tag enrichment succeeds, fails, or is disabled;
- no endpoint may present a point estimate without its surrounding distribution and provenance where the product contract requires them.
