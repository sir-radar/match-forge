# UI state matrix

| Surface | Implemented states |
| --- | --- |
| Fixtures | loading, empty, unavailable forecast, failure/retry, retained refresh, status/team/data filters, success |
| Expanded overview | loading, missing forecast, partial context, independent failures, success |
| Markets / score matrix | missing forecast, malformed rejection, complete API display |
| H2H / team statistics | loading, no history, missing statistics, partial, success |
| Simulation evidence | explicit unavailable; no public validation artifact |
| Diagnostics | explicit research-only restriction |
| Forecast history | explicit unavailable; no public revision list |
| Performance | loading, empty, `UNRATED`, partial metrics, failure/retry, success |
| External predictions | loading, empty, source-only partial, isolated failures, success |

Desktop and purpose-built mobile layouts cover fixture states. Abort signals and
generation guards enforce last-choice-wins for date/filter changes.
