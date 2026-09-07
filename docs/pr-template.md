# Pull Request Template

Use this structure for substantial MatchForge pull requests. Omit sections that are genuinely not applicable rather than filling them with boilerplate.

## Summary

Describe the final behavior change in a few concrete sentences.

## Why

Explain why the change is needed.

Reference, where available:

- task/issue;
- `PLAN.md` phase or milestone;
- resolved owner/Wayfinder decision;
- bug/reproduction;
- architecture requirement.

## What Changed

Group by responsibility, not just filenames.

### <Area / Module>

- What was added.
- What changed.
- What was removed.
- Important behavior.
- Important invariants.

## Architecture / Contract Impact

Explain any effect on:

- module ownership;
- dependency direction;
- schemas/contracts;
- point-in-time rules;
- provider contracts;
- forecast contracts;
- artifact contracts;
- public/cross-module interfaces.

If none:

```text
N/A — implementation remains within existing contracts.
```

## Data and Point-in-Time Safety

For modelling, ingestion, feature, or evaluation changes, explain:

- football cutoff behavior;
- knowledge cutoff behavior;
- target-match isolation;
- same-kickoff behavior;
- leakage protections;
- source traceability.

If not applicable:

```text
N/A — no historical or point-in-time data path changed.
```

## Model / Statistical Changes

For modelling PRs, document:

- model family;
- mathematical behavior changed;
- parameters/configuration;
- probability behavior;
- assumptions;
- numerical tolerances;
- whether expected predictions intentionally changed.

If not applicable:

```text
N/A — no model mathematics changed.
```

## Persistence / Migrations

Describe:

- migrations added;
- constraints/indexes added;
- upgrade behavior;
- compatibility implications;
- rollback/reconciliation considerations.

If none:

```text
N/A — no persistence changes.
```

## Artifact / Serialization Impact

Describe changes to:

- model artifacts;
- manifests;
- serialization;
- checksums;
- reproducibility;
- compatibility versions.

If none:

```text
N/A — no artifact contract changed.
```

## Backward Compatibility

State:

- whether existing callers remain compatible;
- whether adapters were added;
- whether an old path is deprecated;
- whether a breaking change exists;
- how consumers were migrated.

## Tests Added or Updated

List meaningful coverage, such as:

- unit tests;
- property/invariant tests;
- integration tests;
- migration tests;
- leakage tests;
- serialization round-trip tests;
- deterministic/reproducibility tests;
- concurrency/retry tests.

Explain what the tests prove.

## Verification Performed

List exact commands actually executed and actual outcomes.

Example:

```text
make check
PASS

uv run pytest tests/models/test_elo.py
18 passed
```

Never include a command that did not run.

## Evidence / Generated Artifacts

List relevant durable evidence, where applicable:

- evaluation reports;
- validation reports;
- manifests;
- fixture output;
- benchmark output;
- model hashes;
- recovery proof.

Do not add transient evidence documents merely to fill this section.

## Risks and Limitations

Document known limitations, such as:

- retrospective knowledge-time limitation;
- provider coverage;
- sparse calibration support;
- intentionally deferred behavior;
- numerical assumptions.

Do not hide known limitations.

## Out of Scope

State important work intentionally excluded.

Do not invent speculative follow-up work.

## Checklist

- [ ] Scope matches the requested task.
- [ ] No unrelated files are included.
- [ ] Relevant tests were added/updated.
- [ ] Relevant tests pass.
- [ ] Lint/format/type/static checks pass.
- [ ] Complexity requirements pass.
- [ ] Minimality/dead-code review passed.
- [ ] No task-introduced unused, duplicate, speculative, placeholder, or superseded code remains.
- [ ] Point-in-time/leakage checks pass where applicable.
- [ ] Migrations were validated where applicable.
- [ ] Serialization/reproduction checks pass where applicable.
- [ ] Documentation was updated where required.
- [ ] No quality gate was weakened.
- [ ] No placeholder implementation remains.
- [ ] PR body matches the final diff.
