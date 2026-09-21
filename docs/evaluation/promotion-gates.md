# Promotion Gates

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

A research decision, Rust numerical `PASS`, model promotion and production enablement are **separate** events. Actual pass/fail is unknown absent repository evidence. The threshold values and cost/SLO limits must be frozen prior to the authoritative run. The simulation gate applies only to simulation-capable candidates once separately authorized and accepted.

---

## 13. Promotion gates

A candidate is eligible for promotion consideration only if all applicable gates pass:

### Integrity

- point-in-time feature audit passes;
- dataset manifest and checksums reproduce;
- no target leakage or same-kickoff leakage;
- complete lineage and immutable artifacts;
- missingness and fallback behaviour match the frozen policy;
- derby and unpredictability tags are absent from feature manifests, calibrator inputs, parameter generation, simulator inputs, and probability post-processing;
- forecast-with-tags and forecast-without-tags probability artifacts are identical.

### Predictive performance

- no material regression on primary proper scores;
- improvement exceeds the pre-registered practical threshold or provides a separately approved operational benefit;
- confidence interval satisfies the frozen decision rule;
- gains are not concentrated in one competition or fold;
- calibration is maintained or improved.

### Segment safety

- derby and high-uncertainty segments are explicitly reviewed as evaluation slices only;
- incomplete-data fallbacks do not produce unjustified confidence;
- newly promoted and low-history teams remain calibrated enough for the approved use;
- non-H2H fixtures are not degraded by the H2H candidate.

### Operations

- latency and resource budgets pass;
- model, calibrator, and feature versions are deployable and reversible;
- contract compatibility and database migration dry runs pass;
- training-serving parity and deterministic replay pass;
- dashboards, actionable alerts, runbooks, and on-call ownership exist;
- backup restoration meets the approved RPO and RTO;
- build provenance, dependency policy, and security scans pass;
- cost per forecast, simulation, and scheduled rebuild remains within budget;
- shadow run and rollback evidence exists;
- Rust simulation reference-fixture parity, independent-batch convergence, tail checks, validation-artifact integrity, and cost gates pass for any simulation-capable candidate (once separately authorized);
- owner records a separate promotion decision.

Passing research, numerical simulation validation, or evaluation does not automatically promote a model. A real-outcome evaluation is still required before predictive promotion.
