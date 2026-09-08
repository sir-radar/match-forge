# DCv3 Shared Match-Pace Corrected Deterministic Feasibility — 2026-09-08

## Result

```text
Execution: new provenance-bound feasibility rerun
Algorithm: DCV3_SHARED_MATCH_PACE_MIXTURE_V1
Result: CORRECTED_DETERMINISTIC_FEASIBILITY_PASS
```

This is a new execution against a different immutable source state. It does
not replace or reinterpret the historical record:

```text
Historical Ticket 03: FAIL
Previous correction attempt: NOT VERIFIED
Latest multi-defect correction: VERIFIED
Sprint 2: FAIL
Model promoted: false
Phase 3: BLOCKED / UNAUTHORIZED
```

This pass is deterministic-feasibility evidence only. It does not authorize
Ticket 04 admission, access to the frozen 280 targets, authoritative
evaluation, promotion, or Phase 3 work.

## Source lineage

```text
Ticket 01 base commit: 4c0d6cc340d27b1448e39417e9f03dd1dbeefaa7
Ticket 01 base tree: 93ebaf103772d6dc5c5a9468f0a3386154414755
Ticket 01 carry-forward patch SHA-256: 88ffaa4b421efc2993451d1e1d77d94bc0a005a415c5a157989592eebc178af0
Ticket 02 implementation commit: c4ca903f8842a15d459c2a4ccff7993e18e61e4c
PR #95 merge provenance: 4852ec23ac9d7b6d8afff7e3feb337c3a0fe8477
Historical failure evidence: docs/evidence/dcv3-shared-match-pace-deterministic-feasibility-2026-09-08.md
Numerical research conclusion: IMPLEMENTATION_NUMERICAL_DEFECT
First correction attempt: NOT VERIFIED
Multiple-defect diagnostic conclusion: MULTIPLE_IMPLEMENTATION_DEFECTS

Corrected implementation commit: be078729d527a43be1f7144f7c001de1e2b789eb
Corrected source tree: 0ef0305b3bbedb3cc652228681b61aeb28b3a891
Corrected source parent: 363b984d39cc12d8c33852ace43236ba1d3bc265
uv.lock SHA-256: d14def6539f213b2af3011975062ed3e1e0bba2d86e8064803bd3d86d0a39e4e
```

The source commit contains only the authorized shared-match-pace production
correction and its regressions. `git diff --check` passed before that commit.

The fresh gate ran in:

```text
/Users/radar/Desktop/football-simutation-dcv3-shared-match-pace-corrected-feasibility
HEAD: be078729d527a43be1f7144f7c001de1e2b789eb
tree: 0ef0305b3bbedb3cc652228681b61aeb28b3a891
status before execution: clean
status after all gates, before this evidence record: clean
```

## Frozen correction under test

The corrected implementation preserves the agreed distribution:

```text
Z ~ Uniform(1 - kappa, 1 + kappa)
P(N = n) = 1 / (2 kappa) integral[1-kappa, 1+kappa] PoissonPMF(n; mu z) dz
```

For `h = mu * kappa <= 0.05`, it evaluates the same centered integral using
the degree-7 Taylor integral and `math.fsum`. The deterministic bound on the
finite numerical evaluation is below `1.1e-15`; this changes numerical
evaluation, not the probability family. Above that conditioning boundary, it
retains the legacy binary64 endpoint construction exactly:

```python
lower = mean * (1.0 - kappa)
upper = mean * (1.0 + kappa)
```

The correction also associates an optimizer candidate with its own detected
profile basin before comparing it with other minima. The frozen rules for a
genuine distinct basin remain unchanged:

```text
|kappa_a - kappa_b| > 1e-8
|J(kappa_a) - J(kappa_b)| <= tau_J
```

## Environment

```text
Bootstrap: make bootstrap
Python: CPython 3.13.14
uv: 0.12.1
SciPy: 1.18.1
pytest: 8.4.2
Platform: macOS-26.6.2-arm64-arm-64bit-Mach-O
```

## Gate results

### Gate 1 — historical failing oracle first

The first substantive check was the historical synthetic fixture, evaluated
against an independent 100-decimal oracle:

```text
lambda_home: 0.02
lambda_away: 0.03
mu: 0.05
kappa: 1e-8
rho: 0.0
score: 0-0

expected: 0.9512294245007140091310598791338485777030589363231194297706996094765558870790959396699597321646867962
observed: 0.9512294245007140158776337557355873286724090576171875
absolute error: 6.7465738766017387509693501212940680702293003905234441129209040603300402678353132038e-18
required absolute error: <= 1e-12
result: PASS
```

Command:

```text
. ./scripts/toolchain.sh
uv run pytest -q python/football/tests/test_dixon_coles_shared_match_pace.py -k near_zero_kappa_zero_total_probability_matches_stable_oracle
```

### Gate 2 — independent probability, boundary, moment, profile, and determinism checks

The independent 100-decimal centered-integral stress check covered `720`
probability cases plus `108` legal branch-boundary cases. It included
`kappa = 0`, very small positive kappa, the `h = 0.05` boundary and adjacent
representable values, legacy-path values, ordinary interior values, values
near one, and `kappa = 1`; small through large tested means; and low through
high tested total-goal counts.

```text
stable path cases: 618
legacy path cases: 102
maximum absolute error: 1.380423553243304e-13
worst case: mean=50, kappa=0.0010000000000000002, h=0.05000000000000001, n=50
all absolute errors <= 1e-12: true
stress output SHA-256: 89439b3b8c6985331d7f272482f8e29f1c6c1f051f7cfe37322420c832ec6965
```

The explicit pre-rho joint-moment check used 100-by-100 score supports for
small, ordinary, high, and `kappa = 1` inputs. Normalization and both means
were within `4.5e-15`; the largest covariance error against
`lambda_home * lambda_away * kappa**2 / 3` was `4.9e-15`.

```text
moment output SHA-256: 00b18b27e281c36390e39f2ae508be6d34e0714f4f49d9ed4d6036b375489ec4
```

The synthetic interior profile had exactly one detected minimum, index `974`.
The production candidate and its refined result belonged to that same basin;
the independent profile had the same minimum index. The largest production
versus independent profile-value difference was `4.440892098500626e-15`.
The distinct-basin ambiguity regression remains covered by the focused suite.

```text
profile output SHA-256: 6fbf4281da0ae7da07e2418813bf798cba36c18a2efd4cf7b5de7bdba280f9a4
```

Two independent fresh processes each fitted the synthetic set in canonical,
reversed, and fixed permuted order. All five logical state hashes were:

```text
c200501b684c6717d29cd3bafd1cee2148b9a95acd42216ae805cb698ebaf1e8
```

The two result files were byte-identical; fits and forecasts were equal.

```text
determinism output SHA-256: be45ac75c4e89620ec8022b7147ea2a467e67ed690ed0432acb78ccfe1b8d9cd
```

### Gate 3 — complete shared-match-pace suite

```text
. ./scripts/toolchain.sh
uv run pytest -q python/football/tests/test_dixon_coles_shared_match_pace.py
result: 29 passed
```

The suite verifies the exact DCv3 limit, convergence from small positive
kappa, probability bounds and support failure, mean/normalization, frozen rho
four-cell transfer and marginals, weighted exact joint-score NLL, frozen
optimizer settings, deterministic and input-order-independent fitting,
same-basin and distinct-basin profile behavior, unified forecast products,
and artifact round-trip, corruption, invalid-kappa, and config-checksum
rejection.

The synthetic inputs use explicit historical kickoff order only. No frozen
Sprint 2 target was accessed, joined, forecast, or scored.

### Gate 4 — repository quality gate

```text
make check
result: PASS
```

```text
ruff format: 209 files already formatted
ruff lint: All checks passed
mypy: Success: no issues found in 190 source files
golangci-lint: 0 issues
Python tests: 403 passed in 80.20s
Rust tests: 1 passed
Go tests: PASS
Python build: source distribution and wheel built
ProjectStatusV1: valid
make-check log SHA-256: 98f48647bad858eb73973baeb612f3b509a2fd973baff60893616b32db94f3f8
```

`make sprint2-evaluate` was not run.

## Frozen-contract and route status

```text
Mathematical distribution: unchanged
kappa domain and accepted fitted interval: unchanged
Rho composition: unchanged
Weighted joint-score NLL, decay, and training scope: unchanged
Optimizer, profile resolution, stationarity, and thresholds: unchanged
Support/tail and artifact contracts: unchanged
Admission: NOT RUN / NOT AUTHORIZED
Frozen 280 targets: NOT ACCESSED
Authoritative evaluation: NOT RUN
Sprint 2: FAIL
Model promotion: false
Phase 3: BLOCKED / UNAUTHORIZED
```
