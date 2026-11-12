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

### Experimental V4 database selection

Experimental acquisition, normalization, backfills and model research must use a
new disposable or explicitly retained shadow database. Reuse the repository's
`createdb`/Goose provisioning convention; never migrate the operating database
for an experiment. Keep the original operating URL available as the reference.

On the newly provisioned target only, its database owner records the intended
role with `ALTER DATABASE "new_database" SET matchforge.database_role='experimental'`.
This is database metadata, not a schema migration or an observation disposition.
Never mark the operating database. The guard independently compares actual
PostgreSQL system identifiers and database OIDs, so even a marked target cannot
equal the supplied operating reference. The connection account needs permission
to read `pg_control_system()`; unverifiable identity fails closed.

Export `.env` once, load `scripts/toolchain.sh`, and supply both explicit URLs.
`V4_TARGET_DATABASE_URL` below is a shell variable for that newly provisioned
database, not a default or a new `.env` configuration field:

```sh
uv run --locked python -m football.storage.experimental \
  --database-url "$V4_TARGET_DATABASE_URL" \
  --operating-database-url "$DATABASE_URL" -- \
  uv run --locked python path/to/experimental_phase.py
```

The launcher checks isolation before starting the child, logs credential-free
database identity, and pins both `DATABASE_URL` and `FOOTBALL_DATABASE_URL` to the
verified endpoint. It rejects service/session overrides, multiple endpoints,
missing connection coordinates and routing `PG*` variables; it removes `PG*`
defaults from the child. Phase scripts must consume those supplied URLs, preserve
the existing quota/work owners, and must not reload `.env` or pass an independent
database URL inside the child. Python callers may instead use
`football.storage.experimental.experimental_connection(target, operating)` and
perform all work through that verified connection. This guards database choice;
it does not sandbox arbitrary code or authorize scientific evaluations, model
promotion or Architecture V2 cutover.

The observation `store` CLI and normalization CLI with `--persist` require the
same two explicit URL arguments and perform this check themselves. Read-only
normalization replay still supports `DATABASE_URL`. Historical V4 local publisher
scripts and their original invocations are audit evidence, not approved launch
instructions; reruns must use the guarded launcher and an isolated target.
Normal operational provider sync retains its existing operating behavior.

`scripts/storage-integration.sh` includes the isolation and development-eligibility
regressions. Its databases and the additional databases created by those tests
are disposable. Role markers used by tests are written only to their own targets.

### Managed disposable rehearsal databases

Use the storage lifecycle fixture launcher for new dated/ad-hoc disposable databases;
see [storage lifecycle operations](operations/storage-lifecycle.md). It requires an
active producing-job lease, capacity admission and explicit fixture inputs, records
ownership and tears down only the newly created target after success or failure.
It does not adopt old databases or authorize acquisition or evaluation. Keep unique
source bytes and durable evidence outside disposable targets. Existing integration
and backup restore helpers retain their scoped teardown and recovery checks.

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

#### Database isolation

Integration tests run only through `make integration` (`scripts/storage-integration.sh`
and `scripts/integration.sh`). Between 29 August and 5 September 2026 test runs
committed 158 synthetic registrations into the operating database: nothing stopped a
run whose `TEST_DATABASE_URL` or `DATABASE_URL` named it. See
[recovery-scope dispositions](recovery.md#recovery-scope-dispositions).

`tests/integration/database_isolation.py` now enforces isolation by identity, not name:

- The harness creates a database, stores the SHA-256 of a per-run token as its comment
  and passes the token in the environment. It refuses to mark a database that already
  holds a `football` schema or a comment.
- `tests/integration/conftest.py` stops the run with a usage error before any test
  module is imported unless both URLs reach this run's marked database. It then checks
  every psycopg connection, in the test process and in Python child processes, by
  `pg_control_system().system_identifier` and database OID. A database that registers
  itself in `football.storage_protections` as `AUTHORITATIVE_OPERATING_DATABASE` is
  always refused, even when it carries the marker. The one exception is the exact
  database `prepare` marked (`MATCHFORGE_PREPARED_TEST_DATABASE_IDENTITY`): storage tests
  run `VerifyAuthority` against it, which records it as authoritative in its own
  registry, and `prepare` had already proved it fresh. A copied marker on any other
  database is still refused. A pre-existing unmarked database with
  a `football` schema, an unverified cluster or an unreadable identity is refused too.
- A database a test creates is tagged with the run's ownership comment on first
  connection. Harness cleanup drops every database carrying this run's marker or tag,
  so an interrupted run does not leave test databases behind.

`tests/integration/test_database_isolation.py` proves that the whole suite refuses to
start against a simulated authoritative database and writes nothing to it.
`tests/test_database_isolation.py` fails when an integration test file is not listed
in the harness, because CI would then never run it.

Go integration tests read `TEST_DATABASE_URL` only, and only through
`go/api/internal/testdb`. It applies the same identity rule as the Python guard and fails
the test, rather than skipping it, when the URL is set but the harness environment or the
database marker is missing, so `TEST_DATABASE_URL=… go test ./...` cannot reach the
operating database. It also puts the Python guard on `PYTHONPATH` for the CLI and
worker processes those tests start. The harness additionally verifies the URL with
`python -m tests.integration.database_isolation verify` before Go tests start.

Lease-expiry tests do not wait out very short wall-clock leases. A 30 ms lease can expire
inside `claim_history_work` itself (its `lock_work` re-check runs after the queue detail
lock), which made those tests fail only under full-suite load. They claim with a normal
lease and move `lease_until` into the past, so the production comparison with
`clock_timestamp()` is still what decides expiry.

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
