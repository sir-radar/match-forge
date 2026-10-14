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

## Product performance selection

This section describes the implemented product contract; the proposed research
monitoring list above remains subject to its existing gates.

The performance API declares `analytics_policy_version=pre-match-revisions-v2`
and `analytics_horizon`. The default `LATEST` selects one immutable MVP forecast
per verified fixture, issued strictly before kickoff. Fixed horizons (`7D`,
`3D`, `24H`, `6H`, `1H`, `15M`) select the latest eligible revision available at
or before the declared cutoff; the stored revision horizon label does not decide
eligibility. Ties use issue time followed by forecast UUID. Football and knowledge
cutoffs cannot exceed issue time or reach kickoff. Only verified regulation-time
finished results qualify; unresolved fixture duplicates and incompatible score
bases are excluded. Historical forecast rows are unchanged.

Each forecast's league baseline uses only selected fixtures whose result was
known by that forecast's knowledge cutoff. Until a dedicated historical outcome
availability record is established, `product_fixtures.updated_at` provides a
conservative availability bound only when it is after the fixture's kickoff.
Unknown availability contributes no prior result. Later fixture metadata updates
can delay this bound; the product metric is current operational monitoring,
not a replacement for governed historical evaluation. Same-kickoff peers cannot
enter one another's priors. Laplace counts, rating thresholds and the existing
log-loss floor remain unchanged.

Top-three and top-five metrics rank score categories. An aggregate such as `5+`
can match those category metrics but cannot count as an exact-score modal hit.
The API preserves existing metric field names and adds mandatory policy/horizon
metadata. Unknown bucket contracts fail rather than interpreting `5+` as five.

Default pagination bounds forecast loading to the returned competition page.
Rating and minimum-count filters require computing the filtered population;
those records load in one batch. Context form, head-to-head and rest history use
native UUID indexes and append-only decisions at their requested knowledge cutoff,
including admissions and revocations. Current eligibility never substitutes for
historical eligibility.
