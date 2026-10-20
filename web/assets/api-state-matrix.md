# API state matrix

| Resource | Loading | Success | Empty | Partial | Invalid | Failure | Retry | Stale response |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Competitions | Yes | Yes | Yes | Yes | Rejected | Scoped | Yes | Aborted |
| Fixtures | Yes | Yes | Yes | Yes | Rejected | Scoped | Yes | Aborted |
| Forecast | Yes | Yes | Unavailable | Yes | Rejected | Scoped | Yes | Aborted |
| Match context | Yes | Yes | Explicit gaps | Yes | Rejected | Scoped | Yes | Aborted |
| Performance | Yes | Yes | UNRATED | Yes | Rejected | Scoped | Yes | Aborted |
| External predictions, exact day | Yes | Yes | Yes | Yes | Rejected | Scoped | Yes | Aborted |

Every request key contains all filters. Effects abort superseded requests;
aborts do not replace valid content with an error. Independent expanded-match
resources fail without hiding the fixture row or forecast summary.

The predictions table always sends one exact `date`. Source metrics send that
same value as both `date_from` and `date_to`. A response-side guard excludes any
record whose `prediction_date` differs from the selected day.

## Forecast score buckets

| State | Treatment | Evidence |
| --- | --- | --- |
| New labeled payload | Display exact scores and aggregated `5+` categories distinctly | versioned tail-bucket component test |
| Historical compact payload | Explicit known-model legacy normalization preserves `5+` meaning | legacy tail-bucket component test |
| Unknown version or contradictory labels | Reject at transport boundary; existing scoped error and retry | malformed contract tests |
| Unavailable forecast / partial context | Existing unavailable state; other resources remain independent | fixture and context component tests |
| Loading, refresh, cancellation, stale response | Existing `useResource` behavior; no new requests or mutations | resource hook tests |

## Provider history admin states

Scope: additional eligibility metrics on the existing `/v1/admin/sync-runs` response.

| State | Treatment | Evidence |
| --- | --- | --- |
| Success / zero counts | Render backend counts, distinguish linked observations from verified matches | `data-sync-admin.test.tsx`, `data-sync.spec.ts` |
| Provisional / quarantined / insufficient history | Separate counts and explanation; never imply import means forecast eligibility | `admin_sync.go`, `data-sync-admin.tsx` |
| Malformed or missing metrics | Boundary rejects response; actionable alert and retry, no invented zeroes | malformed eligibility test |
| Loading / slow | Existing loading state, polling continues independently of ingestion | existing admin component |
| Network / HTTP failure | Existing alert and local status retry | actionable API errors test |
| Duplicate mutation | Disable bulk submission while active; independent live lanes remain available | duplicate-submission and operational-lane tests |
| Cancellation / retry | Existing stop and retry workflow | component and browser tests |
| Optimistic rollback | Not applicable: operations reconcile server responses; no optimistic metric writes | `data-sync-admin.tsx` |
| Query-choice races / offline cache | Not applicable to this change: fixed status endpoint, no new selectors or cache | `data-sync-admin.tsx` |

Performance policy/horizon metadata is mandatory and validated. Horizon changes
use the existing cancellation and stale-response handling. Unknown metadata
produces the scoped error/retry state; empty populations retain nullable metrics.

## R8 date, revision and job states

| State | Treatment | Evidence |
| --- | --- | --- |
| Cleared/invalid fixture date | Keep last valid request and show validation alert | component/date tests and production browser test |
| Initial civil day / hydration | Server prop in configured timezone; deterministic selected-day label | timezone/DST unit tests and SSR/browser comparison |
| Changed-key slow/reordered response | Hide old-key data immediately; abort and generation guard | hook and delayed-day browser regressions |
| Same-key refresh | Retain known data with refreshing state | hook regression |
| Forecast history loading / empty / error | Independent state with scoped retry | revision component tests |
| Selected/current revisions | Original probabilities and complete lineage; local selection only | component and keyboard/browser history tests |
| Malformed revision / wrong fixture | Reject at transport boundary | revision contract tests |
| Bulk and provider lanes active together | Disable only corresponding lane; separate stop/retry | hook and admin component tests |
| Delayed RUNNING after terminal / slow poll | Terminal precedence; no overlapping polls; cleanup aborts | controlled-request hook regressions |
| Optimistic rollback | Not applicable: job state is reconciled from durable server responses | admin hook |

## Architecture V2 frontend boundary

| State | Treatment | Evidence |
| --- | --- | --- |
| Duplicate canonical fixture or competition ID | Reject the response; retain same-key rows and show refresh failure | contract and fixture component tests |
| Separate match IDs with identical teams and kickoff | Preserve both rows; identity is never inferred from display fields | contract, representative component and browser tests |
| Representative replacement | Replace the response array under canonical IDs through polling, navigation and reload | Europa League, Conference League and Botola Pro regressions |
| Wrong fixture, forecast revision or competition response | Reject at the request boundary; scope the error to that resource | API identity tests |
| Unknown canonical status or malformed display timestamp | Reject before date formatting or status controls | contract and API tests; SQL/OpenAPI drift test |
| Same forecast ID with a refreshed summary object | Keep the existing immutable forecast request | controlled component regression |
| New forecast revision / late old response | Change the resource key, abort old request and reject stale completion | controlled component and resource hook regressions |
| Same-key fixture polling failure | Show retained rows plus an alert and local Retry button | component regression |
| Date change followed by failure | Clear previous-date rows and show scoped error | component and delayed-day browser regressions |
| Missing analytical read report / HTTP 503 | Explicit resource failure; independent forecasts and fixture summaries remain visible | API and component regressions |
| Live request failure | Show local error and retry without a perpetual loading indicator | component regression |
| Simulation evidence | Explicitly unavailable until the API exposes a linked approved artifact; no inferred validation | existing expanded-fixture tab |

Product requests remain read-only. Presentation filters and selected tabs stay
local; no additional server-state store or optimistic mutation is introduced.
