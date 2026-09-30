# MVP data coverage audit

Checked 30 September 2026. Counts below describe live provider discovery, not guaranteed MatchForge forecast availability. A competition appears in MatchForge only after a successful sync; forecastability additionally requires enough strictly pre-kickoff history.

## Existing credentials and active roles

| Source | Current role | Live audit | Limits / cost | Important gaps |
| --- | --- | --- | --- | --- |
| API-Football | Primary competition discovery, fixtures, results, standings, H2H history, team statistics | 1,240 current competition records; 202 fixtures across 64 competition groups on 2026-09-30 | Free: 100 requests/day. Pro: USD 19/month, 7,500/day. Ultra: USD 29/month, 75,000/day. Mega: USD 39/month, 150,000/day. | No qualified xG/shot feed in the MVP. The current free credential rejects 2026 history, so it cannot produce present-season forecasts until its entitlement changes or a qualified history adapter is enabled. |
| football-data.org | Qualified coverage fallback candidate; audited, not enabled in the ingestion path | 13 competitions available to the current token, including EPL, Championship, La Liga, Bundesliga, Serie A, Ligue 1, Eredivisie, Primeira Liga, UCL, Brazil Serie A, Libertadores, Euros and World Cup | Free: 12 competitions, 10 requests/minute and delayed scores. Paid plans currently range from EUR 12 to EUR 199/month. | Current token is much narrower than API-Football; no xG/shot data. Adapter remains future gap work, not silently activated. |
| PitchAPI | Source of the retained evaluated model artifact and historical development evidence | Existing immutable repository snapshots and artifacts | Current entitlement is repository-specific. | Not used as the live fixture service. Prior research rules and firewalls remain active. |

API-Football remains the live MVP source. When its standings endpoint is unavailable, MatchForge deterministically reconstructs standings from stored completed results. That fallback affects only standings and does not fabricate unavailable fixtures, H2H, or forecasts.

## Discovered domestic-league breadth

The current catalog contains 601 European, 74 African, 127 Asian, 62 North/Central American, 163 South American, 32 Oceanian, and 181 world competition records. It identifies 643 records as first division and 67 as second division where provider names are sufficiently clear. These are display/catalog counts, not claims of forecast availability. The current credential produced zero forecastable competitions because 2026 history was unavailable; all 1,240 catalog entries therefore expose `NOT_ENOUGH_HISTORY` rather than fabricated probabilities.

The live API-Football audit found league records in all owner-prioritized European countries. Selected counts of current provider league records are: England 35, Spain 34, Germany 30, Italy 23, France 21, Portugal 15, Netherlands 10, Belgium 26, Scotland 7, Austria 19, Switzerland 14, Denmark 12, Sweden 14, Norway 13, Finland 8, Poland 9, Czech Republic 15, Greece 15, Turkey 9, Croatia 8, Serbia 7, Romania 14, Bulgaria 6, Hungary 7, Slovakia 8, Slovenia 4, Ukraine 6, Ireland 2, Northern Ireland 4, Iceland 4, and Cyprus 3.

Selected non-European discovery counts are: Nigeria 1, South Africa 4, Egypt 5, Morocco 2, Tunisia 2, Algeria 3, Ghana 2, Kenya 2, Tanzania 1; Brazil 83, Argentina 9, Colombia 3, Chile 3, Uruguay 2, Ecuador 2, Paraguay 3, Peru 3; USA 13, Mexico 9, Costa Rica 2; Japan 6, South Korea 5, Saudi Arabia 4, Qatar 2, UAE 3, China 3, India 4, Thailand 2, Australia 23, and New Zealand 5.

These counts include provider-labelled leagues beyond senior first and second divisions. MatchForge infers division only where the provider name is sufficiently clear and exposes the stored division value rather than claiming every discovered record as a senior competition.

## Data fields and gap statuses

Each stored competition records country, continent, inferred division, season, fixtures, results, standings, H2H, forecast, xG and team-stat availability plus source roles. Fixture availability is separate from forecast availability. The product exposes `FORECAST_AVAILABLE`, `NOT_ENOUGH_HISTORY`, `SOURCE_DATA_INCOMPLETE`, and `TEMPORARILY_UNAVAILABLE` without inventing probabilities.

Current material gaps are:

- `NOT_ENOUGH_HISTORY` for teams without ten eligible pre-kickoff matches;
- `NO_STANDINGS` when neither provider standings nor enough stored results exist;
- `NO_H2H` when no mapped prior meetings exist;
- `PROVIDER_LIMIT` / `RATE_LIMIT` when the active API plan cannot cover a requested history refresh;
- no qualified MVP xG or shot source;
- football-data.org adapter not yet activated, so it is not claimed as a working provider fallback.

## Additional providers assessed

Sportmonks, SportDevs, TheSportsDB, OpenLigaDB, Sportradar and Stats Perform/Opta remain candidates only where a measured coverage gap justifies integration. No new paid provider was added. Before integration, MatchForge must record exact competition gain, historical depth, request/storage rights, rate limits, reliability and expected cost for the intended plan.

Current source references: [API-Football pricing](https://www.api-football.com/pricing), [API-Football coverage](https://www.api-football.com/coverage), and [football-data.org pricing](https://www.football-data.org/pricing).
