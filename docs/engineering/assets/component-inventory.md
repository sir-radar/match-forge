# Admin data-sync component inventory

| Existing item | Decision | Evidence |
|---|---|---|
| `AppShell` | Extend navigation only | Owns desktop and mobile primary navigation. Existing structure and accessibility names preserved. |
| `.page`, `.page-heading`, `.table-scroll` | Reuse | Existing app layout, heading, and responsive table contracts match. |
| `ResourceError` / `ResourceLoading` | Local equivalent | Admin needs mutation-specific retry and retained action controls; changing shared resource API would add one-off behavior. |
| Fixture/performance panels | Do not reuse | Different semantics and interaction state. |
| `DataSyncAdmin` | Create locally | One operational owner; no second stable consumer. |

No new shared primitive or public component API was added. Existing color, spacing, focus, reduced-motion, and forced-color tokens remain authoritative.
