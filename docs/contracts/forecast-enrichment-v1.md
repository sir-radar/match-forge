# ForecastEnrichmentV1 — optional display-only sidecar

**Status:** proposed replacement for duplicated legacy `ForecastRiskAssessmentV1` and `FixtureDisplayTagsV1` *persistence ownership*. Existing named contracts may remain read adapters until a versioned migration is authorized; do not overwrite deployed schemas. The logical `risk_assessment` and `display_tags` remain distinct nested views under **one post-forecast artifact**.

## Record shape

```text
schema_version, enrichment_id, forecast_id, fixture_id
computed_at, knowledge_cutoff, evidence_snapshot_ids
forecast_probability_hash, forecast_artifact_hash
tag_policy_version, risk_policy_version, risk_model_id (nullable)
risk_assessment: {risk_band, risk_components, reason_codes, evidence_status}
display_tags: [{code, reason_codes, evidence_status, effective_sample_size?}]
forecast_effect = false
status = COMPLETE | PARTIAL | UNAVAILABLE
(optional) enrichment_artifact_hash
```

Reason codes and eligibility/evidence coverage must be reproducible from versioned **cutoff-eligible** inputs. A new enrichment version is a new sidecar, never a forecast revision. Future enrichment cannot invent information that was unavailable at the forecast cutoff when presenting a pre-match tag as historically issued; a later descriptive update must declare its separate enrichment knowledge time and must not masquerade as prior availability.

## Tag vocabulary (source union, not new predictive features)

`DERBY`, `UNPREDICTABLE`, `HISTORICALLY_VOLATILE`, `HIGH_FORECAST_UNCERTAINTY`, `HIGH_MODEL_DISAGREEMENT`, `OUT_OF_DISTRIBUTION`, `DATA_INCOMPLETE`, `INSUFFICIENT_EVIDENCE`.

- `DERBY` **only** from reviewed, temporally valid rivalry registry; geographic proximity alone does not declare it; `DERBY` **never implies** `UNPREDICTABLE`.
- `UNPREDICTABLE` **only** with a previously frozen, validated diagnostic policy and component reasons. Until approved, expose component tags rather than a composite label. Do not promise match outcome certainty.
- `HISTORICALLY_VOLATILE` needs earlier out-of-sample residuals, shrinkage and minimum effective sample size. `INSUFFICIENT_EVIDENCE` is not normal confidence.
- Disagreement, entropy, drift, OOD and quality describe forecasts/evidence; they do not flatten, widen, recalibrate, suppress, revise or adjust probabilities.
- Post-match shock labels belong to a separate post-match artifact. No future match information in a historical pre-match tag.

## Strict dependency firewall

Enrichment cannot feed training matrices, feature snapshots, model/calibrator state, parameter generator, Rust inputs, probability post-processing, automatic revision triggers or model promotion features. Do not use `forecast_effect=false` as the sole proof: enforce module import/DB access boundaries, manifest column allowlists, and [automated parity](forecast-enrichment-parity-v1.md). `forecast_probability_hash` and `forecast_artifact_hash` must match immutable originals; simulation validation evidence remains untouched.

## Failure and public API

Enrichment is best-effort **after successful forecast publication**; timeout/outage results in no sidecar or an explicit unavailable field while the existing forecast remains retrievable and identical. API projects only approved tags and public reason codes; internal risk components, training provenance, private provider data and diagnostic internals are **not** automatically public. See [API compatibility](../api/compatibility-policy.md).
