# PitchAPI domain-stratified evaluation V2 metrics

Status: `FROZEN — EXECUTION NOT AUTHORIZED`

Protocol: `PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2`

Policy SHA-256:
`e4dfbf6a5133fba4806de80e6a79ccc878670531bb695e5509776dca082c1da1`

This document fixes the calculation details for the metrics already named in
the approved policy. It adds no evaluation target, feature, model or acceptance
threshold.

## Common rules

For every target, the reference and challenger must supply one finite,
non-negative joint home/away score distribution whose probability sum differs
from one by no more than `1e-12`. All derived markets use that same
distribution. Invalid distributions fail the protocol; they are not clipped or
renormalized.

`delta = challenger metric - compatible reference metric`. Lower loss and
error values are better, so a negative delta favours the challenger. Metrics
are first averaged over targets within each domain. The primary macro result is
the arithmetic mean of the three domain deltas. The approved weighted result
is `(216*BL22_23 + 216*BL23_24 + 280*L1_22_23) / 712`. Calibration
coefficients are never averaged. Raw source distributions are never pooled.

A missing forecast, outcome, required probability or required Rust result is
not dropped. It is a protocol failure unless an exclusion was recorded before
outcomes were opened under an already frozen source-admission rule. A metric
that is explicitly descriptive and mathematically undefined is reported as
`NOT_CALCULABLE` with its reason and counts.

Required paired uncertainty uses the frozen moving-block bootstrap over
chronological kickoff batches: block length 10, 2,000 replicates, seed
`20260924`, percentile 95% interval. Domains are resampled independently;
aggregate replicate `i` combines replicate `i` from each domain. The single
confirmatory primary has no multiplicity adjustment. Domain guardrails are
conjunctive safety checks.

## Confirmatory and guardrail metrics

Let `Y=(h,a)` be the observed score, `p(h,a)` the forecast joint probability,
and `1(condition)` the indicator function.

### Joint-score log loss

Per target: `-ln p(Y)`, in natural-log nats. The compact reporting grid uses
labels `0,1,2,3,4,5+`; an observed goal count of at least five maps to `5+`.
The primary is the challenger-minus-reference domain mean and its macro mean.
Lower is better. A zero probability for the observed bucket fails as an invalid
forecast rather than being floored.

### 1X2 log loss

Sum the joint distribution into ordered classes `away win, draw, home win`.
Per target: `-ln p_c`, where `c` is the observed class. Lower is better.

### 1X2 multiclass Brier score

Per target: `sum_c (p_c - 1(Y=c))^2` over the three ordered 1X2 classes. The
score is not divided by three. Lower is better.

### 1X2 ranked probability score

Using class order `away win, draw, home win`, per target:
`RPS = (1/2) * sum_{k=1}^{2} (F_k - O_k)^2`, where `F_k` is the forecast
cumulative probability through class `k` and `O_k=1(Y is in a class <=k)`.
Lower is better.

### Total-goal CRPS

Let `T=h+a`, forecast CDF `F_T(k)`, and observed total `t`. Per target:
`CRPS = sum_{k=0}^{infinity} (F_T(k) - 1(t<=k))^2`. The implementation must
extend exact non-negative score support until the unresolved joint tail is at
most `1e-12`; it must report the cutoff and an upper bound for the omitted CRPS
contribution. An upper bound above `1e-12` fails. Lower is better.

### Calibration intercept and slope

For each domain and each one-versus-rest 1X2 class, fit the unpenalized logistic
model `logit Pr(Y=c) = alpha_c + beta_c*logit(p_c)`. Forecast probabilities
equal to zero or one are invalid before fitting. Report `alpha_c`, `beta_c`,
standard errors and convergence. Perfect separation, singularity or
non-convergence is `NOT_CALCULABLE` and fails the required calibration gate.
Calibration is ideal at intercept zero and slope one. Worsening is
`|alpha_challenger|-|alpha_reference|` and
`|beta_challenger-1|-|beta_reference-1|`; every class in every domain must
satisfy the frozen domain limits.

### Reliability diagram

For each 1X2 one-versus-rest class and domain, use fixed left-closed bins
`[0.0,0.1),...,[0.8,0.9),[0.9,1.0]`. Report target count, mean forecast and
observed rate per non-empty bin. Empty bins remain present with null means.
This is descriptive and has no separate acceptance threshold.

### Prediction interval coverage and width

For total goals, report central equal-tailed integer intervals at nominal 50%
and 90%. The lower endpoint is the smallest integer with CDF at least
`(1-level)/2`; the upper endpoint is the smallest integer with CDF at least
`1-(1-level)/2`. Report empirical coverage and mean inclusive width
`upper-lower+1` by domain. These are descriptive; no unregistered gate is
created.

## Descriptive metrics

- Binary market log loss and Brier use the usual Bernoulli formulas
  `-[y ln p +(1-y)ln(1-p)]` and `(p-y)^2`; lower is better.
- Binary AUC is the Mann-Whitney rank statistic with average ranks for ties;
  higher is better. A single-class slice is `NOT_CALCULABLE`.
- Exact-score top-k accuracy is the fraction whose observed compact score
  bucket is among the `k` largest probabilities, for `k=1,3,5`. Ties at the
  boundary are ordered by lower home goals, then lower away goals. Higher is
  better.
- Expected-total-goal MAE is `|E[T]-t|`; lower is better.
- Sharpness reports mean width of the frozen 50% and 90% total-goal intervals
  only alongside their coverage. Narrower is not called better unless coverage
  is adequate; this metric has no acceptance threshold.

Descriptive binary markets are BTTS and over/under totals at 0.5, 1.5, 2.5,
3.5 and 4.5 goals. Adding another post-outcome metric requires an explicitly
labelled exploratory report or a new protocol version; it cannot affect V2's
disposition.

## Heterogeneity reporting

For every required loss or score, report the three domain estimates, paired
95% intervals and deltas, the frozen macro and weighted aggregates, and the
range `maximum domain delta - minimum domain delta`. Also report the frozen xG
moments/quantiles, calibration fits, shot-situation and penalty summaries, and
overall and situation-conditioned two-sample KS statistic
`sup_x |F_domain1(x)-F_domain2(x)|`. Heterogeneity is descriptive unless it
reveals a schema or source-semantic failure.
