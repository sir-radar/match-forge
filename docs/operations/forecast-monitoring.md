# Forecast Monitoring

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

Statistical/data monitoring is distinct from service SLOs. Set thresholds from frozen policy and registered alert rules, not invented values. The simulator health dashboard never serves as evidence of predictive calibration.

---

## 16. Model, data, and forecast monitoring

This section owns statistical and data-quality monitoring. Section 18.4 owns service-health telemetry and SLOs.

Monitor:

- input missingness and schema drift;
- feature distribution shift;
- score residuals and probability integral transform diagnostics;
- Brier, log loss, RPS, CRPS, calibration slope/intercept, and coverage;
- performance by competition and mandatory segments;
- display-tag prevalence, evidence sufficiency, and diagnostic monotonicity;
- rivalry and non-rivalry calibration as reporting segments only;
- tag-enrichment parity: probabilities and simulator inputs remain identical with enrichment enabled or disabled;
- H2H contribution and effective sample size;
- H2H counterfactual variant performance and distribution shift;
- forecast performance by horizon and revision stage;
- information value and calibration change from each revision reason;
- travel-load, rest, and congestion segments;
- lineup impact, uncertainty, and continuity segments;
- squad-transition, player-rating, and retained-minutes segments;
- goalkeeper post-shot residual coverage and shrinkage behaviour;
- pre-shot threat and territory feature coverage;
- raw versus game-state-adjusted feature behaviour;
- provider corrections and dependency impact;
- model disagreement;
- simulation validation PASS/FAIL/INCONCLUSIVE rates, seed reproducibility, reference parity errors, Monte Carlo intervals, tail stability, batch convergence, timeouts, and compute costs;
- independently, real-outcome calibration and proper scoring of simulation-derived forecasts only when such a variant has a distinct approved contract and evaluation policy.

Retraining policy:

```text
trusted completed-match publication
  -> dependency and correction checks
  -> eligible future training data
  -> scheduled candidate rebuild
  -> leakage-safe evaluation
  -> calibration review
  -> governed promotion decision
```

Drift detection opens a review or challenger route. It must not silently replace the champion, change feature weights, or recalibrate production forecasts.
