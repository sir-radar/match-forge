# Calibration Policy

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Clarification:** forecast-risk bands and components belong to optional `ForecastEnrichmentV1`, NOT the immutable probability outputs. The corresponding legacy bullet has been moved out of this extracted minimum-output checklist. Calibration uses only out-of-sample real outcomes and preserves joint-distribution coherence. See [forecast contract](../contracts/forecast-artifact-v1.md).

---

## 10. Probability and calibration requirements

Every forecast must provide coherent probabilities for approved products.

Minimum outputs:

```text
home/draw/away
home and away goal distributions
exact-score matrix with explicit tail
total-goal distribution
over/under approved lines
BTTS
clean sheets
goal range probabilities
expected goals for each team
prediction intervals or credible intervals
forecast-risk components and band
```

Calibration policy:

- fit calibration only on predictions generated without seeing their outcomes;
- compare uncalibrated, sigmoid/temperature-style, and isotonic candidates where sample size permits;
- assess overall and segment calibration;
- reject calibrators that improve one metric while materially degrading proper scores or sharpness;
- version calibrators by model, competition scope, target, and time period;
- ensure the final joint distribution is coherent before Rust sampling: if a proposed 1X2-only calibrator breaks coherence with exact scores, totals, or BTTS, reject it or use a separately evaluated distribution-coherent reconciliation; do not let Rust silently reconcile inconsistent market probabilities;
- never fit or refit calibration to repeated draws generated from the model itself; synthetic replicates share the same model assumptions and are not independent football outcomes;
- never recalibrate from a single match;
- trigger review, not automatic promotion, when drift thresholds are crossed.
