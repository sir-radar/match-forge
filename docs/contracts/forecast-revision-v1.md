# Forecast Revision V1

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Source-derived proposed field contract.** Require separate owner approval, point-in-time eligibility and implementation/schema review before production use. A revision is a new forecast; the publication and Rust validation gates apply prospectively once enabled, and historical revisions remain immutable.

---

### 6.11 `ForecastRevisionV1`

```text
forecast_id
fixture_id
issued_at
knowledge_cutoff
forecast_horizon
supersedes_forecast_id
model_feature_and_calibration_ids
probability_distributions
revision_reason_codes
new_information_ids
distribution_change_metrics
version
```

Supported research horizons may include `7d`, `3d`, `24h`, `6h`, `1h`, `15m`, and `CONFIRMED_LINEUP`, but only where historical availability can be reconstructed. A revision creates a new artifact and never overwrites an earlier forecast.
