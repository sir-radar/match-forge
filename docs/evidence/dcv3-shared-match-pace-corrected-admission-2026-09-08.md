# DCv3 Shared Match-Pace Corrected Admission — 2026-09-08

## Result

```text
Execution: frozen 100-match training-only admission
Algorithm: DCV3_SHARED_MATCH_PACE_MIXTURE_V1
Result: FROZEN_100_MATCH_TRAINING_ONLY_ADMISSION_FAIL
```

The terminal failure occurred in the first `60/10` fold before any validation
forecast or score was produced:

```text
First failed condition: LOWER_BOUNDARY_DCV3_LIMIT
Stage: fit kappa after the frozen DCv3 base state
Accepted fitted kappa interval: strictly inside (0, 1)
```

The frozen implementation rejects the lower-boundary DCv3 limit rather than
publishing a challenger state outside the accepted fitted interval. The
authorization requires an immediate stop on a hard failure. No optimizer,
contract, training window, metric, or challenger setting was changed, and the
admission was not retried.

## Provenance gate

```text
Corrected implementation SHA: be078729d527a43be1f7144f7c001de1e2b789eb
Corrected source tree: 0ef0305b3bbedb3cc652228681b61aeb28b3a891
PR #98 merge provenance: 5a5f982bb1e26057e9415ad0e0279c64af5ecefe
Execution source: abc844a759fb52fba14c4e831b8107f4b95cf36c
uv.lock SHA-256: d14def6539f213b2af3011975062ed3e1e0bba2d86e8064803bd3d86d0a39e4e
```

Before admission, the run verified that the corrected implementation commit is
an ancestor of the execution source, resolves to the stated source tree, and
that no file under `python/football/src/football/forecasting` or the
shared-match-pace test changed after the corrected source. The dependency lock
checksum matches the corrected deterministic-feasibility record. PR #98 merged
the corrected source through `5a5f982bb1e26057e9415ad0e0279c64af5ecefe`.

## Authorized command

```text
. ./scripts/toolchain.sh
MF_DB_URL='postgresql://football:football-local-only@127.0.0.1:55433/football?sslmode=disable' \
MF_ADMISSION_ARTIFACT_ROOT='.scratch/wayfinder/dcv3-shared-match-pace-implementation-admission/evidence/corrected-admission-artifacts' \
MF_ADMISSION_REPORT_PATH='.scratch/wayfinder/dcv3-shared-match-pace-implementation-admission/evidence/DCV3SharedMatchPaceAdmissionReportV1.json' \
uv run python .scratch/wayfinder/dcv3-shared-match-pace-implementation-admission/run_corrected_admission.py
```

The harness binds the existing governed 100-match admission population:

```text
Population SHA-256: 8f3813c9fa6d2053d3916e6ee242d7c3497da85745ad6fe614a5ec1f87b79f25
Population count: 100
Dataset version ID: d62b97d6-f39b-5f14-9773-61f57f7b677b
Source snapshot ID: 01a0534c-cb84-702b-8249-a0a572a2f280
Knowledge mode: retrospective-fixed-snapshot-v1
```

It defines only the authorized folds `60/10`, `70/10`, `80/10`, and `90/10`.
For a completed fold it would freeze the DCv3 state, fit only kappa, publish
and reload the challenger artifact, freeze all validation forecasts before
outcome scoring, and then reproduce the complete run. The first challenger fit
failed before those later actions became applicable.

## Terminal admission state

```text
Admission: FAIL

Windows:
60/10: FAIL — LOWER_BOUNDARY_DCV3_LIMIT
70/10: NOT RUN
80/10: NOT RUN
90/10: NOT RUN

Validation targets forecast: 0
Validation targets scored: 0

DCv3 pooled total-goal CRPS: NOT COMPUTED
Challenger pooled total-goal CRPS: NOT COMPUTED
DCv3 pooled exact-score NLL: NOT COMPUTED
Challenger pooled exact-score NLL: NOT COMPUTED

Integrity: FAIL — challenger fit did not produce an accepted kappa
Determinism: NOT RUN
Artifacts: NOT RUN
Reload: NOT RUN
Point-in-time: NOT RUN AFTER TERMINAL FIT FAILURE
Leakage: NOT RUN AFTER TERMINAL FIT FAILURE
Corrected feasibility: PASS
Historical Ticket 03: FAIL — PRESERVED

Frozen-contract changes: NONE
Frozen 280 targets: NOT ACCESSED
Authoritative evaluation: NOT RUN / NOT AUTHORIZED
Sprint 2: FAIL
Model promoted: false
Phase 3: BLOCKED / UNAUTHORIZED
```

The run did not invoke `make sprint2-evaluate`, load an authoritative target
plan, or request an authoritative outcome, forecast, score, bootstrap, or
diagnostic. It queried only the separately governed 100-match admission
population.

## Owner handoff

The frozen training-only admission is terminally `FAIL`. The current route
therefore stops for owner review. This result does not authorize a changed
implementation, a retry with different settings, authoritative evaluation,
promotion, a Sprint 2 status change, or Phase 3 work.
