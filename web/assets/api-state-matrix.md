# API state matrix

| Resource | Loading | Success | Empty | Partial | Invalid | Failure | Retry | Stale response |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Competitions | Yes | Yes | Yes | Yes | Rejected | Scoped | Yes | Aborted |
| Fixtures | Yes | Yes | Yes | Yes | Rejected | Scoped | Yes | Aborted |
| Forecast | Yes | Yes | Unavailable | Yes | Rejected | Scoped | Yes | Aborted |
| Match context | Yes | Yes | Explicit gaps | Yes | Rejected | Scoped | Yes | Aborted |
| Performance | Yes | Yes | UNRATED | Yes | Rejected | Scoped | Yes | Aborted |
| External predictions | Yes | Yes | Yes | Yes | Rejected | Scoped | Yes | Aborted |

Every request key contains all filters. Effects abort superseded requests;
aborts do not replace valid content with an error. Independent expanded-match
resources fail without hiding the fixture row or forecast summary.
