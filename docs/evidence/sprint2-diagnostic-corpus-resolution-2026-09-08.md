# Sprint 2 diagnostic corpus resolution — 2026-09-08

## Result

```text
Status: BLOCKED — NO_ELIGIBLE_DIAGNOSTIC_CORPUS
Diagnostic corpus: NOT CREATED
```

The authorized diagnostic requires one point-in-time-valid corpus that is
disjoint from both the frozen 280-target Sprint 2 evaluation population and
the terminal 100-match shared-pace admission population. No such corpus is
available in the local governed data.

This record is a pre-analysis corpus-resolution result. It contains no
forecast, outcome, residual, score, challenger fit, or target-level data.

## Predeclared selection and qualification rule

Before outcome inspection, an eligible diagnostic corpus was defined as the
complete canonical match population for one published dataset,
competition, and season with at least 120 matches. The threshold was chosen
to permit the planned 30-observation minimum for a reported predicted-mean
bucket or chronological block; diagnostics below their own threshold would
have been marked `INSUFFICIENT_SAMPLE` rather than merged.

The intended diagnostic thresholds were:

```text
Predicted-mean bucket: 30 matches
Team aggregate:        12 team appearances
Time block:             30 matches
Competition aggregate:  60 matches in each of at least 3 competitions
```

No outcomes were read while applying this rule.

## Governed-data availability

Read-only metadata queries found exactly one competition-season with at least
10 canonical matches:

```text
Dataset version:       d62b97d6-f39b-5f14-9773-61f57f7b677b
Source snapshot:       01a0534c-cb84-702b-8249-a0a572a2f280
Competition:           01a051db-5565-70d1-85d4-ab6342d86baf
Season:                01a051db-5566-7286-8ad7-40d945ab8253
Canonical matches:     380
Other competition-seasons with >=10 matches: 0
```

The retained Sprint 2 contract records 280 frozen targets in this same
competition-season after 100 warm-up exclusions. The shared-pace admission
harness defines a 100-match population of completed matches strictly before
`2015-10-31T13:45:00Z`; its retained population identity is
`8f3813c9fa6d2053d3916e6ee242d7c3497da85745ad6fe614a5ec1f87b79f25`.

The two governed populations are temporally disjoint: admission matches are
strictly before that cutoff, while the frozen target range begins at the same
cutoff. Their documented counts sum to the complete canonical population:

```text
100 admission matches + 280 frozen targets = 380 canonical matches
```

Therefore they partition the only adequately sized canonical
competition-season. A third non-empty, disjoint population cannot be selected
from it. The remaining local competition-seasons have one match each and fail
the predeclared corpus threshold.

This is a cardinality and time-boundary proof only. It does not enumerate,
load, join, forecast, score, or inspect any frozen target or admission match.

## Provenance

```text
Code SHA:               c733cc34be07009c8f5f1948123f075b35b63291
uv.lock SHA-256:        d14def6539f213b2af3011975062ed3e1e0bba2d86e8064803bd3d86d0a39e4e
Knowledge mode:         retrospective-fixed-snapshot-v1
Knowledge cutoff:       Not applicable; no diagnostic scope was created
Football-time range:    Not applicable; no diagnostic scope was created
Population count:       Not applicable; no diagnostic population exists
Population SHA-256:     Not applicable; no diagnostic population exists
```

## Required diagnostic outputs

Not produced. The authorization requires a valid frozen corpus before
forecasting or outcome inspection; creating residual, variance, covariance,
team-persistence, shape, or time-period outputs without one would violate
that order.

## Next action

Authorize or publish a separate canonical, point-in-time-valid diagnostic
dataset/competition-season that is not part of either protected population.
Its corpus must be frozen and proven disjoint before any frozen-DCv3
forecasts or outcome diagnostics run.

## Boundaries

```text
Frozen 280 targets:                 NOT ACCESSED
Shared-pace admission:              NOT RERUN
Candidate challengers:              NOT FIT
Authoritative Sprint 2 evaluation:  NOT RUN / NOT AUTHORIZED
Sprint 2:                           FAIL
Model promoted:                     false
Phase 3:                            BLOCKED / UNAUTHORIZED
Production changes:                 NONE
```
