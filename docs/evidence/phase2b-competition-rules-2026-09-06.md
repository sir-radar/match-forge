# Phase 2B competition-rules evidence

Status: `FAIL`

This evidence checks the Phase 2B competition-rules requirement. It does not
change Sprint 2 evidence, promote a model, or authorize Phase 3.

## Inputs

- Code commit: `368bc36cadd049fc94320f353c8298a9c0254b52`
- Dependency lock SHA-256:
  `d14def6539f213b2af3011975062ed3e1e0bba2d86e8064803bd3d86d0a39e4e`
- Command: `uv run pytest python/football/tests/test_competition_rules.py`
- Result: 3 passed

## Current corpus rules

The approved StatsBomb Open Data EPL 2015/16 corpus and the bounded
Football-Data.co.uk P1 overlap are league data. They use this deterministic
`CompetitionRulesV1` record:

| Field | Value |
| --- | --- |
| rules ID | `premier-league-epl-2015-16-regulation-v1` |
| competition reference | `statsbomb_open_data:competition:2` |
| format | `LEAGUE` |
| fixture structure | `ROUND_ROBIN` |
| outcome scope | `REGULATION_TIME` |
| extra time | `NEVER` |
| shootout | `NEVER` |
| neutral venue | `NOT_APPLICABLE` |
| policy version | `competition-rules-v1` |
| rule SHA-256 | `ae6701cb613a3ce024bd314de0c86d15312102c8e14a33d4c3efc97b68b129fc` |

Its source references are:

- `statsbomb_open_data/competition/2`
- `football_data_uk/mmz4281/1516/E0.csv/sha256/bd3502a18c38a1597fd9af62e2366b4015006d3528dd4d18b311bd6237bbc085`

The contract tests also exercise a knockout, two-leg, extra-time, and shootout
combination. This is contract coverage only: the current approved corpus has no
knockout or neutral-venue competition to claim as supported data.

## Blocking result

`CompetitionRulesV1` can represent the required rules, but
`BaselineForecastV1` and `EvaluationCorpusV1` do not carry a rules ID or an
outcome scope. Their persisted outputs therefore cannot prove which result
scope they predict. The rules must be bound to new forecast and evaluation
records before this check can pass.

```text
CompetitionRulesV1 contract = PASS
Forecast/evaluation outcome-scope binding = FAIL
Phase 2B competition-rules evidence = FAIL

Sprint 2 = FAIL
Phase 3 = blocked
```
