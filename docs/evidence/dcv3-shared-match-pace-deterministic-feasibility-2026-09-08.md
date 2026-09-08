# DCv3 Shared Match-Pace Deterministic Feasibility — 2026-09-08

## Terminal result

```text
Ticket: 03 — Run clean deterministic feasibility
Algorithm: DCV3_SHARED_MATCH_PACE_MIXTURE_V1
Result: FAIL
```

## Source lineage

```text
Ticket 02 implementation commit: c4ca903f8842a15d459c2a4ccff7993e18e61e4c
PR #95 merge provenance: 4852ec23ac9d7b6d8afff7e3feb337c3a0fe8477
Ticket 01 base commit: 4c0d6cc340d27b1448e39417e9f03dd1dbeefaa7
Ticket 01 base tree: 93ebaf103772d6dc5c5a9468f0a3386154414755
Ticket 01 carry-forward patch SHA-256: 88ffaa4b421efc2993451d1e1d77d94bc0a005a415c5a157989592eebc178af0
Worktree status before execution: clean
uv.lock SHA-256: d14def6539f213b2af3011975062ed3e1e0bba2d86e8064803bd3d86d0a39e4e
```

## Environment

```text
Python: CPython 3.13.14
uv: 0.12.1
SciPy: 1.18.1
pytest: 8.4.2
Platform: macOS-26.6.2-arm64-arm-64bit-Mach-O
```

## Commands and observations

```text
. ./scripts/toolchain.sh
uv run pytest -q python/football/tests/test_dixon_coles_shared_match_pace.py
exit status: 0
```

The existing focused implementation suite is supporting evidence only. It does
not resolve this gate.

The independent deterministic oracle then evaluated the pre-rho exact-score
probability for this permitted synthetic fixture:

```text
lambda_home: 0.02
lambda_away: 0.03
kappa: 0.00000001
rho: 0.0
score: 0-0
```

For this score, the independent high-precision oracle is:

```text
(exp(-0.05 * (1 - kappa)) - exp(-0.05 * (1 + kappa)))
----------------------------------------------------------------
                         2 * kappa * 0.05
```

Observed values:

```text
expected: 0.95122942450071400913105987913384857770305893632311942977069960947655589
observed: 0.95122943431492135
absolute error: 9.8142073424476156e-9
```

## Failed invariant

```text
Invariant: mathematical distribution — B(0,0;kappa) agrees with an independent
           deterministic oracle near kappa = 0 within the frozen numerical contract.
Test: high-precision independent near-zero-kappa oracle.
Expected: exact uniform shared-pace mixture value shown above.
Observed: implementation result differs by 9.8142073424476156e-9.
Failure identifier: none defined by the frozen contract.
```

This is a substantive feasibility failure. Per Ticket 03, execution stopped
immediately: no broader quality gate, Ticket 04 admission, frozen 280-target
access, or authoritative Sprint 2 evaluation was run.

## Route boundaries

```text
Frozen-contract changes: NONE
Training-only admission: NOT RUN
Frozen 280-target access: NOT PERFORMED
Authoritative Sprint 2 evaluation: NOT RUN / NOT AUTHORIZED
Sprint 2: FAIL
Model promoted: false
Phase 3: BLOCKED / UNAUTHORIZED
```
