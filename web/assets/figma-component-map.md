# Design-to-code map

| Design evidence | Code owner | Decision |
|---|---|---|
| Competition rail and top navigation | `AppShell` | Local shared shell |
| Collapsed fixture row | `FixtureRow` | Local shared fixture component |
| Three-way probability bar | `ProbabilityBar` | Shared; same semantics and geometry |
| Inline expanded overview/tabs | `ExpandedFixture` | Local fixture feature |
| Markets and score matrix | `ExpandedFixture` panels | Local; one current consumer |
| H2H and team statistics | `ExpandedFixture` panels | Local; API-dependent states |
| Analytics tables | `PerformancePage`, `PredictionsPage` | Separate route components |
| Mobile bottom navigation | `AppShell` | Responsive shell variant |

Token values map to `matchforge_analytics/DESIGN.md`. Screenshot HTML confirms
the same slate, emerald, cyan, mono-label, 4 px radius system.
