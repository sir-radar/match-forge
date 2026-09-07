# Testing and Verification

## Goal

Tests must prove required behavior, failure handling, invariants, and compatibility.

Tests do not create requirements for otherwise unnecessary production code.

## TDD

Use red-green-refactor for changed behavior where practical.

### Red

Write or update a focused test first.

Confirm it fails for the intended reason.

### Green

Implement the smallest complete production change satisfying the contract.

### Refactor

Improve structure without altering proven behavior.

### Extend

Add boundary, regression, property, integration, and failure coverage exposed by the implementation.

Tests should normally be committed with the production behavior they prove.

## Testing layers

### Unit tests

Use for:

- football mathematics;
- probability transformations;
- validation;
- metric calculations;
- serialization;
- domain invariants;
- deterministic pure functions.

### Property / invariant tests

Use heavily for:

- probability normalization;
- monotonicity where required by the contract;
- point-in-time eligibility;
- determinism;
- input-order stability;
- artifact round trips;
- count distributions;
- stable ordering;
- algebraic limiting cases.

### Integration tests

Use for:

- PostgreSQL;
- migrations;
- provider adapters;
- point-in-time reconstruction;
- artifact publication;
- forecast registration;
- retry/reconciliation;
- cross-module contracts.

### End-to-end / operator tests

Use for critical workflows such as:

```text
ingest
→ validate
→ build dataset
→ fit
→ forecast
→ evaluate
→ report
```

Do not make external live provider availability a requirement for deterministic tests unless explicitly defined.

## Historical modelling leakage tests

Any implementation affecting historical modelling must test relevant cases:

- future match excluded;
- target match excluded;
- target outcome inaccessible before prediction;
- same-kickoff matches isolated;
- historical corrections obey knowledge time;
- current-state shortcuts cannot enter historical evaluation;
- calibration target excluded;
- feature lookbacks use prior history only.

A confirmed leakage defect is always blocking.

Predictive performance cannot compensate for leakage.

## Model artifact tests

Model artifacts require coverage for:

```text
fit
→ serialize
→ checksum
→ unload
→ reload
→ predict
```

Prediction before/after serialization must satisfy the approved numerical tolerance.

Also test, where relevant:

- missing artifact file;
- corrupt artifact file;
- checksum mismatch;
- unsupported artifact schema;
- unsupported feature/forecast contract;
- concurrent identical fit;
- retry after partial publication;
- existing artifact reuse;
- immutable artifact protection;
- logical state identity;
- physical file identity where required.

## Probability/model tests

For model mathematics, cover as applicable:

- parameter domain boundaries;
- valid limiting cases;
- invalid parameter failures;
- normalization;
- finite outputs;
- probability bounds;
- deterministic fitting;
- optimizer failure;
- non-convergence;
- local stationarity/optimality check where the contract requires it;
- extreme but legal inputs;
- exact tail/support behavior;
- expected marginal/mean/variance identities;
- same-kickoff behavior.

Do not silently repair invalid mathematical states in tests unless the model contract explicitly defines the repair.

## Migration tests

Before changing persistence:

- inspect existing migrations;
- inspect constraints and indexes;
- inspect MatchForge ID behavior;
- inspect point-in-time/bitemporal behavior;
- inspect foreign keys;
- inspect upgrade behavior;
- inspect existing-data expectations.

Add a new migration rather than editing an accepted migration.

Validate relevant migrations against:

- an empty database;
- a previous-phase database, where practical.

Never silently reinterpret an existing timestamp or identifier.

## Concurrency and retry tests

Assume at-least-once execution.

Consider:

- duplicate execution;
- races;
- partial publication;
- ordering;
- idempotency;
- retry recovery.

Artifact and forecast identity should make identical semantic requests converge on one result.

Do not assume exactly-once execution.

## Complexity checks

Use the repository's configured complexity threshold.

If none exists:

```text
target cyclomatic complexity <= 10
per new or materially changed executable unit
```

Complexity above the threshold requires:

1. cohesive decomposition; or
2. concrete technical justification.

Do not:

- disable complexity checks;
- add ignore comments only to pass;
- move tangled branches into meaningless helpers;
- split code mechanically to game metrics.

Decision-heavy code requires branch-oriented tests.

Before completion inspect:

- independent conditions;
- nested conditions;
- state combinations;
- retry branches;
- error branches;
- point-in-time branches;
- duplicate conditions;
- hard-to-reason execution paths.

## Minimal implementation test

Before commit, inspect newly added or materially changed:

- functions;
- methods;
- classes;
- modules;
- configuration keys;
- schema fields;
- branches.

For each, answer:

```text
why does this exist now?
who or what consumes it?
which current task requirement or established contract requires it?
what would fail or become materially worse if it were removed?
```

If the answers are not concrete, remove or simplify the code.

A unit test alone does not justify unused production code.

## Verification order

Prefer:

1. focused tests while implementing;
2. relevant package/module test suite;
3. lint/type/static/complexity checks;
4. integration/migration checks where applicable;
5. repository-wide `make check` or equivalent;
6. phase/evaluation commands only when the current authorization explicitly permits them.

Do not run an authoritative evaluation merely because implementation tests pass.

## Evidence

Record exact commands and actual results.

Never claim:

```text
tests passed
migration succeeded
model reproduced
evaluation passed
```

without executed evidence from the final state.
