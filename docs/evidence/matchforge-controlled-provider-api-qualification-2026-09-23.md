# Controlled provider API qualification — 2026-09-23

Status: `RESEARCH_ONLY`. Authorized by
[the owner decision](owner-decision-authorize-controlled-provider-api-qualification-2026-09-23.md).

Existing credentials were read only from the ignored `.env` file. Credential
values were never printed, logged, documented, committed, or included in tool
output. Responses were processed in memory; no raw response was retained. No
protected competition, bulk acquisition, ingestion, provider activation, model
implementation, frozen-decision change, or Evaluation V2 execution occurred.

## Result

| Provider | Requests | Bundesliga 2023/24 | Ligue 1 2022/23 | Statistics / odds | Shot xG | Qualification result |
| --- | ---: | --- | --- | --- | --- | --- |
| football-data.org | 8/10 | `PASS` for 306-match Tier B fixtures/results | `FAIL`: HTTP 403 under current entitlement | No detailed statistics; no usable odds | None | Useful for Bundesliga fixtures/results and current schedules; does not cover both historical groups or xG |
| API-Football | 10/10 | `CONDITIONAL PASS`: 306 regular-season matches plus 2 relegation-playoff fixtures | `CONDITIONAL PASS`: 380 matches | Aggregate statistics sampled; historical odds explicitly unavailable | No shot-level xG; one Bundesliga sample had team-match aggregate xG only | Best two-season Tier B fixture/stat candidate; not an odds or Tier A xG solution |
| PitchAPI | 7 successful API requests; 1 local failed attempt | `PARTIAL`: 306 finished matches and one 31-shot xG sample | `PARTIAL`: 380 finished matches; shots not sampled | Match analytics advertised | Per-shot xG verified in one Bundesliga match | Best Tier A technical candidate, but model identity, full-season shot completeness, rights, retention, corrections and stable versions remain blocking |

No provider/competition-season combination yet meets every MatchForge technical
and data-access requirement. No new Evaluation V2 group is qualified.

## Credential and request controls

| Provider | Credential variable | Control result |
| --- | --- | --- |
| API-Football | `API_FOOTBALL_API_KEY` | Present in ignored `.env`; value suppressed; exactly 10 read-only requests |
| football-data.org | `FOOTBALL_DATA_DOT_ORG_API_TOKEN` | Present in ignored `.env`; value suppressed; 8 read-only requests |
| PitchAPI | `PITCH_API_TOKEN` | Present in ignored `.env`; value suppressed; 7 API requests plus one sandbox-local failed attempt |

`.env` is ignored by `.gitignore`. No request used verbose HTTP output. Reports
contain endpoint paths and aggregate facts only.

## football-data.org

### Requests

All successful unless noted:

1. `GET /v4/competitions/BL1`
2. `GET /v4/competitions/BL1/matches?season=2023`
3. `GET /v4/competitions/BL1/matches`
4. `GET /v4/competitions/FL1`
5. `GET /v4/competitions/FL1/matches?season=2022` — HTTP 403
6. `GET /v4/competitions/FL1/matches`
7. `GET /v4/competitions/BL1/matches?season=2023&matchday=1`
8. `GET /v4/matches/{historical_bl1_match_id}`

### Account and limits

- Every response reported API version `v4`.
- Remaining-minute headers decreased from 9 to 4; reset values ranged from 60
  to 1 seconds.
- This matches the published free limit of 10 requests/minute.
- No header identified the account plan.

### Bundesliga 2023/24

- 306 matches; provider result count 306.
- All 306 finished.
- 306 unique non-null match IDs; team IDs present.
- All kickoffs use UTC `Z` timestamps.
- Kickoff range: 2023-08-18T18:30:00Z through 2024-05-18T13:30:00Z.
- `lastUpdated` exists on all matches.
- Available fields include competition, season, match ID, UTC kickoff, status,
  matchday, stage, teams, score, referees, `lastUpdated`, and an odds object.
- The detailed historical match had no statistics field.
- The odds object contained no usable prices.

This is a complete Tier B fixture/result candidate, subject to later terms,
retention, independent kickoff, mapping, and lifecycle checks. It cannot supply
match statistics, odds, shots, or xG.

### Ligue 1 2022/23

The season request returned HTTP 403 because it is outside this account's
permissions. Catalog metadata does not override this result. Match count,
kickoffs, IDs, lifecycle and completeness are unavailable from this entitlement.

### Current-season continuity

On 2026-09-23:

- Bundesliga 2026/27: 306 fixtures; 36 finished, 72 timed, 198 scheduled.
- Ligue 1 2026/27: 306 fixtures; 45 finished, 69 timed, 192 scheduled.
- IDs were unique and kickoffs were UTC in each returned snapshot.

This proves account access to current schedules/results, not an update SLA.

### Corrections and reproducibility

`status` and `lastUpdated` support mutable polling. No revision ID, prior-value
history, correction reason, immutable release, cursor, webhook, or provider
publication timestamp was found. A later authorized adapter must save each exact
response with MatchForge acquisition time and hash; `lastUpdated` alone cannot
prove what was known at an earlier time.

## API-Football

### Requests

Exactly 10 requests returned HTTP 200 with empty API error objects:

1. `GET /status`
2. `GET /leagues?id=78&season=2023`
3. `GET /fixtures?league=78&season=2023`
4. `GET /fixtures/statistics?fixture=1048881`
5. `GET /leagues?id=61&season=2022`
6. `GET /fixtures?league=61&season=2022`
7. `GET /fixtures/statistics?fixture=871474`
8. `GET /odds?league=78&season=2023&page=1`
9. `GET /odds?league=61&season=2022&page=1`
10. `GET /fixtures?league=78&season=2023`

All returned result sets used one page.

### Account and limits

- Plan: `Free`; active: `true`.
- Reported expiry: 2027-09-23T00:00:00Z.
- Published/status daily limit: 100; public minute limit: 10.
- Requests 1–9 reported remaining values decreasing from 100 to 91.
- Request 10, from a fresh client process, reported 99 remaining.
- The conflicting remaining values mean final provider-reported quota is
  `UNKNOWN`; MatchForge's own request count is exactly 10.

### Bundesliga 2023/24

- League ID: 78.
- 308 unique fixture IDs returned.
- 306 regular-season fixtures: 34 rounds × 9.
- 2 additional relegation-playoff fixtures.
- Statuses included `FT` and `PEN`.
- Qualification must select regular-season rounds explicitly; using all 308
  would violate the intended complete-league-season scope.
- Coverage metadata reports events, lineups, fixture statistics, player
  statistics, injuries, standings and related endpoints as available.
- Coverage metadata reports odds as unavailable.

One fixture-statistics sample returned two team rows. Fields included possession,
blocked shots, corners, fouls, saves, offsides, pass counts/accuracy, cards,
inside/outside-box shots, shots on/off goal, total shots, and `expected_goals`.
The xG value was one string-valued team-match aggregate per team. No shot records
or shot-level xG were supplied.

### Ligue 1 2022/23

- League ID: 61.
- 380 unique fixtures returned; all observed statuses were `FT`.
- Coverage metadata matches the Bundesliga resource flags and reports odds as
  unavailable.
- One fixture-statistics sample returned the same general aggregate fields but
  no `expected_goals` field.

One sample cannot prove season-wide statistic completeness or season-wide xG
absence. The provider publishes no xG-specific completeness guarantee.

### Odds, corrections and reproducibility

Both candidate seasons report `odds=false`; both historical odds requests
returned zero rows. Historical odds therefore fail on this free entitlement.

Provider league and fixture IDs are numeric and unique in these snapshots.
Kickoffs use ISO UTC offsets. No immutable source version, correction sequence,
prior-value history, or usable record-level correction timestamp was verified.
Any later use requires immutable MatchForge observations and acquisition times.

## PitchAPI

### Requests

Seven API requests returned HTTP 200. One earlier sandbox-local attempt failed
before reaching the service, producing eight client attempts total. No raw
response was retained.

The bounded calls covered:

- league catalog;
- Bundesliga 2023/24 match list;
- Ligue 1 2022/23 match list;
- current Bundesliga match list;
- current Ligue 1 match list;
- one Bundesliga match detail; and
- that match's shots.

### Account, limits and catalog

- Live catalog contains 70 leagues, resolving the earlier public 42-versus-70
  documentation conflict for this account and date.
- Germany Bundesliga: league ID `l_1Isor4`, free, seasons 2021/22–2026/27.
- France Ligue 1: league ID `l_3FJFUl`, free, seasons 2021/22–2026/27.
- Austria Bundesliga is a separate `l_3zsMpo`; country must be part of scope.
- Responses exposed `content-type` and `x-request-id`, but no rate-limit,
  account-tier, API-version, `ETag`, or `Last-Modified` header.
- Exact numeric burst ceiling and account entitlement contract remain unknown.

### Historical candidates

Bundesliga 2023/24:

- 306 matches, all finished.
- 306 unique IDs; no duplicates.
- All 306 have kickoff dates.
- Date range: 2023-08-18 through 2024-05-18.

Ligue 1 2022/23:

- 380 matches, all finished.
- 380 unique IDs; no duplicates.
- All 380 have kickoff dates.
- Date range: 2022-08-05 through 2023-06-03.

Current 2026/27 catalogs contain 306 fixtures for each league. Bundesliga had
36 finished and 270 not started; Ligue 1 had 45 finished and 261 not started.

### Shot xG sample

One Bundesliga match returned 31 shots:

- all 31 had parseable `expected_goals`;
- xG range: 0.0117523512–0.6388428807;
- fields included shot ID, `expected_goals`, `expected_goals_on_target`,
  `situation`, `shot_type`, minute, team ID, and location/target flags.

No penalty occurred in this sample. Official documentation enumerates
`Penalty`, but a live value was not verified. Shot rows did not contain a period
field; documentation describes a response grouped by half. The exact live
period-envelope representation still needs validation.

### Blocking xG and access facts

No catalog, match, or shot response identified:

- upstream xG provider;
- model name or version;
- one-model consistency across competitions/seasons;
- correction or restatement sequence;
- immutable data/snapshot version;
- source update/publication time;
- long-term ID migration guarantee; or
- retention and attribution rights.

Only one match's shots were checked. Full-season shot presence, 100% finite xG,
penalty/period completeness, and Ligue 1 shot coverage remain `NOT_RUN`.
Public documentation previously recorded an ID-breaking source rebuild, so
unique IDs in these responses do not prove long-term stability.

## Provider/season disposition

| Provider and scope | Technical result | Data-access result | MatchForge disposition |
| --- | --- | --- | --- |
| football-data.org Bundesliga 2023/24 | Complete Tier B fixture/result snapshot | Credential works; permanent retention still unclear | Candidate for later isolated fixture/result qualification only |
| football-data.org Ligue 1 2022/23 | Access denied | Outside entitlement | Reject this scope |
| API-Football Bundesliga 2023/24 | Complete 306-match regular season after excluding 2 playoffs; aggregate stats sampled | Free key works; retention/revisions unclear; odds absent | Candidate Tier B fixture/stat source, not Tier A xG |
| API-Football Ligue 1 2022/23 | Complete 380-match fixture list; aggregate stats sampled | Free key works; retention/revisions unclear; odds absent | Candidate Tier B fixture/stat source, not Tier A xG |
| PitchAPI Bundesliga 2023/24 | Complete fixture list; shot xG verified for one match only | Key works; legal terms, retention, model/version and corrections unresolved | Promising Tier A research candidate; not qualified |
| PitchAPI Ligue 1 2022/23 | Complete fixture list; shot coverage not sampled | Same unresolved contract/model facts | Promising Tier A research candidate; not qualified |

## Evaluation V2 conclusion

The remaining corpus blocker is not fixture capacity. API-Football and PitchAPI
both expose the required 306-match Bundesliga regular season and 380-match Ligue
1 season. The blocker is a lawful, retained, reproducible, single-model shot-xG
series with complete shots and explicit penalty/period handling.

PitchAPI remains the only credentialed free provider in this probe with actual
shot-level xG. It cannot yet replace or mix with `shot.statsbomb_xg`. Existing
StatsBomb development and Serie A evidence remains intact but cannot count in a
PitchAPI experiment. Decisions 1 and 2 remain unchanged.

## Recommended next actions requiring owner approval

1. Send a bounded PitchAPI inquiry for its legal entity and terms, private
   automated research and retention rights, attribution, upstream xG supplier,
   model/version consistency, correction/version policy, ID migrations, and
   exact numeric request limits.
2. Ask PitchAPI for a provider-generated coverage manifest for every shot in
   the two candidate seasons. Prefer this over a bulk all-match audit.
3. If no manifest exists and the written contract is acceptable, separately
   authorize a bounded full-season completeness audit with an exact request and
   storage plan. Do not retain raw payloads under the current authorization.
4. Clarify permanent internal raw-response retention with API-Football and
   football-data.org before adapter or contract registration.
5. Keep Football-Data.co.uk manual-only and Understat excluded while their
   published terms remain ambiguous for the intended retained model research.
6. After written answers, return to the owner-decision ticket for exact provider
   scopes. Only then may isolated acquisition be considered.
