# Forecast Revision V1

> **Document status:** implemented for MVP champion forecasts by migration
> `202610070200_live_context_revisions.sql`. This contract does not enable predictive context weights.

---

### 6.11 `ForecastRevisionV1`

```text
forecast_id
fixture_id
issued_at
football_cutoff
knowledge_cutoff
forecast_horizon
supersedes_forecast_id
model_id
artifact_sha256
predictive_input_snapshot_sha256
context_snapshot_sha256
revision_reason_codes
new_information_ids
probability payload
payload_sha256
```

Supported horizons are `EARLY_GT_7D`, `7D`, `3D`, `24H`, `6H`, `1H`, `15M`, and
`CONFIRMED_LINEUP`. The confirmed-lineup horizon applies only when the active model consumes that
lineup. The current champion does not.

A revision creates a new forecast and never overwrites an earlier forecast. Semantic identity uses
the model artifact and predictive input hash. Time passing, an unchanged provider response, or a
context-only update does not create a forecast revision.
