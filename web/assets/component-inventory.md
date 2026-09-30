# Component inventory

No production frontend or component library existed before this branch.
`web/ui-designs` contains static reference HTML only.

Local owners:

- `AppShell`: responsive header, desktop competition rail, mobile navigation.
- `FixtureExplorer`: date and coverage filters, request state, fixture groups.
- `FixtureRow`: compact desktop/mobile fixture disclosure.
- `ExpandedFixture`: tab state and independent context/forecast resources.
- `ProbabilityBar`: shared 1X2 distribution geometry.
- `PerformancePage` and `PredictionsPage`: analytics-style tables.

Shared visual tokens live in `app/globals.css`; domain behavior stays in the
feature components. No public package API changes.
