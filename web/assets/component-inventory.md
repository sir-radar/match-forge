# Component inventory

Pre-existing production components were audited: `AppShell`, `FixtureExplorer`,
`FixtureRow`, `ExpandedFixture`, `ProbabilityBar`, resource states, performance,
predictions, and admin sync.

- Extended `AppShell` for approved navigation, search, timezone, feed state,
  exact logo, footer, and mobile navigation.
- Extended fixture components for competition rail, dense workbench, filters,
  and distinct mobile geometry.
- Extended `ExpandedFixture` for all authored tabs and API-backed panels.
- Reused `ProbabilityBar`; semantics and three-way geometry match.
- Added one shared typed `Icon` primitive for shell and fixture glyphs. Inline
  SVG removes the runtime Material Symbols font dependency.
- Kept performance and predictions route-local using shared approved tokens.
- Added one route-local `BackToTop` control owned by `AppShell`; it reuses the
  shared `Icon` primitive and is rendered only for `/`.
- Kept performance pagination inside `PerformancePage`; its native select and
  buttons have no second consumer or shared-component contract.

No public component API changed. Duplicate search found one owner per role.
