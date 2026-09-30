# Fallow remediation record

Run 30 September 2026 with Fallow 3.30.0 against the complete dirty MVP worktree and again from `web/` after remediation.

Commands:

```text
FALLOW_AGENT_SOURCE=codex pnpm dlx fallow --format json --quiet --explain
npm_config_offline=true FALLOW_AGENT_SOURCE=codex pnpm dlx fallow@3.30.0 --format json --quiet --explain
```

Initial findings were three unused exports and four frontend complexity findings. The exports were removed. Fixture, expanded-match, performance, and prediction composition was split by responsibility without changing behavior. The final web analysis covered 38 files and 200 functions and reported zero health findings, unused files, unused exports, unused dependencies, unresolved imports, circular dependencies, duplicate exports, or framework contract findings.

Fallow reported that repository architecture boundaries and policy rule packs are not configured. Their zero violation counts are not treated as measured passes. MatchForge's existing language and ownership boundaries were reviewed manually against the final diff and by the repository lint/type/test/build gates.

No automated remediation was applied. Final validation: `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build`, Playwright/axe, `make check`, and `make integration` pass.

The staged-diff security scan reported seven medium SSRF candidates in `web/lib/api.ts`. They are manually closed as not exploitable SSRF: the code runs in the browser, the origin is a deployment-controlled `NEXT_PUBLIC_API_BASE_URL`, every path is a code-owned `/v1/...` route, and all user filter values are encoded with `URLSearchParams`. No request URL accepts a user-controlled origin or raw path. The root scan also lacked root `node_modules`; the frontend-specific scan used `web/node_modules`. Security-sink enforcement is advisory in the repository's current Fallow configuration.
