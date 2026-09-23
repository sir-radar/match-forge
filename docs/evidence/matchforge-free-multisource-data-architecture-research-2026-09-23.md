# Free multi-source data architecture research — 2026-09-23

Status: `RESEARCH_ONLY`. No source was downloaded, ingested, admitted, or made
authoritative. No frozen decision, preregistration, model, forecast, protected
dataset, or Evaluation V2 result was changed or executed.

The bounded public-source follow-up is recorded in the
[provider access matrix](matchforge-provider-access-matrix-2026-09-23.md).

## Result

MatchForge can run a useful free fixture/result service, but no verified free
combination currently clears every requirement for continuous match statistics,
odds, and one reproducible shot-xG series across Evaluation V2.

The most feasible free route is:

1. use football-data.org for automated fixtures and results in its free
   competitions;
2. qualify API-Football's free account for current statistics and odds;
3. retain Football-Data.co.uk for controlled historical CSV acquisition, not
   unattended polling unless written permission is obtained;
4. use OpenLigaDB and OpenFootball only as scoped checks and fallbacks; and
5. investigate PitchAPI first, then Understat, for one complete and consistent
   shot-xG series.

This route does not yet unblock Evaluation V2. PitchAPI and Understat both lack
the rights, model-version, correction, and complete-season evidence required for
admission. StatsBomb Open Data remains the most reproducible source and preserves
the frozen feature exactly, but it cannot supply the two missing complete men's
groups. TotalCorner is paid. FotMob and SofaScore prohibit the required automated
or bulk public-page acquisition. Wyscout Open Data contains events but no xG.

## Ranked provider feasibility

### Fixtures, results, odds, and match statistics

| Rank | Provider | Verified availability | Automation and cost | Main risk | Recommendation |
| --- | --- | --- | --- | --- | --- |
| 1 | [football-data.org](https://www.football-data.org/coverage) | Free fixtures, delayed scores, tables, UTC kickoffs, stable match/team/competition IDs, status, and `lastUpdated` for 12 competitions | Official API, 10 calls/minute, €0; statistics and odds are separate €15/month add-ons | Free historical depth, delay, correction history, and season completeness still need qualification | Best free automated fixture/result feed |
| 2 | [API-Football](https://www.api-football.com/pricing) | Fixture, event, lineup, statistic, pre-match odds, and in-play odds endpoint types; league-season coverage flags | Official free API, 100 calls/day and 10/minute; paid fallback starts at $19/month | Exact free seasons, retained odds, completeness, ID correction behavior, and snapshot retention are unverified | Best free current-stat/odds candidate after a bounded account-level probe |
| 3 | [Football-Data.co.uk](https://football-data.co.uk/data) | 32 result seasons and 27 odds/stat seasons are advertised; current 2026/27 big-five CSVs are present and normally updated at least Wednesday and Sunday | Free CSVs, but no API; published use restriction makes unattended bot polling unsuitable without written permission | Mutable files, no stable entity IDs or correction ledger; statistics change definition by league/season; odds lack row-level observation time | Keep as controlled historical source; seek written automation and retention permission |
| 4 | [OpenLigaDB](https://api.openligadb.de/index.html) | Keyless season/match/team/table API, stable numeric IDs, last-change endpoint; completed seasons stated not to change | Free, ODbL, 60 requests/minute/IP, automated use supported with a descriptive user agent | German focus, community completeness, no odds or broad match statistics | Bundesliga result check and emergency fallback |
| 5 | [OpenFootball](https://github.com/openfootball/football.json) | Major-league fixture/result JSON from 2010/11; current season folders and Git revisions | Public-domain files, generated daily | Upstream files are not guaranteed current; no stable match IDs, odds, or statistics | Reproducible cross-check and gap detector only |
| 6 | [TotalCorner](https://www.totalcorner.com/page/api) | JSON fixtures/results, provider IDs, aggregate statistics, timestamped events, and odds movement; claims history since 2014 | API requires paid membership; 30 requests/minute and 30 rows/page. Published Advanced price is €28/30 days. Public-page scraping is prohibited without consent | Not free; older coverage is thinner; retention, correction history, and exact membership entitlement are unclear | Paid fallback only after owner and terms review |

Football-Data.co.uk is still valuable because its CSVs include full/half-time
results, aggregate shots, shots on target, corners, fouls, offsides, cards,
referees, and market prices described in its [field notes](https://football-data.co.uk/notes.txt).
Those fields are not stable enough to assume one definition across all seasons.
For example, its Italy page warns that Serie A shot counts changed from 2018/19,
apparently when blocked shots began to be included. Pinnacle prices have also
been flagged unreliable since July 2025. Each field therefore needs a scoped
provider rule and source-version record.

Football-data.org's [free plan](https://www.football-data.org/pricing) does not
include the statistics or odds required by the full request. API-Football is a
candidate for those gaps, not a qualified source: the official guidance requires
clients to inspect each league-season `coverage` record, and no authorized data
probe was run in this research.

### Shot-level xG

| Rank | Provider | Shot and model evidence | Coverage/update evidence | Rights and reproducibility | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | [PitchAPI](https://pitchapi.dev/) | Per-shot `expected_goals`, coordinates, team/player, outcome, minute, body part, period grouping, and `situation`, including `Penalty`; documentation calls xG pre-shot | Claims every endpoint, history from 2021, current fixtures synchronized daily, and a free key | Upstream xG supplier/model/version, retention right, correction ledger, and snapshot export are not published. A September 2026 rebuild changed IDs. Documentation also conflicts on catalog size. | Best technical lead; not admissible yet |
| 2 | [Understat](https://understat.com/) | Its own neural-network xG model; public/third-party evidence exposes shot ID, match ID, xG, minute, coordinates, body part, outcome, and penalty situation | Men's EPL, La Liga, Bundesliga, Serie A, Ligue 1, and RFPL pages; historical pages include the candidate 2022/23 and 2023/24 seasons | No official API/export, current bulk-use and retention permission, model version, explicit period field, correction history, or SLA was found | Historical fallback only after written permission and a versioned export/frozen capture |
| 3 | [StatsBomb Open Data](https://github.com/hudl/open-data) | Exact frozen `shot.statsbomb_xg`, explicit period and penalty type, rich documented context | Select historical competitions; updates are irregular rather than continuous | Git revisions and per-file hashes provide the strongest free replay path | Preserve existing evidence, but public coverage cannot supply two more complete men's groups |
| 4 | [Wyscout Open Data](https://figshare.com/articles/dataset/Events/7770599) | Complete 2017/18 big-five event data with shot positions/outcomes and period; no provider xG field | Fixed historical release only | CC BY 4.0, DOI/versioned Figshare files and stable provider IDs | Excellent event source; cannot implement the frozen xG feature |
| 5 | [FotMob](https://www.fotmob.com/tos.txt) | Current/historical shot maps and xG; FotMob states detailed data and xG are Opta-powered | Historical pages exist and current matches update live | Terms require consent and prohibit automated, systematic, regular, or bulk retrieval; no public versioned export/model contract | Reject public-page acquisition; permission inquiry only |
| 6 | [SofaScore](https://sofascore.helpscoutdocs.com/article/129-sports-data-api-availability) | Consumer pages show xG and shot maps, but supplier/model can vary | Live and historical pages | SofaScore says it cannot provide sports-data API endpoints; its terms prohibit scraping/aggregation and automated load | Reject as an acquisition source |

[OpenFootAPI](https://openfootapi.com/docs) advertises FotMob-derived shot xG,
but that capability is priced at $14/month and does not remove the underlying
FotMob provenance and permission questions. It is a low-cost commercial lead,
not a free route. A direct Opta feed is quote-based. No stronger free,
officially documented, versioned shot-xG provider was found.

## xG comparison rules

The available xG values are different measurements, not interchangeable
columns:

- StatsBomb documents a contextual model and publishes the exact frozen field
  in pin-able event files.
- Opta is a mature provider, but neither FotMob public access nor a generic API
  label establishes an authorized, versioned Opta series.
- Understat documents its own model but not a model version or immutable
  correction history.
- PitchAPI documents a useful shot shape but says xG is joined from shot data;
  it does not identify the supplier or prove one unchanged model across seasons.
- SofaScore says its underlying sources vary.
- Wyscout Open Data has no xG field.

Penalty exclusion is directly expressible for StatsBomb, PitchAPI, and
Understat's observed shot shape. Understat still needs an exact period rule.
For every provider, a target becomes ineligible when provider identity, period,
penalty status, or finite pre-shot xG in `[0, 1]` is missing or ambiguous.

Never average, calibrate together, substitute row by row, or join shots by
approximate player/time across xG providers. Development and every authoritative
evaluation group must use the same frozen `xg_series_id`.

## Evaluation V2 capacity

The frozen policy still requires at least three complete men's groups, two
competitions, two seasons, 120 matches per group, and 500 eligible targets.
The qualified StatsBomb Serie A 2015/16 group has 280 eligible targets but is
not admitted. The current StatsBomb Open Data revision has no two further
complete men's domestic groups.

PitchAPI and Understat both show nominal capacity. For example:

- Bundesliga 2023/24 has 306 matches and about 216 ideal targets after a
  10-match team warm-up.
- Ligue 1 2022/23 has 380 matches and about 280 ideal targets after that warm-up.

The combined ideal count is about 496, above the remaining 220. These are not
qualification counts. Missing shots, match lifecycle, exact kickoff order,
same-kickoff grouping, and integrity failures can reduce them. No raw data was
acquired and exact eligible counts remain `NOT_RUN`.

More importantly, PitchAPI or Understat xG cannot be added to the qualified
StatsBomb group. If either alternative is chosen, the coherent experiment needs
a new development dataset and three newly qualified evaluation groups using one
frozen xG series. Existing StatsBomb development and Serie A evidence remains
intact as historical evidence but cannot count in that alternative experiment.

Conclusion: free sources have enough plausible nominal capacity, but no free
route currently proves the access rights, complete season coverage, stable xG
model, and immutable revision required to satisfy Evaluation V2.

## Recommended architecture

Reuse the contracts already defined in `docs/source-acquisition.md`; do not add
a generic data lake, a global provider ranking, or a merged cross-provider event
stream.

```text
ProviderCapabilityV1 + terms and approved scope
        ↓
ProviderSyncPolicyV1 + ProviderResourceContractV1
        ↓
bounded fetch → immutable raw bytes + SourceManifestV1 + SHA-256
        ↓
provider-specific normalization
        ↓
ResolutionDecisionV1 → MatchForge IDs or quarantine
        ↓
field-scoped DataResolutionPolicyV1
        ↓
point-in-time observations and datasets
        ↓
CanonicalChangeSetV1 + DependencyEdgeV1
```

### Ownership and storage

- Python owns provider adapters, normalization, ID mapping, the sync worker,
  point-in-time datasets, and xG features.
- PostgreSQL stores MatchForge IDs, provider mappings, observation intervals,
  conflicts, corrections, jobs, cursors, change sets, and selected field rules.
- Immutable files/object storage holds exact provider bytes, manifests, and
  reports. Parquet holds normalized high-volume shots/events.
- Redis remains cache and temporary job state only. Go serving and Rust
  simulation remain unchanged.

Provider roles are explicit: Tier A supplies shot xG; Tier B supplies
fixtures/results/match statistics; Tier C supplies odds benchmarks. Odds remain
for comparison only and are forbidden as Phase 3A model features. A Tier B or C
source may confirm a fixture fact but cannot manufacture or replace Tier A shots.

### Identity, duplicate handling, and conflicts

- Keep every provider ID and map it to stable MatchForge competition, season,
  team, player, and match IDs.
- A season mapping is keyed by provider, provider competition ID, and provider
  season ID.
- Automatic match mapping requires mapped competition, season, home team, away
  team, and timezone-aware kickoff. Score is not identity. Name/date similarity
  alone never merges records.
- Remove repeats only within the same provider snapshot/entity identity. Across
  providers, keep both observations and apply a field-specific rule.
- A disagreement creates an append-only conflict record and quarantine where
  required. Never silently choose whichever provider returned a value.
- Mapping decisions are append-only and later superseded, not edited in place.

There is no global primary source. A versioned `DataResolutionPolicyV1` selects
eligible providers and explicit precedence for one domain/resource/field and
competition scope. Fixture ownership may differ from match-stat and odds
ownership. Provider-specific statistics such as `dangerous_attacks` remain in
their provider namespace unless an exact shared definition is approved.

### Snapshots, corrections, and updates

- Save exact bytes before parsing. Record locator, request identity, HTTP
  evidence, provider update time, MatchForge acquisition time, provider locale
  and timezone, adapter/parser/normalizer versions, and SHA-256.
- A mutable URL is a locator, not a version. New bytes create a new snapshot;
  identical bytes confirm the prior content.
- Corrections append new bitemporal observations and correction records. Old
  inputs, datasets, artifacts, forecasts, reports, and decision evidence are
  never overwritten.
- A correction marks affected dependents for rebuild and publishes a replacement
  with an explicit link to the prior item. Published forecasts remain immutable.
- Keep `football_cutoff`, `knowledge_cutoff`, and `knowledge_mode` separate.
  Retrospective captures without original publication times use the existing
  fixed-snapshot mode and cannot claim historical availability.
- Freeze every same-kickoff forecast batch before revealing outcomes. Target
  outcomes remain structurally separate from inputs.

Each provider/resource/competition has its own approved sync policy. Historical
backfill is pinned and bounded. Current-season updates use the provider's
authorized API, conditional requests or cursors where available, rate limits,
and a bounded post-match correction sweep. Do not freeze a cadence until its
terms and quota are verified.

A cursor advances only after acquisition, preservation, validation,
normalization, ID mapping, field selection, and publication succeed. One
provider failure blocks only the dependent fields. It never triggers silent xG
fallback. Record freshness, fetched/unchanged counts, hashes, bytes, schema
errors, rate limits, retries, quarantines, conflicts, cursor lag, circuit state,
and rebuild work.

## Exact proposed governance amendments

These are proposals for owner review, not approved changes.

### Decision 1

If a licensed/versioned StatsBomb export proves the exact existing
`shot.statsbomb_xg` contract, Decision 1 does not change.

For any other xG source, append a superseding owner decision. Do not edit the
approved event and do not reuse `MATCHFORGE_NPXG_FOR_LAST10_V1`. The new decision
must freeze:

```text
Feature ID:
  a new provider-specific ID, assigned only after the provider contract is known

xg_series_id:
  exact provider + product/feed + field path + schema version + model version
  or an exact immutable snapshot cohort when the provider cannot expose a model
  version and the owner explicitly accepts that limitation

Allowed shots:
  regulation periods 1 and 2 only
  explicit provider penalty flag/situation excluded
  finite pre-shot xG in [0, 1]

Consistency:
  one xg_series_id for development and all authoritative evaluation groups
  no per-shot, per-match, or per-group provider fallback
  no averaging or approximate cross-provider shot joins
  missing/ambiguous provider, period, penalty, or xG makes the target ineligible

Lineage:
  provider IDs, request/export identity, acquisition time, exact raw-byte hashes,
  schema/adapter versions, and correction links retained
```

Keep the approved team match sum, prior 10 eligible same-season matches, season
reset, reference mean, log signal, one coefficient, fitting rules, invalid-value
failures, forbidden additions, same-kickoff seal, and leakage rules unchanged.

PitchAPI cannot receive a final feature ID yet because its upstream xG provider
and model/version are unknown. Understat cannot receive one until a lawful,
versioned export defines the exact xG and period fields. FotMob/Opta and
SofaScore cannot receive one from public pages. Wyscout Open has no compatible
field; fitting a new xG model would be a new hypothesis outside this map.

### Decision 2

If an alternative xG source is selected, append a superseding owner decision
that:

1. keeps the men's-only rule, group/competition/season/match/target minima,
   chronological rules, same-kickoff handling, protected exclusions,
   thresholds, budget, baselines, and dispositions unchanged;
2. requires the new development dataset and every evaluation group to use the
   same frozen `xg_series_id`;
3. preserves existing StatsBomb development and Serie A evidence but excludes
   it from counting in the alternative-provider experiment;
4. requires a newly qualified development source and at least three new men's
   evaluation groups, two competitions, two seasons, and 500 eligible targets;
5. freezes every raw/source manifest, normalized dataset hash, target manifest,
   eligible count, MatchForge/provider mapping, and field-selection policy;
6. requires zero protected/development intersection without opening protected
   outcomes; and
7. requires the full preregistration to be revised and explicitly approved
   before implementation tickets are released.

Fixture/result/stat sources may differ from the xG provider only when the exact
selected facts and field rules are recorded and those sources do not substitute
or alter xG.

## Incremental migration

1. Preserve the current StatsBomb and Football-Data evidence, baselines,
   published forecasts, protected firewall, and mandatory Rust simulation rule.
2. Approve exact provider/resource scopes, terms, retention, cadence, and cost.
3. Register disabled capability, resource, runtime, and sync contracts.
4. Acquire only approved sources into isolated provider namespaces; publish no
   canonical or model input data.
5. Normalize and map IDs, quarantine ambiguity, and publish completeness,
   conflict, correction, and point-in-time evidence.
6. Add field-specific selection rules and compare them with current sources;
   leave production forecasting unchanged.
7. Enable current-season sync only after quota, retry, cursor, correction,
   replay, and failure-isolation checks pass.
8. Owner chooses the xG route and, if needed, approves Decisions 1 and 2
   amendments.
9. Qualify exact development and evaluation groups, freeze the corpus and full
   preregistration, then separately release feature implementation.

## Estimated infrastructure cost

| Deployment | Planning estimate | Included | Excluded |
| --- | --- | --- | --- |
| Existing local development machine | $0 incremental/month | Existing PostgreSQL, Redis, filesystem/object storage, scheduled worker | Electricity, backup media, engineering time |
| Free hosted object tier | $0 at up to 10 GB on [Cloudflare R2](https://developers.cloudflare.com/r2/pricing/) | 10 GB-month, 1 million Class A and 10 million Class B operations, free egress under published free tier | Compute and database |
| 50 GB object archive | About $0.60/month beyond R2's free 10 GB, before operations | Raw and normalized immutable files | Compute, database, backup copy |
| Small always-on hosted stack | Rough planning allowance of $6–$17/month | $5–$15 small worker/database plus about $1–$2 object storage/backup | Provider fees, traffic spikes, legal review, engineering time |

The 5–25 GB archive and hosted compute ranges are planning assumptions, not
vendor quotes. Recalculate them after exact leagues, resources, update cadence,
retention, compression, and backup policy are frozen. The recommended free data
baseline costs $0 in provider fees. Paid fallbacks include TotalCorner at the
published €28/30 days, football-data.org statistics plus odds at €30/month,
API-Football from $19/month, and OpenFootAPI xG at $14/month.

## Owner approval boundary

No implementation ticket may be released from this report. The next owner
decisions are:

1. approve the exact provider access matrix: resource, competition/season,
   permitted acquisition method, automation/bulk permission, retention,
   attribution, credential handling, rate ceiling, update policy, and cost cap;
2. choose whether to pursue PitchAPI terms/catalog/model qualification,
   Understat permission/export qualification, the pending StatsBomb offer, or
   no xG route;
3. if a non-StatsBomb route is selected, approve the exact append-only Decision
   1 and Decision 2 replacements after the missing provider facts are proved;
4. separately approve exact corpus membership and the revised complete
   preregistration after qualification.

The pending StatsBomb inquiry remains open. These findings do not lower any
frozen threshold and do not authorize purchases, ingestion, production changes,
model work, or Evaluation V2.
