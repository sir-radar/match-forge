# Pre-P03 acquisition audit, 13 November 2026

Phase A baseline. GitHub main was `14e670fbf365eaed8040de2bacd127e6600df949`.
The operating database was queried in read-only transactions and reported
migration `202611130300`. No provider requests or operating writes were made
for this audit. Counts are observations, not recovery targets or eligibility
decisions. P02's existing result, identity and knowledge-time rules apply.

## Restriction inventory

| Classification | Evidence on main | Consequence |
| --- | --- | --- |
| Remove | [history_requests.py](../../python/football/src/football/product/history_requests.py) assigns the same 86,400-second deadline to successful checks. [provider_history_scopes.py](../../python/football/src/football/product/provider_history_scopes.py) applies that interval to scope completion and cached current-season results. | A successful request prevents an immediate fresh check, even with explicit refresh. The latest result may change while retained bytes are still treated as fresh. |
| Replace | The same scope claim selects successful scopes by the first year in the season label. The response cache uses the final year and can reuse completed seasons indefinitely. | A season spanning two years can lose scheduled rechecks halfway through. A partial or corrected completed season still needs an explicit fresh path. |
| Replace | [cli.py](../../python/football/src/football/product/cli.py) caps scheduled history at two scopes per provider and one discovery request. [config.go](../../go/api/internal/app/config.go) requires at least one hour and defaults scheduled history off. | Fixed throughput is unrelated to observed capacity. The local file has history disabled and sets both scope limits, the discovery limit and the one-hour cadence. |
| Remove | The local file and example cap API-Football history at 2024. [sync_history.py](../../python/football/src/football/product/sync_history.py) skips the requested year above that value and later substitutes the capped season. | A permitted account can miss requested seasons. Verified plan denials and real quota limits must still govern requests. |
| Separate | `_sync_league_history` can return without a provider request when the upcoming teams satisfy `_history_sufficient`. It also uses sufficiency to stop its fallback sequence. | Ten eligible prior matches can satisfy forecast context while the latest result is absent. Bootstrap sufficiency is not a result-recovery signal. |
| Replace | [operational_details.py](../../python/football/src/football/product/operational_details.py) performs bounded overdue recovery during operational provider sync. [product_recoverable_fixtures](../../infrastructure/migrations/202610130500_operational_refresh_state.sql) only exposes trusted FotMob and PitchAPI mappings in nonterminal states. | Recovery shares detail capacity and depends on that sync running. Finished fixtures with missing score basis or team history, plus fixtures without an admitted native route, need distinct dispositions. The date predicate in this lane selects *older* fixtures and has no age floor. |
| Retain or refine | [history_requests.py](../../python/football/src/football/product/history_requests.py) and [api_football.py](../../python/football/src/football/product/api_football.py) enforce persistent provider budgets and cooldowns. Historical requests yield to active live work. Scope claims and publication use the existing work leases and fencing. | Preserve enforced quotas, source cooldowns, transactional deduplication and ownership. A finite positive balance is not by itself proof that all remaining requests must be reserved. Live scheduling and fairness changes belong to P03. |
| Retain | [capability_registry.py](../../python/football/src/football/providers/capability_registry.py) checks exact resource scope, availability and processing versions. [resource_authority.py](../../python/football/src/football/providers/resource_authority.py) tracks downstream authority separately. | Scope, credentials, versions and score qualification remain valid controls. The audited operational routes do not use a blanket model-approval predicate. Partial capability is already eligible for its declared scope. |
| Retain | [history_requalification.py](../../python/football/src/football/product/history_requalification.py), [fixture_reconciliation.py](../../python/football/src/football/product/fixture_reconciliation.py), [sync_storage.py](../../python/football/src/football/product/sync_storage.py) and [live_resources.py](../../python/football/src/football/product/live_resources.py) own replay, mapping, score-basis and source-order behavior. | A delayed or absent score does not prove full time. Raw or retained final observations still need verified identity, chronology and result qualification. |
| Verify | [sync.py](../../python/football/src/football/product/sync.py) calls existing settlement after MVP sync. [external_prediction_recovery.py](../../python/football/src/football/product/external_prediction_recovery.py) already owns append-only settlement and generation checks. | Trace work generation from each result writer. [PR #230](https://github.com/sir-radar/match-forge/pull/230) was an open draft at `887acb8`, so its changes are outside this main baseline. |

## Operating census

At 21:22 UTC the raw product fixture table had 306,820 rows. Using P02's
four-hour audit threshold, 1,678 unresolved rows were overdue: 1,261 scheduled,
74 live and 343 postponed. Of those, 1,261 were older than seven days, 1,097 had
no linked operational provider observation and three scheduled rows had a
linked retained observation marked finished. These are raw fixture rows and may
include equivalent identities. The counts do not establish that the provider
still has a score or that the three retained scores can be admitted.

The existing recovery view exposed 29 FotMob candidates and no PitchAPI
candidates at that threshold. Twenty of the 29 were older than seven days.
There were 296,633 finished rows, all with both score values. 93,380 had
`UNKNOWN` score basis. Among latest stored match-history decisions, 181,363
were ineligible under `ProductIdentityTrustV1` and five were ineligible for a
non-played terminal status. Those decision counts use a different population
from the raw product fixtures and do not measure missing scores.

FotMob history had 578 pending, 333 failed, eight deferred and two successful
scopes. PitchAPI had 288 pending, three failed, 11 deferred and one running
scope. The running scope's shared lease expired on 6 November at 20:37 UTC.
Neither provider completed a scope that UTC day. One overall history run
reported success that day, so the outer job status alone cannot report
historical scope completion.

At the budget snapshot, API-Football had used all 100 daily calls on both
12 and 13 November. On 13 November, FotMob had 7,317 recorded calls and
PitchAPI had 10,525. Neither budget row declared a finite remaining allowance.
That absence supplies no upper bound. There was no active deferred-until
timestamp on those two rows at census time.

## Provider availability

Snapshot counts are retained database registrations. They establish prior
access only and do not establish current access for another scope. Configured
credentials were checked for presence, with their values omitted.

| Provider | Route and retained evidence | Current recovery use or gap |
| --- | --- | --- |
| FotMob | Enabled operational calendar, league and match resources. 56,906 validated snapshots and successful same-day syncs. | Existing trusted candidates. Check resource-specific caching, native IDs and ordinary access failures before fallback. |
| PitchAPI | Enabled operational client with a configured token, dated fixtures, league seasons and match resources. 32,055 validated snapshots and successful same-day syncs. | Existing score route. Honor HTTP 429 and Retry-After and keep missing optional analytics separate. No candidates in the existing overdue view at census time. |
| API-Football | Configured token, dated fixtures, finished seasons and standings. 715 validated snapshots and five partial capability registrations. | Persisted quota exhausted. The [provider's league guidance](https://www.api-football.com/news/post/how-to-get-all-data-from-a-league-with-api-football) describes free-plan season limits. Exact account season coverage still needs verification. |
| football-data.org | Configured token, v4 competition fixtures and standings, with an explicit league crosswalk. 163 validated snapshots. | Existing historical fallback. Retained access does not establish current entitlements for every season. |
| OpenFootball | Commit-pinned repository mirror and bulk importer. One validated registration. | Historical file source. Check revision and native identity before using changes. |
| Football-Data.co.uk | CSV/ZIP catalogue and importer. 67 validated snapshots out of 68. | Historical file source. Preserve version/digest checks and actual service limits. |
| StatsBomb Open Data | Commit-pinned source adapter. Eight validated registrations. | Selected historical competition and season coverage. Not a general live or correction feed. |
| Understat | Public session-backed resource adapter. Two validated registrations and three partial capabilities. | Scoped historical match and xG evidence. No proven recurring score fallback. |
| Flashscore | Existing source adapter. Seven validated registrations and six partial capabilities. | Scoped evidence only. Reuse retained resources first and respect actual access behavior. |
| Soccerway | Existing source adapter. Seven validated registrations and six partial capabilities. | Scoped evidence only. Shared ownership with Flashscore makes independence unproven. |
| WhoScored | Existing historical selector and scoped fixture adapter. One validated registration and one partial capability. | Retained sample. Neither continuous coverage nor crosswalk verified. |
| ESPN | Scoreboard and summary adapters. Three validated registrations and three partial capabilities. | Targeted research route. No confirmed production identity bindings for the overdue cohort. |
| Sofascore | Native normalizer. | No configured recurring acquisition route or validated registration found in this census. |
| FBref | Native normalizer. | No configured recurring acquisition route or validated registration found in this census. |
| ClubElo | Rating normalizer. | Rating enrichment does not provide result authority. |
| Sportmonks | Configured token and existing prediction adapter. | Historical result entitlement and a usable recovery adapter remain unverified. |
| TotalCorner | Candidate documented in the [access register](../source-acquisition.md). | No configured adapter or verified token. |

Exact account coverage and fallback participation must be verified on relevant
resource scopes. Absent evidence remains unresolved. The inventory supplies a
baseline for the requested recovery work, with no readiness or rollout verdict.
