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
- Kept performance and predictions route-local using shared approved tokens.

No public component API changed. Duplicate search found one owner per role.
