# Admin data-sync component decision

`DataSyncAdmin` remains local to the admin route. Promoting its action, status, coverage, or audit-row pieces to shared ownership would add APIs without a second consumer. `AppShell` receives one additive navigation link; existing semantics, focus order, and responsive breakpoint remain unchanged.

Action cards own native buttons and disabled/busy states. Advanced filters and run details use native `details`/`summary`. Tables retain captions and row headers. No custom composite widget is introduced.
