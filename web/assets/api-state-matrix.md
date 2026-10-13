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
