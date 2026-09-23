# Phase 3A provider qualification execution plan — 2026-09-23

Status: `OWNER_APPROVED_BOUNDARY`; engineering work remains ticket-gated.

This plan applies
`REVISE_PROVIDER_QUALIFICATION_CANCEL_INQUIRIES_V1`. It supersedes the
unexecuted communication route without changing earlier evidence or frozen
Evaluation V2 decisions.

## Two separate lanes

| Requirement | Ordinary private research and development | Qualified Evaluation V2 |
| --- | --- | --- |
| Permission | Published terms must explicitly permit the exact access and use. Ambiguous activities are excluded. | Same, plus immutable internal retention and evidence use must be explicitly permitted. |
| API calls | Only a separately approved endpoint/request budget; sanitize outputs and keep secrets out of logs. | Same; calls must produce a complete frozen qualification record. |
| Source completeness | Samples and contract fixtures may establish schema behavior, but claims remain bounded to what was checked. | Every selected match and shot must pass the frozen coverage rules. |
| xG identity | Unknown model/version is allowed only for labelled exploration that makes no cross-season or benchmark claim. | One identified provider/model/version series must be shown compatible for every admitted group. No silent mixing. |
| Retention | If terms do not clearly allow raw retention, process in memory and retain only non-reconstructive sanitized summaries. | Exact raw bytes, acquisition metadata, hashes, corrections, and replay lineage must be retainable. |
| Outputs | `EXPERIMENTAL_ONLY`; no production, promotion, or Evaluation V2 claim. | Frozen manifest and owner-approved authoritative run only. |
| Simulation | Existing authorized Rust route only, with immutable inputs, fixed seeds, and experimental labelling. | Mandatory Rust policy remains unchanged and is distinct from predictive acceptance. |

Published access is not an unrestricted grant. An unknown term blocks only the
activity that depends on it; it does not automatically block synthetic contract
tests, documentation, or other clearly permitted work.

## Published-terms disposition

| Provider | Resolved from published terms | Still excluded |
| --- | --- | --- |
| PitchAPI | Its documentation and issued key support bounded read-only endpoint verification under a separately approved request budget. | No published governing terms were found for raw retention, reuse, attribution, upstream rights, or post-access use. Do not persist raw responses or use it for Evaluation V2. |
| API-Football | The [terms](https://www.api-football.com/terms) permit use of the service to build projects, prohibit direct resale/account sharing, define plan quotas, and disclaim guaranteed coverage. Bounded private technical checks within the account limit are supportable. | The service grants no publication license and does not expressly settle permanent raw-response retention or upstream rights. Keep any future check in memory and retain only sanitized summaries unless published terms change. |
| football-data.org | The [terms](https://www.football-data.org/about) authorize registered API-key use for one application, require credential secrecy and attribution, and impose fair use. The [API policy](https://docs.football-data.org/general/v4/policies.html) publishes the free 10-request/minute limit. | Post-cancellation use is restricted, and permanent raw retention is not expressly granted. Do not treat current access as durable Evaluation V2 authority. |
| Football-Data.co.uk | Existing research found a bounded manual private-research route only. | Automated acquisition stays excluded. Deprioritized unless a named gap requires it. |
| Understat | Public pages can be read manually for bounded research. | No official bulk/API, retention, period, correction, or stable-version permission was found. Automated acquisition stays excluded. Deprioritized. |

The terms review resolves whether small technical checks are possible; it does
not resolve data completeness, xG-series identity, immutable retention, or
Evaluation V2 admission.

## PitchAPI validation procedure

No call may execute until the owner approves a request budget ticket. The
validator may be implemented first against synthetic fixtures and sanitized
schemas.

### Frozen inputs for an approved audit

- provider and endpoint version observed at run time;
- Germany Bundesliga `l_1Isor4`, season 2023/24, expected 306 finished league
  matches;
- France Ligue 1 `l_3FJFUl`, season 2022/23, expected 380 finished league
  matches;
- an exact fixture-ID manifest obtained within the approved budget;
- an explicit rule excluding cups, playoffs, friendlies, abandoned matches,
  and the separate Austria Bundesliga catalog;
- acquisition start/end times, code Git SHA, dependency-lock hash, credential
  reference name, request count, response status, and any returned request ID;
- no credential values and no raw provider payload in logs or reports.

### Checks

1. Verify expected match counts, unique match IDs, league/season identity,
   finished lifecycle, unique stable team IDs, and parseable kickoff values.
2. Request the shot resource once for every manifest match. Stop on an
   unbudgeted pagination path, an undisclosed extra endpoint need, `401`, `403`,
   repeated `429`, a schema change, or request-budget exhaustion.
3. For each match, distinguish a valid empty shot list from missing, denied,
   partial, or malformed data. A missing resource is not zero shots.
4. Require every shot to have a unique provider shot ID within its match, a
   mapped team ID, finite numeric pre-shot `expected_goals` in `[0, 1]`, an
   explicit `situation`, and an explicit response period/group.
5. Identify penalties only from the documented `situation=Penalty` value.
   Never infer penalties from xG, outcome, minute, or coordinates.
6. Admit only explicit regulation-period values mapped to first or second half.
   Never infer the period from minute. Reject unknown, extra-time, shootout, or
   missing periods for the frozen xG-for aggregate.
7. Produce per-season counts for matches requested, successful resources,
   empty resources, shots, penalties, regulation shots, invalid xG, missing
   fields, duplicate IDs, unknown periods/situations, and request failures.
8. Repeat a predeclared small sample only if the owner budgets repeat calls.
   Compare canonicalized response hashes and enumerate changed IDs/fields;
   never overwrite an earlier observation.
9. Test cross-season consistency from observable schema, field semantics,
   numeric domains, enumerations, and documented source metadata. If the
   upstream xG provider/model/version is still unknown, record
   `CROSS_SEASON_XG_SERIES=UNPROVED`; numerical similarity cannot prove model
   identity.
10. Emit `PASS`, `PARTIAL`, or `FAIL` separately for technical coverage and
    Evaluation V2 qualification. Technical coverage cannot override missing
    permission, retention, correction, or model-version evidence.

### Proposed request budget for a later owner decision

The known one-shot-resource-per-match shape implies a base ceiling of 688
requests: one fixture manifest and 306 shot resources for Bundesliga, plus one
fixture manifest and 380 shot resources for Ligue 1. Any match-detail,
pagination, retry, or repeat-sample calls must be enumerated separately before
approval. The budget ticket must also freeze pacing, concurrency, retry count,
temporary handling, deletion, and stop conditions. This plan does not approve
those 688 requests.

## What still needs external confirmation

External confirmation remains necessary for an Evaluation V2 route when
published terms and API metadata do not establish:

- PitchAPI's legal terms for automated private research and immutable raw
  retention;
- upstream xG supplier, model identity/version, and cross-season consistency;
- correction history, immutable revision identity, prior-version access, and
  long-term provider-ID behavior;
- any unpublished numeric limit needed for a safe full-season audit.

Because communications are canceled, these facts remain `UNKNOWN` unless
future published terms or authorized API metadata resolve them. The dependent
Evaluation V2 activity stays excluded. No external answer is needed for
synthetic adapter tests, documented schema validation, or an approved in-memory
technical audit that makes no retention or xG-model identity claim.

API-Football and football-data.org can support only the fields their published
terms and entitlements cover. Neither currently supplies qualifying shot xG.
Understat and Football-Data.co.uk remain inactive fallbacks; do not research or
contact them unless a new ticket names the exact unresolved technical gap.

## Execution order

1. Rotate `FOOTBALL_DATA_DOT_ORG_API_TOKEN` before any future
   football-data.org call because its previous value was exposed in local UI
   output. Never record the replacement value.
2. Implement the PitchAPI coverage validator against synthetic fixtures. It
   must make no network call and persist no provider payload.
3. Add tests for empty versus missing shots, penalty and period mapping,
   finite xG, duplicate IDs, unknown enums, partial seasons, request-budget
   stops, and mixed-xG rejection.
4. Prepare an exact owner decision for the API request budget. Do not execute
   it by implication.
5. After approval, run only the bounded PitchAPI audit and publish sanitized
   technical evidence.
6. Implement disabled research adapters only for provider/resource scopes whose
   published terms clearly permit the intended activity. Use synthetic
   contract fixtures when raw retention is not permitted or remains unclear.
7. Verify identity mapping, correction append behavior, point-in-time rules,
   protected-data denial, immutable forecast behavior, and baseline access.
8. If an existing unchanged Rust engine and appropriately authorized inputs are
   available, run a separately ticketed deterministic simulation labelled
   `EXPERIMENTAL_ONLY`. Do not implement the xG-for model or claim Evaluation V2.

## Remaining Evaluation V2 blockers

- two additional independent men's competition-season groups are not
  qualified;
- the corpus still lacks the frozen minimum 500 eligible targets and remaining
  220-target capacity;
- no alternative provider has proved a single identified, compatible,
  versioned xG series across the proposed groups;
- complete shot, penalty, regulation-period, correction, retention, and source
  hash evidence is missing for PitchAPI;
- exact corpus/firewall/policy IDs and hashes are not frozen;
- the complete pre-registration is not frozen;
- the xG-for model is not implemented or verified; and
- no authoritative Evaluation V2 run has been approved.

No blocker may be removed by treating an experimental result as qualified
evidence or by changing Decisions 1 or 2 without a new owner event.
