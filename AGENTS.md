# MatchForge Engineering Agent Guide

## Mission

Implement requested changes completely, correctly, reproducibly, and safely within MatchForge's established architecture.

Every change must preserve:

- correctness;
- point-in-time integrity;
- reproducibility;
- determinism where required;
- source traceability;
- provider neutrality;
- model traceability;
- testability;
- maintainability;
- compatibility;
- narrow scope;
- explicit verification.

Implement the smallest complete change that satisfies the request and existing contracts.

Do not invent requirements, assumptions, provider behavior, schemas, thresholds, abstractions, dependencies, or future-phase features.

Never claim work is complete without evidence from the final repository state.

---

## 1. Sources of Truth

Resolve implementation conflicts in this order unless the repository owner explicitly changes the priority:

1. Current repository-owner requirements and corrections.
2. Applicable `AGENTS.md` files.
3. Resolved owner / Wayfinder decisions and append-only decision events.
4. Approved ADRs, policies, schemas, migrations, and other versioned contracts.
5. `PLAN.md`.
6. Existing intentional tests and implementation evidence.
7. Existing architecture and source behavior.
8. Repository documentation.
9. Official documentation for the exact dependency/tool version.
10. General engineering practice.

Never let generic engineering advice override an explicit MatchForge decision.

If two authoritative sources conflict:

1. Determine which decision is newer.
2. Inspect the relevant Wayfinder decision/event history where applicable.
3. Inspect Git history.
4. Inspect consumers.
5. Inspect tests, schemas, migrations, and persisted compatibility requirements.
6. Determine the compatibility impact.
7. Ask the repository owner only if the conflict remains materially unresolved.

A stale `PLAN.md` checkpoint must not override a newer resolved owner/Wayfinder decision.

---

## 2. Operating Rules

### Investigate first

Before editing:

- inspect repository status and current branch;
- locate applicable `AGENTS.md` files;
- identify the current project status and active Wayfinder map, if any;
- identify the relevant phase, contracts, tests, and directly relevant documentation;
- search for existing implementations before adding new ones;
- determine whether the current branch belongs to this task.

Do not ask for information already available in the repository.

Do not recursively load all documentation or historical evidence by default. Read only what the current task needs. Avoid repeated searches, reads, and tool calls when the answer is already known; run only actions needed to complete or verify the task.

### Preserve user work

Never:

- reset or discard uncommitted user changes;
- overwrite unrelated files;
- reformat unrelated code;
- stash changes without authorization;
- include unrelated work in a commit;
- amend or rewrite commits unless explicitly requested.

If the current worktree cannot safely support the task, use an isolated branch or worktree.

### Keep scope narrow

Do not add speculative:

- abstractions;
- helpers;
- interfaces;
- flags;
- configuration;
- schema fields;
- dependencies;
- fallback paths;
- future-phase scaffolding;
- duplicate implementations.

Every new production symbol must have a current consumer or an explicit contract reason.

Remove task-introduced dead, obsolete, duplicate, debug, placeholder, or commented-out code before commit.

Do not delete unrelated pre-existing code merely because it appears unused.

### Protect quality gates

Never weaken or disable:

- tests;
- assertions;
- validation;
- linting;
- typing;
- static analysis;
- complexity checks;
- migration checks;
- leakage checks;
- reproducibility checks;
- phase gates;
- frozen evaluation criteria.

Do not hide unfinished work behind TODOs, placeholders, skipped checks, suppressed errors, fake implementations, or silent fallbacks.

Correctness and evidence take priority over speed.

---

## 3. Writing and Naming

Write like an experienced engineer communicating with another engineer.

Prefer simple, concrete language over academic, legalistic, consultancy-style, or AI-generated specification prose.

Do not invent abstract terminology such as:

```text
X surface
X substrate
X authority
X evidence layer
X semantic layer
X decision topology
```

unless the repository already defines that exact term and using it is necessary.

Do not invent a new `SomethingV1` contract merely because a concept appears in a ticket. Create a named contract only when it needs a stable machine-readable or code-level interface.

Use repository-defined technical names exactly when they already exist.

Before finalizing prose, ask:

> Would a senior engineer naturally say this during a code review?

If a shorter normal word preserves the technical meaning, use it.

For detailed writing rules and examples, read `docs/engineering/writing-style.md` when producing substantial plans, research, ADRs, PR descriptions, or durable documentation.

---

## 4. Language and Ownership

MatchForge has deliberate language boundaries:

```text
Python  = football data and modelling
Rust    = deterministic high-volume simulation
Go      = serving and operations
SQL     = database schema and persistence
Schemas = cross-language contracts
```

### Python

Python owns:

- provider adapters;
- ingestion and normalization;
- point-in-time reconstruction;
- football features;
- model fitting;
- forecasting;
- calibration;
- walk-forward evaluation;
- analytical reports;
- model artifact creation.

Do not move football modelling into Go or Rust for symmetry.

### Rust

Rust owns:

- pure deterministic simulation;
- Monte Carlo execution;
- simulation-specific numerical performance.

Rust must not own provider ingestion, database access, historical reconstruction, model training, or HTTP serving.

Do not expand the Rust workspace before simulation is authorized.

### Go

Go owns:

- HTTP serving;
- request validation;
- authentication and authorization;
- rate limiting;
- cache coordination;
- job submission;
- health and readiness;
- observability;
- retrieval of generated forecasts.

Go must not reimplement football models.

Do not add prediction endpoints before forecasting contracts are stable.

### SQL

SQL migrations are the sole schema authority.

Use the repository's approved migration mechanism. Do not introduce a competing ORM migration system.

For detailed boundaries and storage ownership, read `docs/architecture.md`.

---

## 5. Phase and Authorization Discipline

MatchForge is phase-gated.

Before implementation, identify:

- current phase;
- requested phase;
- prerequisites;
- unresolved decisions;
- gate status;
- authorized scope;
- active Wayfinder map and ticket, if applicable.

Implementation completion is not phase completion.

A phase is complete only when its required evidence passes, such as:

- acceptance tests;
- leakage checks;
- walk-forward evaluation;
- calibration analysis;
- reproducibility checks;
- artifact validation;
- model-quality gates;
- operator workflow checks.

When a phase gate completes:

1. Produce the required evidence.
2. Record `PASS`, `PASS_WITH_WARNINGS`, or `FAIL`.
3. Stop.
4. Return control to the repository owner before later-phase work begins.

Do not tune thresholds after observing authoritative results.

Do not reopen, reclaim, or mutate tickets from terminal, failed, abandoned, or superseded Wayfinder routes unless a new explicit owner decision authorizes revisiting that work.

Historical tickets may be read as evidence only. Newly authorized work should normally use new tickets in the current route.

---

## 6. Data, Identity, and Time

### Storage ownership

Use the established storage layer for each type of data:

- Raw provider bytes: immutable files or object storage.
- PostgreSQL: structured relational state and registrations.
- Parquet: high-volume analytical data.
- Object storage: immutable model artifacts.
- Redis: cache and ephemeral job state only.

Do not duplicate authoritative data without an explicit reason.

### Identity

Never use mutable names as authoritative identity.

Use stable MatchForge IDs for matches, teams, players, competitions, and seasons.

Provider IDs and names are source details and mapping inputs. They are not MatchForge model keys.

Cross-provider data must not be merged by name similarity alone. Identity mapping must be explicit, deterministic, and traceable.

### Point-in-time integrity

Historical forecasts may use only information legitimately available before the prediction time.

Keep these concepts separate:

```text
football_cutoff
knowledge_cutoff
knowledge_mode
```

Do not replace them with an ambiguous `as_of` field.

Historical queries must not rely on current-state shortcuts such as:

```sql
WHERE known_to IS NULL
```

by themselves, or on "latest" records without an explicit historical contract.

Use separate contracts for:

- historical training labels;
- pre-match forecast context;
- post-prediction outcomes.

The target match's outcomes and post-match statistics must be structurally absent from forecast inputs.

### Same-kickoff matches

When matches could not observe each other's outcomes:

1. Build all forecasts for the time batch.
2. Persist/freeze all forecasts.
3. Reveal outcomes.
4. Update sequential state.

When ordering is uncertain, exclude the observation conservatively.

Any confirmed future-data, target-outcome, or same-batch leakage is blocking regardless of predictive performance.

For detailed temporal/evaluation rules, read `docs/backtesting.md`.

---

## 7. Provider Neutrality

Models consume provider-neutral MatchForge contracts.

Provider adapters may differ in coverage, granularity, terminology, event detail, and update timing.

Do not force providers into a shape they cannot support.

Preserve:

- provider identity;
- provider IDs;
- source snapshots/resources;
- original values;
- mapping decisions;
- quality findings.

Unknown provider values must be surfaced or quarantined according to the quality policy. Do not silently coerce them.

---

## 8. Model Boundaries

Models consume eligible MatchForge inputs. They do not decide which historical facts they are allowed to observe.

Preferred flow:

```text
point-in-time dataset provider
        ↓
eligible MatchForge history
        ↓
model
        ↓
forecast
```

Do not let models query providers or databases for their own history.

Centralize temporal eligibility rather than duplicating it in Elo, Dixon-Coles, corner models, calibrators, or evaluators.

Simple approved baselines remain the benchmark. Complexity must earn its place through compatible leakage-safe out-of-sample evidence.

Related goal probabilities must derive from one coherent joint score distribution.

Reject materially invalid probabilities. Do not silently clip or renormalize invalid distributions unless the approved mathematical contract explicitly defines that behavior.

Bookmaker data remains outside baseline model features unless explicitly authorized.

For detailed artifact, model, evaluation, calibration, and promotion rules, read `docs/model-governance.md`.

---

## 9. Artifacts and Reproducibility

Published fitted artifacts are immutable.

Keep these concepts separate:

```text
fit run
model artifact
human version label
promotion event
forecast
```

Every authoritative artifact must record or resolve the applicable:

- model family;
- algorithm version;
- artifact schema version;
- serializer version;
- configuration;
- training dataset version;
- feature versions;
- football cutoff;
- knowledge cutoff;
- knowledge mode;
- code Git SHA;
- dependency lock hash;
- file checksum;
- logical model-state checksum;
- compatibility declaration.

Prefer transparent portable formats such as JSON or Parquet.

Do not use pickle, joblib, or cloudpickle as the canonical production artifact format.

Corrections create new artifacts. Published bytes, manifests, lineage, and configuration must not change.

A deterministic specification must reproduce the same logical result within the documented numerical tolerance.

Do not claim reproducibility merely because the command can be rerun. Verify the result.

---

## 10. Testing and Complexity

Use red-green-refactor for behavior changes where practical:

1. Write a focused failing test.
2. Implement the smallest complete change.
3. Refactor without changing behavior.
4. Add boundary, regression, property, integration, and failure coverage.

Use the repository's configured cyclomatic complexity threshold.

If no threshold exists, target cyclomatic complexity of 10 or less for new or materially changed executable units.

Do not disable checks, hide branches in meaningless helpers, or split code mechanically to game complexity metrics.

Decision-heavy code requires branch-oriented tests.

Read `docs/engineering/testing.md` for the detailed test matrix, artifact tests, leakage tests, migration tests, concurrency tests, and final verification expectations.

---

## 11. Documentation

Documentation is required for durable changes to:

- architecture;
- public or cross-module contracts;
- data rules;
- storage ownership;
- time/eligibility rules;
- security boundaries;
- provider mapping policy;
- model or evaluation governance;
- operational procedures.

Prefer existing documents. Make the smallest targeted edit that keeps the document accurate; avoid rewriting whole files, duplicating context, or generating extra documents and evidence unless required.

Do not create documentation for ordinary bug fixes, routine refactors, tests, or normal ticket completion.

Prefer executable and machine-readable sources of truth:

```text
schemas/contracts
        ↓
code
        ↓
tests
        ↓
machine-readable evidence
        ↓
human-readable documentation
```

Maintain current project state in the repository's tracked project-status authority, currently `docs/project-status.json` where that contract remains applicable.

Do not scan all historical evidence by default.

---

## 12. Git and Delivery

Use a dedicated task branch unless the user explicitly requests another delivery mode.

If already on the correct task branch, continue there.

If on the base branch, create a task branch using the repository convention.

Do not mix unrelated concerns.

For changes limited to prose documentation (`*.md`, `*.mdx`, or `*.rst`), skip `make check`, integration, build, lint, type, static-analysis, and code-test commands. Review the changed text and run `git diff --check`; run a documentation-specific validator only when the changed document has one. Treat machine-readable contracts and project-status files as code-related for verification. If any code-related file changes, run the applicable checks below.

Before every commit:

1. Review repository status, the complete task diff, and the staged diff.
2. Confirm every staged file belongs to the task.
3. Check new symbols for current consumers or explicit contract reasons.
4. Search for duplicate or superseded implementations.
5. Remove task-introduced dead or obsolete code.
6. Run configured lint, type, static-analysis, and unused-code checks when code-related files changed.
7. Run `git diff --check`.
8. Run focused tests and relevant quality gates when applicable to the changed files.
9. Check for secrets, local files, generated junk, and debug artifacts.
10. Confirm the diff is the smallest complete implementation.

Do not use `--no-verify` without authorization.

Follow repository policy and the user's requested delivery mode.

If the task's delivery mode requires a PR, implementation is not fully delivered until the verified task changes are committed, pushed, and represented by a reviewable PR.

Never claim a command ran unless it actually ran.

For the complete branch, commit, push, PR, blocker, and handoff procedure, read `docs/engineering/git-delivery.md`.

For PR structure, read `docs/engineering/pr-template.md`.

---

## 13. Completion

Do not declare completion until applicable items are true:

- requested behavior is implemented;
- contracts and architecture are respected;
- point-in-time integrity is preserved;
- failure paths are handled;
- relevant tests pass;
- quality gates pass;
- complexity is acceptable;
- no task-introduced dead, duplicate, speculative, placeholder, or obsolete code remains;
- migrations are validated where applicable;
- artifacts and reproducibility are validated where applicable;
- documentation is updated where required;
- the final diff contains no unrelated work;
- final Git status is understood;
- required delivery steps are complete or explicitly blocked.

Never claim "tests passed", "migration succeeded", "model reproduced", or "evaluation passed" without evidence.

Before final handoff on substantial engineering work, use `docs/engineering/review-checklist.md`.

---

## 14. Wayfinder Maps

When working from a Wayfinder map, track the whole current map, not only the current ticket.

After each implementation ticket, report one of:

```text
Wayfinder map: IN PROGRESS
Wayfinder map: BLOCKED
Wayfinder map: COMPLETE
```

Before reporting `COMPLETE`, verify:

- the map destination;
- all tickets in the map;
- authorized implementation scope;
- remaining open or blocked work;
- frozen requirements;
- acceptance tests;
- required evidence and reports;
- repository checks;
- whether remaining blockers are inside or outside the map.

If the map is incomplete, report:

```text
WAYFINDER MAP IMPLEMENTATION NOT COMPLETE

Blocker:
<exact blocker>

Next required action:
<exact action>
```

If all implementation work and acceptance requirements are complete, report:

```text
WAYFINDER MAP IMPLEMENTATION COMPLETE
```

Then include:

```text
Map:
<map name or destination>

Status:
COMPLETE

Delivered:
- ...

Verification:
- ...

Acceptance evidence:
- ...

Remaining work inside this map:
NONE
```

After reporting map completion, stop.

Do not begin another map, phase, ticket, provider route, refactor, cleanup, or enhancement without repository-owner authorization.

A completed map is an owner handoff point, not permission to start the next logical task.

---

## 15. Model Routing

Use the lowest-cost model that can safely complete the work.

- `L1 / Luna`: bounded, mechanical, low-risk work.
- `L2 / Terra`: normal production engineering requiring judgment.
- `L3 / Sol`: architecture, statistical correctness, historical correctness, governance, security, or difficult concurrency.

Default implementation model:

```text
gpt-5.6-terra
```

Before substantial work, classify the task using `docs/engineering/model-routing.md`.

Route work to `L3 / Sol` when it affects:

- model mathematics;
- point-in-time or knowledge-time rules;
- historical leakage;
- same-kickoff batching;
- authoritative evaluation;
- phase gates or thresholds;
- model promotion/governance;
- MatchForge identity resolution;
- bitemporal behavior;
- immutable artifact or forecast identity;
- security-sensitive architecture;
- difficult concurrency or transaction correctness.

Model escalation does not authorize scope expansion.

---

## Core Principles

```text
Raw source is immutable.
Identity is provider-neutral.
Historical forecasts are point-in-time safe.
Target outcomes stay sealed until prediction.
Models do not choose their own historical universe.
Related probabilities come from one coherent distribution.
Artifacts are immutable.
Forecasts bind exact artifacts.
Raw probabilities are never overwritten.
Calibration uses prior out-of-sample predictions only.
Retries converge.
Lineage reaches the source.
Evaluation is chronological.
Simple baselines remain the benchmark.
Complexity must earn its place.
Every production abstraction must earn its place.
Task-introduced obsolete code is removed.
Phase gates are real gates.
Wayfinder completion returns control to the owner.
Evidence is required for completion.
```

## Supporting Documents

Load these only when relevant to the current task:

```text
docs/architecture.md
docs/backtesting.md
docs/model-governance.md
docs/engineering/git-delivery.md
docs/engineering/model-routing.md
docs/engineering/pr-template.md
docs/engineering/review-checklist.md
docs/engineering/testing.md
docs/engineering/writing-style.md
```
