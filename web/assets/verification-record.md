# MVP frontend verification record

Run 30 September 2026:

- `pnpm lint`: pass.
- `pnpm typecheck`: pass.
- `pnpm test`: 3 tests pass.
- `pnpm build`: pass; routes `/`, `/performance`, `/predictions` generated.
- `pnpm test:e2e`: desktop Chromium and mobile WebKit fixture expansion pass; compact mobile navigation/rail behavior pass; one intentionally inapplicable desktop copy of the mobile-only test is skipped.
- axe-core expanded fixture audit: zero violations in desktop and mobile projects.
- `make check`: 618 Python tests, 15 Rust tests, Go tests, lint, static analysis, builds, and project-status validation pass.
- `make integration`: fresh-database migration/storage invariants and PostgreSQL/Redis/Go service checks pass.
- Fallow 3.30.0: zero code-health findings and zero dead-code/dependency findings; architecture boundaries and policy rule packs are not configured in this repository and therefore were not measured by Fallow.
- `pnpm audit --audit-level=moderate`: no known vulnerabilities after upgrading Vitest to 4.1.11.
- Visual captures: `web/test-results/desktop-expanded.png`, `mobile-expanded.png`, and `mobile-collapsed.png` were inspected locally. Test output is ignored and not a product artifact.

Backend/data verification is recorded in the repository delivery report and command evidence; the live local API returned 1,240 competition rows and 202 real fixtures across 64 competition groups for 2026-09-30.
