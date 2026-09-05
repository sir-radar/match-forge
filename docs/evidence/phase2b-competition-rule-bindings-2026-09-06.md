# Phase 2B competition-rule binding evidence

Status: `PASS`

This record closes the outcome-scope binding failure in the earlier
competition-rules evidence. It does not change Sprint 2 metrics, promotion, or
Phase 3 authorization.

## Inputs

- Code commit: `30bd41a4d13c95fa0a7dd5391080d48e62a953d7`
- Dependency lock SHA-256:
  `d14def6539f213b2af3011975062ed3e1e0bba2d86e8064803bd3d86d0a39e4e`
- `make check`: passed; 328 Python tests passed, with Rust and Go checks and
  builds also passing.
- `make integration`: passed from an empty database through migration
  `202609060100_competition_rule_bindings.sql`.

## Binding contract

New `BaselineForecastV1` artifacts contain the complete `CompetitionRulesV1`
object and include it in their semantic identity. New `EvaluationCorpusV1`
records contain the same object, and `Sprint2EvaluationReportV1` serializes it
with the evaluation corpus.

The PostgreSQL forecast and evaluation registries each persist:

```text
competition_rules_id
competition_rules_sha256
outcome_scope
```

The migration uses `NOT VALID` constraints. Existing immutable rows are not
rewritten; every new row must provide a non-empty rule ID, a SHA-256 checksum,
and one supported outcome scope.

Integration assertions publish and read back all three fields for both a
forecast and an evaluation. Contract tests confirm that the immutable forecast
artifact and evaluation report include the full rules object.

## Result

The current EPL rules record remains:

```text
rules ID: premier-league-epl-2015-16-regulation-v1
outcome scope: REGULATION_TIME
rule SHA-256: ae6701cb613a3ce024bd314de0c86d15312102c8e14a33d4c3efc97b68b129fc
```

```text
CompetitionRulesV1 contract = PASS
Forecast/evaluation outcome-scope binding = PASS
Phase 2B competition-rules evidence = PASS

Sprint 2 = FAIL
Phase 3 = blocked
```
