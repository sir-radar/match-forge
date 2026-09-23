# PitchAPI live audit request budget proposal — 2026-09-23

Status: `PROPOSED — OWNER APPROVAL REQUIRED`

This proposal follows completed synthetic validator ticket
`Implement the PitchAPI validation tool with synthetic fixtures`. It does not
authorize API calls, acquisition, ingestion, raw retention, corpus admission,
model implementation, or Evaluation V2.

## Exact scope and ceiling

| Scope | Manifest calls | Shot-resource calls | Base calls |
| --- | ---: | ---: | ---: |
| Germany Bundesliga `l_1Isor4`, `2023/2024` | 1 | 306 | 307 |
| France Ligue 1 `l_3FJFUl`, `2022/2023` | 1 | 380 | 381 |
| Total required successful calls | 2 | 686 | **688** |

Proposed retry reserve: **14 attempts** (2% of 688, rounded up).

Proposed hard request ceiling: **702 attempts**.

No catalog, match-detail, event, lineup, player, advanced-statistics, repeat
sample, correction-recheck, pagination, or other endpoint is included. Any
pagination requirement or extra endpoint stops the audit and requires a new
budget decision.

## Request paths

- `GET /v1/leagues/l_1Isor4/matches?season=2023%2F2024`
- `GET /v1/leagues/l_3FJFUl/matches?season=2022%2F2023`
- one `GET /v1/matches/{validated_match_id}/shots` for each of the 686 unique
  manifest match IDs.

All 686 shot paths are derived only after the corresponding manifest passes
league, season, match-count, lifecycle, kickoff, team-ID, and match-ID checks.

## Rate and retry strategy

- concurrency: **1**;
- start rate: **1 request/second**, no bursts;
- request timeout: **30 seconds**;
- maximum attempts per path: **2**;
- total retry attempts across the audit: **14**;
- retryable failures: timeout, transport error, HTTP `408`, `429`, `500`,
  `502`, `503`, or `504` only;
- timeout/transport/5xx/408 delay: **5 seconds**, then one retry;
- first `429`: require `Retry-After`, wait that duration plus **5 seconds**,
  then retry once;
- second `429` anywhere in the audit: **stop**;
- `401` or `403`: **stop immediately**;
- any other non-`200`: mark failure and stop the affected scope;
- no SDK or transport auto-retry: every attempt must be visible in the audit
  log and count toward 702;
- wall-clock ceiling: **45 minutes**; reaching it stops the audit.

At one request/second, the 688-call base needs at least 11 minutes 28 seconds,
plus response latency. The 45-minute ceiling allows bounded latency and the
declared retry waits without permitting an unbounded run.

## Data handling

- Read the existing key only through `env:PITCH_API_TOKEN`.
- Never print request headers, URLs containing credentials, credential values,
  or raw response bodies.
- Hold response bodies in memory only for validation.
- Do not write raw PitchAPI payloads, caches, temporary response files, or
  reconstructed source data.
- Retain only sanitized counts, finding codes, request status classes,
  request-ID-presence flags, timestamps, code/dependency hashes, and the final
  validator report.
- Delete in-memory payload references when each scope report is complete.

## Expected coverage

If all required calls succeed, technical coverage is:

- 306/306 Bundesliga matches and shot resources;
- 380/380 Ligue 1 matches and shot resources;
- 686/686 combined matches and shot resources;
- every returned shot checked for match-scoped ID uniqueness, fixture-team
  membership, finite numeric pre-shot xG in `[0,1]`, explicit situation, and
  explicit `FirstHalf` or `SecondHalf` grouping;
- penalties counted only from exact `situation=Penalty`;
- empty shot arrays distinguished from missing, failed, or malformed resources.

Shot volume and eligible Evaluation V2 target count remain unknown until the
audit runs. The audit cannot promise the remaining 220 eligible targets.

## Restrictions that remain after a technically complete audit

Unless separately resolved, all of these still block Evaluation V2:

- no published permission for immutable raw-response retention;
- upstream xG supplier/model/version remains unidentified;
- one-series cross-season compatibility remains unproved;
- correction history, immutable revision identity, and prior-version access
  remain unavailable;
- provider IDs have a documented history of rebuild changes;
- the proposal includes no repeat fetch, so correction convergence is not
  tested;
- exact corpus/firewall hashes and owner corpus admission remain unfrozen.

A technical `PASS` therefore does not imply Evaluation V2 qualification.
