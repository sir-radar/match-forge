# DCv3 static team heterogeneity multiplicity protocol — 2026-09-09

## Map

~~~
Static Team Heterogeneity Multiplicity Confirmation
~~~

This protocol is frozen before the joint-bootstrap output is generated. It uses only the corrected frozen La Liga forecast/residual artifact and does not refit DCv3 or a challenger.

## Bound input

~~~
Input: docs/evidence/dcv3-independent-laliga-diagnostic-corrected-2026-09-09.json
Required SHA-256: 120ca2e0e135942d7d0b0316d8035562e9d57426225fe3d49dedf4ada445ee5e
Targets: 280
Warm-up: first 100 chronological matches
Frozen model: sprint2-dixon-coles-v3, unchanged
~~~

The original artifact does not persist its batch index. The follow-up reconstructs a kickoff batch by grouping forecast records with the identical retained UTC kickoff string, then requires exactly 243 groups. This is the original plan's retained kickoff-batch count.

## Frozen bootstrap

~~~
Method: circular chronological moving-block bootstrap
Sampling unit: reconstructed kickoff batches
Block length: 10 kickoff batches
Replicates: 2,000
Seed: 20260909
Team eligibility: at least 12 original diagnostic appearances
Primary family: every eligible attack and defence series together
~~~

Each replicate samples consecutive circular kickoff-batch blocks until it contains exactly 243 sampled batches. All records in every selected batch are retained. This preserves same-match home/away coupling, team appearance coupling, chronological block structure, and shared frozen forecast/refit structure. Teams are never resampled separately.

For team \(t\), the statistics remain the frozen definitions:

\[
\bar r^A_t=\operatorname{mean}(g-\lambda)
\quad\text{when team }t\text{ scores},\qquad
\bar r^D_t=\operatorname{mean}(g-\lambda)
\quad\text{when team }t\text{ concedes}.
\]

The observed vector has all eligible attack means followed by all eligible defence means. Let \(\hat\theta_j\) be one observed mean and \(\hat\theta^*_{j,b}\) its bootstrap value. Its bootstrap standard error is the sample standard deviation of \(\hat\theta^*_{j,b}\).

The primary 40-series maximum statistic is:

\[
M_b=\max_j\left|\frac{\hat\theta^*_{j,b}-\hat\theta_j}{\widehat{se}_j}\right|.
\]

Its empirical 95th percentile \(q_{0.95}\) produces simultaneous 95% intervals \(\hat\theta_j\mathbin{\pm}q_{0.95}\widehat{se}_j\). A primary-family exclusion is an interval that does not contain zero.

The predeclared global statistic is:

\[
Q_{\rm obs}=\sum_j\left(\frac{\hat\theta_j}{\widehat{se}_j}\right)^2,
\qquad
Q_b^*=\sum_j\left(\frac{\hat\theta^*_{j,b}-\hat\theta_j}{\widehat{se}_j}\right)^2.
\]

The global reference probability is the empirical upper-tail fraction \(\Pr(Q_b^*\ge Q_{\rm obs})\). This is a non-parametric bootstrap reference, not an independent-Binomial calculation or a fitted heterogeneity model.

Attack-only and defence-only maximum-statistic intervals are secondary descriptive results. They do not override the primary 40-series result.

## Classification

- A. STATIC_HETEROGENEITY_CONFIRMED_AFTER_MULTIPLICITY requires global reference probability at most 0.05 and either more than one primary simultaneous exclusion or a global statistic exceeding its 95% bootstrap reference interval.
- B. STATIC_HETEROGENEITY_NOT_CONFIRMED_AFTER_MULTIPLICITY applies when the bootstrap is valid but those conditions fail.
- C. MULTIPLICITY_DIAGNOSTIC_INCONCLUSIVE applies only to a predeclared failure of bootstrap validity, including missing eligible series, non-finite/zero standard errors, malformed frozen input, or nondeterministic repetition.

No effect-size cutoff is added. Surviving mean residuals, simultaneous intervals, and appearances are reported descriptively only.
