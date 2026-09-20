# StatsBomb La Liga lifecycle-publication scope correction — 2026-09-09

## Result

```text
STATSBOMB_LALIGA_LIFECYCLE_SCOPE_VERIFIED
```

The correction adds an explicit immutable lifecycle-publication route:

```bash
football resolve lifecycle \
  --dataset-version 670662d6-6ed7-5fa1-ba3c-1cfd561e524f \
  --source-snapshot 01a08471-f763-7787-80ca-4293316b7e44
```

`football resolve sprint2-lifecycle` remains a separate, fixed Sprint 2/EPL
wrapper.

## Correction

The earlier requalification record said that all four `Half End` events were
in period 2. Retained source evidence establishes four total events per match:
two in period 1 and two in period 2. The production predicate was already
correct and remains unchanged:

```text
provider_event_type = 'Half End' AND period = 2
count == 2
max(period) == 2
```

The actual blocker was that no explicit immutable La Liga dataset/source scope
could invoke the existing v1 publisher. La Liga lifecycle publication had not
previously been attempted.

## Published immutable scope

```text
Base SHA:              72361cabedfaff850ee8ff73c32e97eadb8c7499
Implementation SHA:    uncommitted bounded correction on the base SHA
Dataset version:       670662d6-6ed7-5fa1-ba3c-1cfd561e524f
Source snapshot:       01a08471-f763-7787-80ca-4293316b7e44
Lifecycle contract:    statsbomb-terminal-event-score-v1
Validator run:         1780ec10-300c-5de0-90f5-df6acabea4eb
```

The route accepts only the supplied published normalized StatsBomb event
dataset, its exact source snapshot, exactly one usable validator-v3 result,
one canonical season represented by registered event files, and exact
match/source/file lineage. Unknown dataset IDs, unknown source snapshots, and
dataset/snapshot mismatches fail before any claim is written.

## Eligibility and publication

A read-only query against the published dataset applied the unchanged v1
preconditions before publication:

| Check | Count |
| --- | ---: |
| Canonical matches | 380 |
| Lifecycle eligible | 380 |
| Rejected: terminal count | 0 |
| Rejected: maximum period | 0 |
| Rejected: event-resource lineage | 0 |
| Rejected: scored observation | 0 |

Publication created 380 `completed` lifecycle claims. A second identical
command returned `verified_existing` with 380 claims. Stored-claim checks found
380 distinct matches, 380 exact v1 terminal/count/period/dataset/snapshot
bindings, and 380 claim scores equal to their bound scored observations.

```text
Lifecycle determinism: PASS
Lifecycle idempotence: PASS
```

No source, normalized event file, provider event ID, event index, related-event
relationship, event order, source snapshot, or dataset version was modified.

## Verification

```text
Focused explicit-scope lifecycle integration test: PASS
Fresh-database storage and lifecycle integration suite: PASS (84 tests)
CLI parser tests: PASS (13 tests)
Lint: PASS
Type checks: PASS
make check: PASS
```

## Point-in-time qualification boundary

The lifecycle blocker is resolved. The direct prerequisite check found zero
La Liga kickoff claims and zero La Liga corner labels. The existing
point-in-time provider requires those immutable records in addition to lifecycle
claims, so the full qualification cannot yet pass under this lifecycle-only
authorization:

```text
POINT_IN_TIME_SUITABILITY: FAIL
First remaining blocker: MISSING_LALIGA_KICKOFF_CLAIMS
Additional required record: MISSING_LALIGA_CORNER_LABELS
```

No kickoff or corner publication scope was added, and no diagnostic/model work,
protected EPL outcome access, admission reuse, shared-pace admission, DCv3
diagnostics, candidate fitting, authoritative Sprint 2 evaluation, model
promotion, or Phase 3 work was performed.
