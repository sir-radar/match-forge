# Full-coverage challenger V2 development result

Protocol: `MATCHFORGE_FULL_COVERAGE_CHALLENGERS_V2_DEVELOPMENT_V1`

Result: `FAIL_CLOSED_PROTOCOL_VIOLATION`

The V2A/V2B implementation is complete and its architecture checks pass. A
development diagnostic reached 100% fixture coverage for every challenger and
ensemble through native forecasts, cold start, or explicit whole-fixture
champion fallback.

The diagnostic is not authoritative. It called the executor directly while the
implementation was uncommitted, and the direct entry point did not yet repeat
the clean-HEAD preflight. Development outcomes were loaded before this defect
was identified. Computed comparison metrics were discarded and are not
published.

The executor now fails before data loading unless the supplied source commit is
the clean current `HEAD`. A regression test covers the direct-call path. The
development protocol was not rerun.

## Diagnostic coverage

The 300-fixture development holdout produced forecasts for all 300 fixtures for
each V2A, V2B, and ensemble model.

- V2A Dixon-Coles, Negative Binomial, and Weibull-Copula used champion fallback
  on 55% of fixtures.
- V2B Dixon-Coles and Negative Binomial used native cold start on 55% and did
  not use champion fallback.
- V2B Weibull-Copula used explicit champion fallback on 55% because no tested
  stable cold-start parameter adapter exists.
- The V2A ensemble included champion component weight but did not classify that
  as whole-ensemble fallback.
- The V2B ensemble used cold-start components on 55% and did not fall back as a
  whole ensemble.

These figures verify routing and accounting only. They do not establish model
quality or satisfy development acceptance.

## Selected diagnostic configuration

- Shrinkage `k`: `40`
- L2 regularization: `0.01`
- Transfer weight: `0` because no qualified cross-competition relationship was
  available
- Split: chronological 60/20/20 by kickoff batch

This selection is non-authoritative and must not be promoted.

## Verification

- `make lint`: pass
- `make test`: 721 Python tests and 15 Rust tests pass; Go tests pass
- `make integration`: pass
- `make project-status-check`: pass
- `make check`: pass, including 6 web test files and 21 web tests
- `git diff --check`: pass

Implementation source commit:
`dfdd0876394b40998bfb2edbfc8c264b8b634614`

## Disposition

No production promotion is justified. No unspent authorized independent
evaluation corpus exists. Do not rerun this protocol without an explicit owner
decision. The next valid step is a new protocol with an unspent development or
independent evaluation corpus.
