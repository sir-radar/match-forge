# Fallow remediation record

Run 1 October 2026 with Fallow 3.31.0 against the complete task worktree and
again from `web/`.

Commands:

```text
FALLOW_AGENT_SOURCE=codex fallow --format json --quiet --explain
git diff --cached --unified=0 | FALLOW_AGENT_SOURCE=codex fallow security --diff-file - --format json --quiet
```

The final frontend analysis reported zero dead-code, dependency, duplicate, or
framework-contract findings. Its advisory health gate reports one CRAP finding
for the pre-existing `PerformancePage` function because Fallow has no direct
unit-coverage mapping for it; this task adds deterministic desktop and mobile
route tests for that page. The unrelated pre-existing `DataSyncAdmin`
cognitive-complexity advisory is outside this task.

Fallow reported that repository architecture boundaries and policy rule packs are not configured. Their zero violation counts are not treated as measured passes. MatchForge's existing language and ownership boundaries were reviewed manually against the final diff and by the repository lint/type/test/build gates.

No automated remediation or suppression was applied. Final validation:
`pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build`, and
Playwright/axe pass.

The staged-diff security scan covered all 265 added lines and reported no
security findings or unresolved-edge files. It reported 127 unresolved callee
sites (25 sampled), all ordinary dynamic JavaScript/React method dispatch in
the changed components and Playwright test. The root scan lacked
`node_modules`; the frontend-specific full scan used `web/node_modules`.
Security-sink enforcement is advisory in the repository's current Fallow
configuration.
