# DCv3 low-score structure diagnostic — 2026-09-09

## Map

```text
Frozen DCv3 Low-Score Structure Diagnostic
```

This is a bounded, read-only diagnostic. It used only the retained corrected
frozen La Liga forecasts and did not fit, retune, or alter DCv3 or a
challenger.

## Bound evidence

```text
Dataset: StatsBomb La Liga 2015/16
Dataset version: 670662d6-6ed7-5fa1-ba3c-1cfd561e524f
Source snapshot: 01a08471-f763-7787-80ca-4293316b7e44
Diagnostic targets: 280 across 243 kickoff batches
Target SHA-256: b758e795d41f0cc84145626d20d791eccbcfbd9fb94d2767039bdcdf50f3eb18
Corrected diagnostic artifact SHA-256: 120ca2e0e135942d7d0b0316d8035562e9d57426225fe3d49dedf4ada445ee5e
Frozen model: sprint2-dixon-coles-v3
```

The cell-level method was frozen before result generation in
[dcv3-low-score-structure-diagnostic-protocol-2026-09-09.md](dcv3-low-score-structure-diagnostic-protocol-2026-09-09.md).
It uses a circular chronological moving-block bootstrap over retained kickoff
batches: 10-batch blocks, 2,000 replicates, seed `20260909`. The primary
family is the four frozen-DC cells together, using simultaneous 95%
max-standardized centered-bootstrap intervals.

## Production DCv3 mathematics

The analysis verified each computed low-score value against its frozen joint
forecast state. For independent Poisson mass `p(x,y)`, production DCv3 uses:

```text
P(x,y) = p(x,y) * tau(x,y; lambda_home, lambda_away, rho)

tau(0,0) = 1 - lambda_home * lambda_away * rho
tau(0,1) = 1 + lambda_home * rho
tau(1,0) = 1 + lambda_away * rho
tau(1,1) = 1 - rho
tau(x,y) = 1 otherwise
```

Increasing rho decreases `0-0` and `1-1`, and increases `0-1` and `1-0`.
The reverse occurs when rho decreases. The four changes sum to zero, so this
is a transfer of mass within the four cells; all other independent-Poisson
cells are unchanged.

## Rho behaviour

```text
Observations: 280
Mean: -0.11319
Median: -0.13260
Sample standard deviation: 0.06024
Minimum / maximum: -0.24315 / -0.03473
P05 / P25 / P75 / P95: -0.20368 / -0.16351 / -0.05084 / -0.03895
At lower bound (-0.25): 0.00%
At upper bound (0.25): 0.00%
Within 0.01 of lower bound: 1.07%
Within 0.01 of upper bound: 0.00%
Within 0.01 of zero: 0.00%
```

Rho is comfortably interior: no fit hits either bound and only three of 280
forecasts are within 0.01 of the lower bound. Chronological block mean rho
moves from `-0.18334`, to `-0.15282`, `-0.07930`, and `-0.04845` (range
`0.13489`); the sequence changes materially through time but does not show
boundary constraint. Boundary proximity therefore provides no evidence of
insufficient flexibility.

## Low-score calibration

| Cell | Predicted expected count / frequency | Observed count / frequency | Error | Simultaneous 95% interval |
| --- | ---: | ---: | ---: | ---: |
| 0-0 | 24.92 / 8.90% | 13 / 4.64% | -4.26 pp | [-6.91, -1.60] pp |
| 0-1 | 18.84 / 6.73% | 21 / 7.50% | +0.77 pp | [-3.25, +4.79] pp |
| 1-0 | 26.99 / 9.64% | 27 / 9.64% | +0.00 pp | [-4.09, +4.10] pp |
| 1-1 | 34.95 / 12.48% | 35 / 12.50% | +0.02 pp | [-4.89, +4.92] pp |

The retained zero-total finding is exactly a 0-0 finding. It remains material
after four-cell simultaneous inference. The neighbouring cells show no
simultaneous exclusion, so there is no robust compensating low-score vector.

## Independent-Poisson decomposition

With rho set to zero but frozen lambdas retained, 0-0 has predicted expected
count `21.31` / frequency `7.61%`, versus observed `13` / `4.64%`: error
`-2.97` pp, marginal moving-block 95% interval `[-4.96, -0.83]` pp. Thus the
underlying means already overpredict 0-0.

Frozen DC raises predicted 0-0 to `8.90%`, increasing absolute error from
`2.97` pp to `4.26` pp. Its effect on 0-0 calibration is `WORSENS`; error
origin is `BOTH`, not purely means or rho. The other correction effects are:

| Cell | Independent error | Frozen-DC error | Rho correction effect |
| --- | ---: | ---: | --- |
| 0-0 | -2.97 pp | -4.26 pp | WORSENS |
| 0-1 | -0.52 pp | +0.77 pp | WORSENS |
| 1-0 | -1.29 pp | +0.00 pp | IMPROVES |
| 1-1 | +1.31 pp | +0.02 pp | IMPROVES |

The earlier mean-bias buckets remain non-excluding, but this targeted
counterfactual shows that their aggregate result does not rule out a 0-0
mean contribution.

## Safeguards and shape checks

Frozen-DC 0-0 probability strata are forecast-only equal-count groups:

| Stratum | Targets | Mean lambda home / away | Predicted 0-0 | Observed 0-0 | Error | Marginal 95% interval |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Lowest predicted 0-0 | 93 | 1.925 / 1.267 | 5.22% | 1.08% | -4.15 pp | [-5.42, -1.54] pp |
| Middle | 93 | 1.495 / 1.110 | 8.81% | 3.23% | -5.58 pp | [-8.84, -2.10] pp |
| Highest predicted 0-0 | 94 | 1.259 / 0.967 | 12.63% | 9.57% | -3.06 pp | [-7.69, +2.31] pp |

The 0-0 error is negative in every earlier predeclared chronological block:
`-5.62`, `-3.84`, `-5.32`, and `-2.52` pp. The directional signal therefore
appears across all four periods, not one isolated block. These descriptive
block values are not separate inference tests.

Team net-contribution concentration is low: the largest team accounts for
`10.01%`, top three for `25.02%`, and effective concentration is `17.31`
teams. The 0-0 residual is not dominated by a small team subset.

The point-estimate error directions are not jointly moved toward zero by a
single signed rho adjustment: increasing rho would decrease `0-0` as needed
but also decrease `1-1`, whose point error is positive; decreasing rho fails
the 0-0 direction. However, only 0-0 survives the simultaneous family.
Formal scalar-rho directional compatibility is therefore `INCONCLUSIVE`, not
an inference-backed incompatibility result.

## Conclusion

```text
FROZEN_DCV3_LOW_SCORE_STRUCTURE_DIAGNOSTIC_COMPLETE

Conclusion:
E. LOW_SCORE_MECHANISM_INCONCLUSIVE

Dataset:
StatsBomb La Liga 2015/16

Targets:
280

Frozen DCv3:
UNCHANGED

Rho observations:
280

Rho boundary behaviour:
Comfortably interior; no boundary hits. Block means change from -0.18334 to -0.04845.
```

```text
Independent-Poisson 0-0 error:
-2.97 pp, marginal 95% interval [-4.96, -0.83] pp

Frozen-DC 0-0 error:
-4.26 pp, simultaneous 95% interval [-6.91, -1.60] pp

Effect of rho correction on 0-0 calibration:
WORSENS

Error origin:
BOTH

Scalar-rho directional compatibility:
INCONCLUSIVE

Chronological robustness:
Negative 0-0 error in all four predeclared chronological blocks.

Team concentration:
Top team 10.01%; top three 25.02%; effective concentration 17.31 teams.

Multiplicity-aware low-score evidence:
Only 0-0 excludes zero in the four-cell simultaneous family.

Recommended next action:
AUTHORIZE_ADDITIONAL_INDEPENDENT_LOW_SCORE_DIAGNOSTIC
```

The smallest next evidence is one fresh, independently retained season or
competition forecast artifact using this exact four-cell, frozen-lambda,
moving-block and simultaneous-inference protocol. It must decide whether the
same decomposition reproduces before any low-score contract research.

```text
Static heterogeneity challenger:
NOT JUSTIFIED

Frozen DCv3:
UNCHANGED

La Liga forecasts:
NOT REFIT / NOT RETUNED

Candidate models:
NOT FIT

Frozen EPL 280 outcomes:
NOT ACCESSED

Protected 100-match admission population:
NOT REUSED

Authoritative evaluation:
NOT RUN / NOT AUTHORIZED

Sprint 2:
FAIL

Model promoted:
false

Phase 3:
BLOCKED / UNAUTHORIZED

Production changes:
NONE
```

## Reproducibility

```text
Input diagnostic SHA-256: 120ca2e0e135942d7d0b0316d8035562e9d57426225fe3d49dedf4ada445ee5e
Target SHA-256: b758e795d41f0cc84145626d20d791eccbcfbd9fb94d2767039bdcdf50f3eb18
Code Git SHA: 72361cabedfaff850ee8ff73c32e97eadb8c7499
Diagnostic script SHA-256: bf3231670e6bdc9cd47d049f04b221b875a6461ffbc6cb9396aab0b03ef441b9
Dependency-lock SHA-256: d14def6539f213b2af3011975062ed3e1e0bba2d86e8064803bd3d86d0a39e4e
Bootstrap: circular chronological moving-block; 10 batches; 2,000 replicates; seed 20260909
Cell family: 0-0, 0-1, 1-0, 1-1
Result SHA-256: 415eea25660e4724efce92280323a1d1f8550d4453081c2b11e89519f4c83c0f
Output SHA-256, run 1: 3a2caab45974a05ab5c09126002e907ea5bd5b0f75b698fdca701f09a27f0661
Output SHA-256, run 2: 3a2caab45974a05ab5c09126002e907ea5bd5b0f75b698fdca701f09a27f0661
```

Machine-readable evidence:
[dcv3-low-score-structure-diagnostic-2026-09-09.json](dcv3-low-score-structure-diagnostic-2026-09-09.json).
