# Git Delivery

## Purpose

This document defines the default Git workflow for implementation tasks.

Follow the user's requested delivery mode. Analysis, review, planning, research, or explicitly local-only work does not require automatic commit/push/PR delivery. However, every fresh push of a task branch requires a reviewable PR; later pushes update that PR.

## Startup inspection

Before editing:

```bash
git status --short
git branch --show-current
git log --oneline -n 10
git diff
git diff --cached
```

Determine:

- current branch;
- branch purpose;
- base branch;
- staged work;
- unstaged work;
- relevant untracked files;
- whether existing work belongs to the requested task.

Never:

- reset user work;
- overwrite it;
- reformat it incidentally;
- stash it without authorization;
- include it in unrelated commits;
- rewrite existing commits without authorization.

Use a separate worktree when useful for isolation.

## One concern per branch

Implementation work should use a dedicated task branch unless the user explicitly requests otherwise.

Determine whether the current branch is:

```text
A. the correct existing task branch
B. the repository base branch
C. a branch for unrelated work
```

### Correct existing task branch

Continue on it.

Do not create a second branch merely for naming preference.

### Base branch

Create a dedicated task branch before committing implementation work.

Do not commit feature, fix, refactor, modelling, data, or migration work directly to the base branch unless explicitly requested.

### Unrelated branch

Do not mix tasks.

Create an isolated task branch.

If unrelated uncommitted user changes make switching unsafe, stash them and use a separate branch where practical, then unstash them when new changes are finally pushed.

## Branch naming

Use the repository convention.

Where none exists, prefer:

```text
feat/<short-name>
fix/<short-name>
hotfix/<short-name>
refactor/<short-name>
perf/<short-name>
test/<short-name>
docs/<short-name>
chore/<short-name>
```

## Before every commit

1. Review repository status.
2. Review the full task diff.
3. Review the staged diff.
4. Confirm every staged file belongs to the task.
5. Check new symbols for current consumers or explicit contract reasons.
6. Search for duplicate/superseded implementations.
7. Remove task-introduced dead or obsolete code.
8. Run configured lint, type, static-analysis, complexity, and unused-code checks.
9. Run `git diff --check`.
10. Run focused tests and relevant quality gates.
11. Check for secrets, local files, generated junk, temporary evidence, and debug artifacts.
12. Confirm the diff is the smallest complete implementation.

Do not knowingly commit failing work as complete.

Do not use `--no-verify` without authorization.

Prefer Conventional Commit subjects where consistent with repository practice.

Examples:

```text
feat(forecasting): add point-in-time match dataset
fix(backtest): prevent same-kickoff result leakage
test(calibration): cover chronological fit boundary
docs(governance): document baseline promotion contract
```

## Default implementation delivery

When the user requests implementation delivery and does not opt out of Git delivery, the expected flow is:

```text
implementation
    ↓
verification
    ↓
review final diff
    ↓
commit intended task changes
    ↓
push task branch
    ↓
create or update pull request
    ↓
verify PR title/body match final diff
    ↓
final handoff
```

Once a task branch is pushed for the first time, creating its PR is mandatory. Do not treat pushed changes without a reviewable PR as delivered. Later pushes must update the existing PR.

## Required completion state after a fresh push

Before final handoff:

```text
[ ] Intended task changes are committed.
[ ] No intended task changes remain unstaged.
[ ] No intended task changes remain staged but uncommitted.
[ ] The task branch is pushed.
[ ] The remote contains the final verified commit(s).
[ ] A pull request exists.
[ ] The pull request targets the correct base branch.
[ ] The title reflects the final change.
[ ] The body reflects the final diff.
[ ] Verification evidence is included.
[ ] The PR URL is available for handoff.
```

Unrelated pre-existing user changes may remain.

The requirement is:

```text
every fresh task-branch push
must have a reviewable pull request
```

not:

```text
the entire repository must be globally clean
```

## Delivery blockers

If commit, push, or PR creation is blocked by:

- authentication failure;
- missing remote;
- repository permissions;
- protected branch restrictions;
- unavailable GitHub tooling;
- unresolved conflicts;
- hooks/checks failing for reasons that cannot safely be fixed within task scope;
- unrelated dirty work that cannot safely be isolated;

then:

1. Complete every safe delivery step still possible.
2. Preserve all user work.
3. Report the exact failed command and error.
4. Report which delivery step remains incomplete.
5. Leave task changes in a recoverable, clearly identified branch state.

Do not describe the task as fully delivered when a required delivery step is blocked.

## Pull requests

For every fresh task-branch push:

1. Check whether a PR already exists for the branch.
2. Create a PR against the correct base branch when none exists; otherwise update the existing PR.
3. Ensure title and body describe the final diff.
4. Include actual verification commands and results.
5. Include contract/architecture impact where relevant.
6. Include limitations and out-of-scope work.
7. Update the PR body if later commits materially change the implementation.

Never generate a generic PR description from the task statement without inspecting the final implementation.

If PR creation is blocked after a fresh push, report the push and PR creation failure as a delivery blocker. Do not mark the task as delivered.

Use `docs/engineering/pr-template.md`.

## Final handoff

Report at minimum:

```text
Branch: <branch>
Base branch: <base>
Final commit: <sha> <subject>
Push status: PUSHED | BLOCKED | EXPLICITLY_SKIPPED
PR: <url> | BLOCKED | EXPLICITLY_SKIPPED
Remaining task-related uncommitted changes: NONE | <details>
Unrelated preserved worktree changes: NONE | <details>
```

Also include, when applicable:

- changed modules;
- contract changes;
- tests added or updated;
- exact verification commands and results;
- migration/evaluation/artifact/reproduction evidence;
- known limitations;
- blockers and pre-existing failures.

Never claim a command ran unless it actually ran.
