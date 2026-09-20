# Static team heterogeneity challenger contract research — 2026-09-09

## Map

~~~
Static Team Heterogeneity Challenger Contract Research
~~~

Destination: determine the smallest scientifically justified extension to frozen DCv3 that tests the independent residual finding, freeze one challenger only if justified, and stop for owner review.

This route is research only. It does not change production code, the frozen DCv3 implementation, artifact code or schemas, ProjectStatusV1, Sprint 2, or Phase 3.

## Bound inputs and protected data

This research uses the corrected retained diagnostic record only:

~~~
Dataset: StatsBomb La Liga 2015/16
Dataset version: 670662d6-6ed7-5fa1-ba3c-1cfd561e524f
Source snapshot: 01a08471-f763-7787-80ca-4293316b7e44
Diagnostic targets: 280 after a 100-match warm-up
Diagnostic-target SHA-256: b758e795d41f0cc84145626d20d791eccbcfbd9fb94d2767039bdcdf50f3eb18
Corrected diagnostic SHA-256: 120ca2e0e135942d7d0b0316d8035562e9d57426225fe3d49dedf4ada445ee5e
Diagnostic conclusion: STATIC_HETEROGENEITY_SUPPORTED
Evidence strength entering research: MODERATE
~~~

No challenger was fitted, ranked, or tuned on La Liga. The frozen 280 EPL outcomes were not accessed. The terminal 100-match shared-pace admission population was not reused, shared-pace admission was not rerun, and no authoritative evaluation was run.

## Ticket 01 — frozen DCv3 structure

The exact frozen configuration is sprint2-dixon-coles-v3:

~~~
time-decay half-life: 365 days
effect regularization: 16.0
optimizer: slsqp-analytic-gradient-v2
maximum iterations: 1,000
function tolerance: 1e-12
projected-gradient tolerance: 1e-3
attack/defence bounds: [-3, 3]
home-advantage bound: [-1.5, 1.5]
rho bound: [-0.25, 0.25]
score tail: 5+
~~~

For fitted teams \(i\) and \(j\), DCv3 constructs goal means as:

\[
\lambda_H=\exp(a_i+d_j+h),\qquad
\lambda_A=\exp(a_j+d_i).
\]

Here \(a_t\) is the team attack effect, \(d_t\) the team defence effect, and \(h\) the one global home advantage. DCv3 has one \(a_t\) and one \(d_t\) for every fitted team. It therefore already represents stable, role-invariant team scoring and allowing differences.

Attack location is fixed by \(\sum_t a_t=0\). The defence vector retains its mean as the global scoring level; its variation is centred for regularization. The fit minimizes the time-weighted Dixon--Coles exact-score negative log likelihood, including the low-score correction \(\tau(x,y;\lambda_H,\lambda_A,\rho)\), plus

\[
P(a,d)=\frac{16}{2}\left(\sum_t a_t^2+\sum_t(d_t-\bar d)^2\right).
\]

The same scalar shrinks attack and defence variation. Matches receive weight \(2^{-\mathit{ageDays}/365}\). The fit is joint: attack, defence, home advantage, and \(\rho\) are optimized together by analytic-gradient SLSQP. It starts from zero attacks, a common defence level based on smoothed observed away goals, the corresponding home/away log-rate ratio, and \(\rho=0\). It fails if SLSQP fails, the objective is non-finite, or the projected gradient exceeds 0.001.

There is no team-specific home/away strength, residual intercept, dynamic state, team-specific variance, or special promoted-team parameter. The model fits every team in eligible history; the frozen walk-forward target rule keeps targets only when each team has at least 10 prior matches and the competition has at least 100. A forecast for an unfitted team fails closed.

The existing state is DixonColesModelStateV1, embedded in PortableModelStateV1. It records the configuration and checksum, training checksum/count/cutoff, unregularized fitted negative log likelihood, convergence, attack and defence mappings, home advantage, and \(\rho\). The portable envelope checksum covers its canonical JSON state; loading checks the manifest, physical state checksum, logical state checksum, model family, algorithm, fit specification, and runtime/feature compatibility.

## Ticket 02 — what the residual finding can mean

The diagnostic found four attack and three defence team mean-residual 95% intervals excluding zero, but no material short-horizon attack or defence persistence, no positive shared match-level intensity, no broad conditional overdispersion, and no identifiable competition effect.

A stable residual can remain after DCv3 for several reasons:

- The one fixed penalty may over-shrink some finite-sample attack or defence contrasts, including because attack and defence share one shrinkage value.
- The fixed penalty may be too weak for other teams; a raw residual offset cannot distinguish that from ordinary sampling variation.
- A home/away-specific effect could leave a role-averaged residual, but the diagnostic did not test role contrasts.
- The apparent offsets can be a multiple-comparison result. Team residuals also share matches, so their uncertainty is correlated.
- A new mean intercept cannot explain the finding as a distinct mechanism: in this log-rate model it is just another name for an existing attack or defence effect.

The retained evidence does not support dynamic state, a general variance extension, a shared-intensity extension, or a competition-level extension.

## Ticket 03 — multiplicity assessment

There were 20 attack and 20 defence interval checks, all at marginal 95% coverage. Under an idealized independent global-null benchmark, two false exclusions are expected across 40 tests. The chance of at least one false exclusion is 64.2% within a 20-test family and 87.1% across all 40 tests. Those figures show why a marginal interval is not a family-wise team claim.

The observed counts are not routine under that same *independent* benchmark:

~~~
attack: 4 of 20, P(X >= 4; n=20, p=0.05) = 0.0159
defence: 3 of 20, P(X >= 3; n=20, p=0.05) = 0.0755
combined: 7 of 40, P(X >= 7; n=40, p=0.05) = 0.00339
~~~

These are calibration checks, not valid p-values: the diagnostic used chronological moving-block bootstrap percentile intervals, and the 40 team statistics are dependent through shared matches and common refits. The retained result has no joint bootstrap distribution from which simultaneous confidence intervals, Bonferroni-adjusted percentile intervals, or a false-discovery procedure can be calculated faithfully.

Conclusion: multiplicity removes any basis for selecting individual teams or for treating seven marginal exclusions as seven confirmed effects. It does not, by itself, make the pooled pattern ordinary enough to negate the original moderate mechanism signal. It is therefore insufficient to freeze a challenger, but not sufficient evidence for the stronger conclusion that no static signal exists.

## Ticket 04 — candidate comparison

| Candidate | Scientific hypothesis and new capability | Redundant with DCv3 | Parameters added | Identifiability and operational assessment | Evidence | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| Direct team residual mean correction | A separate log-rate offset remains after DCv3. Adding \(r^A_t\) and \(r^D_t\) gives \(a'_t=a_t+r^A_t\), \(d'_t=d_t+r^D_t\); it adds no mean capability. | **YES — REDUNDANT_WITH_EXISTING_DCV3** | Global: 0. Team/latent: nominally \(2T\), but none are separately identifiable. | It has the same attack/defence location invariances as DCv3 and cannot be separated from existing effects or their penalty. It cannot have a meaningful cold-start, artifact, deterministic-fit, or falsification contract distinct from DCv3. | UNSUPPORTED as a distinct model | REJECT |
| Separate attack/defence shrinkage scales | The one fixed L2 value \(\lambda=16\) may impose the wrong relative pooling on attack and defence variation. It keeps the same team mean dimensions but permits \(\lambda_A\ne\lambda_D\). | **NO — IDENTIFIABLE_NEW_CAPABILITY** as a changed fitting contract; fixed equal scales recover DCv3. | Global: 1 additional relative to frozen DCv3 (two scales rather than one). Team/latent: 0. | With scales fixed before fitting, the normal centering constraints remain sufficient. If scales are estimated by minimizing the same penalized objective, the optimum drives them toward zero, so a new, explicitly governed hyperparameter objective would be required. It is PIT-safe and no harder to serialize than DCv3, but joint scale fitting, low-sample behaviour, determinism, and synthetic recovery require a separate contract. | WEAK for the exact split-scale mechanism; MODERATE only for a residual pattern potentially consistent with shrinkage | RETAIN AS THE PRIMARY RESEARCH QUESTION, NOT AS A FROZEN CHALLENGER |
| Home/away-specific team effects | A team has persistent role-specific attack or defence effects beyond \(h\). This adds role deviations to ordinary attack and defence effects. | **NO — IDENTIFIABLE_NEW_CAPABILITY** when each deviation is centred and all deviations are zero in the DCv3 limit. | Global: 0. Team/latent: about \(4(T-1)\) role deviations. | It is confounded with the global home advantage without strict centering and is poorly sample-efficient for low-history teams. It increases numerical, artifact, deterministic-testing, and overfitting risk. The diagnostic did not estimate home/away contrasts. | UNSUPPORTED | REJECT |

The second candidate is the smallest non-duplicative structural question. It does not establish that split regularization is correct. It only identifies the one existing DCv3 design choice that could produce role-invariant static residual offsets without adding duplicate team mean parameters.

## Decision

~~~
Conclusion: C. EXISTING_DCV3_REGULARIZATION_IS_PRIMARY_RESEARCH_TARGET
~~~

No static-heterogeneity challenger contract is frozen. The required evidence does not identify a new mean parameterization, a home/away mechanism, or a scientifically justified method for estimating new shrinkage scales. A direct residual correction is algebraically redundant, while home/away effects would add many unsupported latent parameters.

The smallest separately versioned research question is:

~~~
Does frozen DCv3's single regularization strength systematically over- or under-shrink attack and defence effects, and can separately identified attack/defence shrinkage scales be justified on synthetic data and a separately authorized training-only context?
~~~

This is not permission to change sprint2-dixon-coles-v3. If the owner later authorizes that question, it must define a new algorithm identifier, a non-degenerate scale-selection objective, joint fitting rules, parameter domains, failure rules, artifact fields, and synthetic tests before any real-data challenger fit. It must first prove DCv3-limit recovery, known-heterogeneity recovery, low-sample behaviour, input-order invariance, deterministic repeated fitting, probability normalization, artifact round-trip, and corruption/boundary rejection. Any later training-only admission must be independently authorized and must not use the La Liga diagnostic targets for tuning.

## Owner handoff

~~~
Recommended next action:
Owner review of whether to authorize the separately versioned, synthetic-first regularization research question above. No fit or admission is authorized by this record.

Frozen DCv3: UNCHANGED
La Liga diagnostic: NOT RETUNED / NOT USED FOR CHALLENGER FITTING
Frozen 280 EPL outcomes: NOT ACCESSED
Protected 100-match admission: NOT REUSED
Shared-pace admission: NOT RERUN
Candidate implementation: NOT PERFORMED
Authoritative evaluation: NOT RUN / NOT AUTHORIZED
Sprint 2: FAIL
Model promoted: false
Phase 3: BLOCKED / UNAUTHORIZED
Production changes: NONE
~~~

Wayfinder map: COMPLETE
