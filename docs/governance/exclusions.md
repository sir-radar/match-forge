# Exclusions

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

Explicit non-authorization boundaries carried forward; any later exception needs a new owner decision, versioned scope and migration plan.

---

## 24. Explicit exclusions

This plan does not authorize:

- changing the frozen Sprint 2 corpus, result, or thresholds;
- accessing the frozen 280 targets for a new route;
- automatic model promotion;
- automatic production recalibration after an upset;
- raw bookmaker odds as baseline model features;
- unreviewed web claims as derby truth;
- derby, rivalry, unpredictability, volatility, risk-band, or other frontend display tags as model features, calibrator inputs, simulator parameters, forecast-revision triggers, or probability adjustments;
- widening, flattening, suppressing, or recalibrating a forecast because a display tag is present;
- post-match information in a pre-match forecast;
- opaque “AI confidence” scores;
- LLM-written probability adjustments;
- microservices, Kubernetes, a streaming feature store, or service mesh as prerequisites for the first production release without measured need;
- reliance on exactly-once message delivery instead of idempotent processing and reconciliation;
- separate feature implementations for training, historical replay, and production serving;
- data resale or provider-term violations;
- simulator expansion as a substitute for failed forecasting evidence;
- interpreting this roadmap as authorization to implement Rust simulation, rerun frozen evaluation, or promote/deploy a model;
- presenting simulation frequencies as inherently more calibrated than the final model distribution;
- replacing calibrated analytic forecast probabilities with Monte Carlo frequencies by default;
- requiring retrospective Rust runs or changes to immutable existing Sprint 2 evidence. Foreign ownership of Python model mathematics and calibration by the Rust engine is prohibited.
