# Frontend design-port verification record

Run 1 October 2026:

- `pnpm lint`: pass.
- `pnpm typecheck`: pass.
- `pnpm test`: 3 files and 5 tests pass.
- `pnpm build`: pass; routes `/`, `/admin/data-sync`,
  `/performance`, and `/predictions` generated.
- `pnpm test:e2e`: 10 pass and 2 intentionally viewport-inapplicable tests
  skip across configured desktop and mobile projects.
- axe-core: zero violations on fixtures, performance, predictions, and admin
  journeys in both configured viewport projects.
- Fallow 3.31.0: zero dead-code, dependency, duplicate, or framework-contract
  findings. Advisory pre-existing complexity findings are documented in
  `fallow-remediation-record.md`.
- Visual captures for fixtures, performance, and predictions were generated and
  inspected locally. `web/test-results` is ignored test output.

Run 3 October 2026 for the external-prediction redesign:

- `pnpm test`: 4 files and 10 tests pass, including all nine selected-day rows
  rendered without pagination.
- `pnpm typecheck`: pass.
- `pnpm lint`: pass.
- `pnpm build`: pass; `/predictions` generated.
- `pnpm exec playwright test e2e/design-routes.spec.ts --project=desktop --project=mobile`:
  4 pass; predictions has zero axe-core violations in both projects; exact-date
  request, previous-day navigation, full daily table, and no-pagination
  assertions pass.
- Desktop 1187×1600 and mobile full-page captures generated and inspected.
- Fallow 3.31.0: zero dead-code, dependency, duplicate, or framework-contract
  findings; no task-introduced complexity finding remains. The frontend health
  command still fails on three documented pre-existing functions outside this
  change.
