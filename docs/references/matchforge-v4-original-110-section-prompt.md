# MATCHFORGE V4 — UNIFIED AUTHORITATIVE MASTER CODEX PROMPT

## R3 Completion + Broad Development Data Acquisition + Existing-Provider Expansion + Eight Mandated Source Integrations + Rich Football Intelligence + Live Scores + Multi-Market Forecasting + Controlled Self-Learning

**Repository:** `https://github.com/sir-radar/match-forge`

**Execution mode:** Development/research-first, incremental, evidence-driven and phase-gated.

**Primary current remediation dependency:** `MF-AUD-0009` / R3 identity-history completion.

**Authority:** This prompt supersedes earlier MatchForge provider-integration, data-access, rich-data, market-coverage, live-score and self-learning instructions where they conflict.

Use this document as the **single implementation authority**.

Do not alternate between earlier prompts.

---

# 0. CRITICAL OWNER DECISION — DEVELOPMENT DATA ACCESS

The repository owner has explicitly clarified the intended policy.

MatchForge is currently a **development/research football forecasting platform**, not a commercial production data product.

Therefore:

> **Do not artificially restrict MatchForge data acquisition to officially documented commercial APIs or formally supported production integrations.**

For development, research, historical acquisition, feature engineering, provider comparison, model building and live-data experimentation, MatchForge may investigate and use technically viable public football-data paths.

This includes, where technically accessible:

- official APIs;
- undocumented publicly reachable JSON/API endpoints;
- browser-facing public API endpoints;
- public website resources;
- HTML parsing/scraping of public pages;
- open-source provider wrappers;
- maintained community scraping libraries;
- reverse-engineered public request formats;
- public CSV feeds;
- public JSON feeds;
- public datasets;
- open-source football-data repositories;
- community libraries such as `soccerdata`;
- direct provider-specific adapters;
- public endpoints discovered through normal browser network behavior;
- retained historical resources;
- public website bootstrap/state payloads;
- other technically viable public football-data routes.

The fact that an endpoint:

- is undocumented;
- is intended primarily for the provider's frontend;
- lacks an official developer portal;
- is accessed through a community wrapper;
- requires HTML parsing;
- requires reproducing normal browser HTTP requests;
- would not be ideal for a production commercial integration;

is **not by itself a reason to reject it for MatchForge development**.

The priorities are:

1. useful football data;
2. correctness;
3. reproducibility;
4. evidence retention;
5. coverage;
6. point-in-time integrity;
7. provider neutrality;
8. maintainability.

Do not apply production-vendor conservatism where it unnecessarily prevents useful development/research acquisition.

---

# 1. IMPORTANT BOUNDARY — DO NOT MISINTERPRET THIS DECISION

This decision concerns **football-data acquisition from external sources**.

It does **not** instruct Codex to remove or weaken MatchForge's internal:

- admin API access controls;
- application authorization;
- API authentication;
- browser Origin checks;
- local administration controls;
- request validation.

Do **not** introduce a `MATCHFORGE_ADMIN_ACCESS_ENFORCED` change as part of this decision.

Do **not** alter MatchForge's internal admin/API access policy merely because provider-data access is more permissive.

Those are separate concerns.

If previous uncommitted changes exist solely because this owner decision was previously misinterpreted as an instruction to remove internal MatchForge admin authorization:

- identify them carefully;
- do not discard unrelated user work;
- restore the intended pre-misinterpretation behavior only where the provenance of those changes is unambiguous.

Otherwise leave MatchForge internal access controls unchanged.

---

# 2. EXTERNAL DATA ACCESS — PRACTICAL BOUNDARY

Development flexibility does not mean pretending inaccessible data is accessible.

MatchForge may investigate and use public or otherwise legitimately accessible data routes.

Do not fabricate access.

Do not fabricate observations.

Do not claim support based solely on documentation or repository README claims.

If a source genuinely cannot be accessed, record the actual blocker.

Do not instruct implementation to defeat:

- account authentication;
- CAPTCHAs;
- paywalls;
- private credentials the project does not possess;
- explicit technical restrictions intended to prevent access.

But do **not** classify a source as unavailable merely because:

```text
OFFICIAL_API = false
```

Instead distinguish:

```text
OFFICIAL_API_SUPPORTED
PUBLIC_JSON_ENDPOINT_ACCESSIBLE
PUBLIC_WEB_ENDPOINT_ACCESSIBLE
COMMUNITY_WRAPPER_ACCESSIBLE
PUBLIC_HTML_SCRAPABLE
OPEN_DATASET_AVAILABLE
RETAINED_DATA_AVAILABLE
CURRENTLY_INACCESSIBLE
```

This distinction must appear in the provider capability registry.

---

# 3. EMPIRICAL ACCESS POLICY

Provider capability must be determined empirically.

Use:

```text
DISCOVER
→ INSPECT
→ BOUNDED TEST
→ MEASURE
→ RETAIN
→ NORMALIZE
→ QUALIFY
```

Do not decide:

```text
"unofficial"
→ reject
```

Do not decide:

```text
"scraper"
→ reject
```

Do not decide:

```text
"not documented"
→ reject
```

Instead inspect actual current behavior.

---

# 4. REPOSITORY POLICY RECONCILIATION — MANDATORY

Before implementing the broader provider programme, search the MatchForge repository for documentation, comments, architecture decisions, operational guidance and code assumptions that conflict with this owner decision.

Search for concepts including, but not limited to:

```text
official API only
official provider
supported API only
unsupported endpoint
unofficial endpoint
scraping prohibited
scraper prohibited
public endpoint prohibited
public website data prohibited
authorized provider only
ordinary API only
documented endpoint only
access-control workaround
browser endpoint
community wrapper
provider terms
public web data
web scraping
CAPTCHA
paywall
technical access control
```

Also inspect provider-specific documentation for:

- FotMob;
- Sofascore;
- Flashscore;
- WhoScored;
- Soccerway;
- FBref;
- ESPN;
- Understat;
- ClubElo;
- API-Football;
- PitchAPI;
- football-data.org;
- Football-Data.co.uk;
- OpenFootball;
- StatsBomb;
- any additional provider discovered in the repository.

---

# 5. UPDATE CONTRADICTORY REPOSITORY DOCUMENTATION

Update current authoritative documentation so it reflects the new owner decision.

Potentially relevant current documents include, but are not limited to:

```text
AGENTS.md
PLAN.md
docs/architecture.md
docs/MVP-OPERATIONAL-PROVIDERS.md
docs/MVP-DATA-COVERAGE.md
docs/MVP-HISTORICAL-BACKFILL.md
docs/project-status.json
docs/data-model.md
docs/data-validation.md
docs/model-governance.md
provider-specific documentation
current operational runbooks
current source policies
current ADR/policy documents
```

Do not blindly edit every file.

Only update documents whose current authoritative wording actually conflicts.

The new policy should communicate:

> MatchForge development may use technically viable public football-data sources, including unofficial/public endpoints, community wrappers and bounded public-web acquisition. Official API support is not required for development use. Data still requires provenance, identity qualification, semantic qualification and point-in-time correctness before model use.

---

# 6. HISTORICAL DOCUMENTS / EVIDENCE MUST NOT BE REWRITTEN

Do not corrupt historical evidence.

Documents under historical/evidence/reference areas may represent what was true at the time.

Examples may include:

```text
docs/evidence/
docs/references/
historical decision records
frozen reports
evaluation receipts
```

If an old historical document contains the former policy:

- preserve it;
- do not rewrite immutable evidence;
- create or update the current authoritative policy;
- add a supersession reference where the repository's governance permits it.

Distinguish:

```text
HISTORICAL_RECORD
CURRENT_POLICY
```

A historical decision may remain intact while being superseded prospectively.

---

# 7. CODE COMMENTS / VALIDATION ASSUMPTIONS

Search code for logic that rejects a provider/resource **solely because it is unofficial, undocumented, browser-facing or scraper-derived**.

Do not remove safeguards that protect:

- data correctness;
- malformed responses;
- provider quota;
- request bounds;
- timeouts;
- retries;
- worker ownership;
- resource hashing;
- identity qualification;
- provenance;
- point-in-time correctness;
- semantic compatibility.

But remove or generalize policy-level restrictions whose sole justification is:

```text
not official enough for production
```

when they prevent permitted development acquisition.

Any code change must have tests.

---

# 8. RECORD THE OWNER DECISION DURABLY

Create or update the repository's current owner-decision mechanism.

Use existing project conventions.

The decision should state substantially:

```text
MATCHFORGE DEVELOPMENT DATA ACCESS POLICY

Status:
APPROVED

Scope:
Development, research, provider investigation, historical acquisition,
rich-data collection and live-data experimentation.

Decision:
MatchForge is not restricted to officially documented provider APIs.
Technically viable public football-data paths may be used, including
public browser endpoints, undocumented public JSON resources, public
web pages, community wrappers, maintained scrapers and reverse-engineered
public request formats.

Constraints:
Data must retain source provenance and acquisition time.
Canonical use still requires applicable identity, semantic and PIT
qualification.
Do not fabricate access or observations.
Do not rewrite historical evidence.
Do not infer that an official API is required.

Non-scope:
This decision does not alter MatchForge's own application/admin access policy.
```

If the repository uses append-only owner decisions, follow that mechanism.

---

# 9. EXISTING PROVIDERS FIRST

Before spending substantial effort on new adapters, audit and maximize useful data already available from providers MatchForge currently uses.

Priority:

```text
1. retained data already present
2. fields present in existing payloads but ignored
3. resources already downloaded but discarded
4. provider endpoints already known but unused
5. additional publicly accessible endpoints from existing providers
6. deeper history from existing providers
7. cross-provider completion using current sources
8. eight already-mandated new sources
9. additional providers only if still necessary
```

Existing-provider expansion remains mandatory.

---

# 10. EIGHT MANDATED ADDITIONAL SOURCE INTEGRATIONS

The following remain mandatory implementation/investigation targets:

1. Understat
2. ClubElo
3. Sofascore
4. ESPN
5. FBref
6. WhoScored
7. Flashscore
8. Soccerway

Do not arbitrarily reduce this list.

Do not treat overlap as a reason to skip a provider.

Independent observations are useful for:

- coverage;
- validation;
- identity corroboration;
- conflict detection;
- historical depth;
- fallback;
- live reconciliation;
- semantic comparison.

---

# 11. MANDATORY DOES NOT MEAN BLIND

For each of the eight:

1. inspect current source;
2. inspect proposed wrapper/library;
3. inspect maintained alternatives;
4. inspect current public website/network behavior where needed;
5. test bounded acquisition;
6. identify actual resource capabilities;
7. implement accessible useful resources;
8. record inaccessible resources precisely.

If the originally proposed wrapper is broken:

```text
DO NOT:
declare provider unavailable immediately
```

Instead:

```text
inspect current provider behavior
→ search maintained implementation
→ inspect normal public requests
→ test direct acquisition
→ implement a replacement adapter if reasonable
```

---

# 12. ADDITIONAL PROVIDERS BEYOND THE MANDATED EIGHT

Do not add arbitrary sources.

A ninth/new source should be considered only where:

```text
existing providers
+
eight mandated providers
```

cannot adequately satisfy a valuable data requirement.

Record:

- missing feature;
- required historical depth;
- competitions;
- player requirements;
- semantic requirements;
- why existing combinations are insufficient.

---

# 13. MISSION

Evolve MatchForge into a comprehensive provider-neutral football intelligence and probabilistic forecasting platform.

The system should progressively acquire, normalize, qualify and use:

- fixtures;
- results;
- periods;
- live match states;
- statistics;
- events;
- shots;
- shotmaps;
- xG;
- xGA;
- xGOT;
- lineups;
- appearances;
- player minutes;
- player match statistics;
- managers;
- formations;
- tactical context;
- referees;
- venues;
- injuries/suspensions where available;
- rest;
- congestion;
- travel;
- team-strength history;
- competition context;
- market-relevant outcomes.

---

# 14. SPORTYBET-STYLE MARKET COVERAGE OBJECTIVE

MatchForge should progressively support the major statistical outcome families visible on products such as SportyBet.

SportyBet is primarily:

- product taxonomy reference;
- market-definition reference;
- settlement-semantics reference where useful.

Do not assume SportyBet odds are football truth.

Desired categories include:

- match results;
- goals;
- halves;
- exact scores;
- handicaps;
- BTTS;
- corners;
- cards;
- shots;
- SOT;
- saves;
- fouls;
- offsides;
- player goals;
- assists;
- player shots;
- player SOT;
- passes;
- tackles;
- cards;
- goalkeeper props;
- team statistics;
- combination markets.

Only qualified markets may be published.

---

# 15. SELF-LEARNING ARCHITECTURE

The controlled loop is:

```text
ACQUIRE
→ VALIDATE
→ RECONCILE
→ QUALIFY
→ FEATURE
→ FORECAST
→ SEAL
→ OBSERVE
→ SETTLE
→ SCORE
→ CALIBRATE
→ DETECT DRIFT
→ TRAIN CHALLENGER
→ CHRONOLOGICAL BACKTEST
→ SHADOW
→ PROMOTION DECISION
```

Do not implement uncontrolled production self-modification.

---

# 16. SELF-CORRECTION

Use:

```text
detect conflict
→ retain original observations
→ quarantine affected canonical fact if necessary
→ acquire corroborating evidence
→ append correction/revocation/supersession
→ rebuild only permitted downstream state
```

Never silently rewrite history.

---

# 17. REPOSITORY RECONNAISSANCE

Before editing:

```bash
git status --short --branch
git rev-parse HEAD
git log -1 --format='%H %cI %s'
git diff --check
```

Read applicable:

- `AGENTS.md`;
- current project status;
- active R3 evidence;
- migrations;
- provider architecture;
- history machinery;
- live machinery;
- model contracts;
- market contracts;
- evaluation governance;
- Makefile/CI.

Do not assume historical SHAs in prompts are current.

---

# 18. CLASSIFY CURRENT IMPLEMENTATION

For each requested capability classify:

```text
VERIFIED_REUSED
REVALIDATION_REQUIRED
IMPLEMENT_AND_VERIFY
BLOCKED_WITH_RESUME_POINT
```

Do not duplicate working systems.

---

# 19. R3 REMAINS FOUNDATIONAL

Continue resolving:

- competition identities;
- team identities;
- player identities where needed;
- fixture identities;
- independently correctable contradictions;
- pending history scopes;
- historical qualification;
- false insufficient-data cases.

Never:

- use names alone as proof;
- backdate identity decisions;
- force merges;
- bulk-trust unresolved entities;
- rewrite source evidence.

Provider exploration/raw acquisition may continue while individual identity cases remain blocked.

Canonical use waits for qualification.

---

# 20. R3 PRIORITIZATION

Prioritize identities according to:

```text
upcoming forecast impact
+
historical rows unlocked
+
rich resource rows unlocked
+
market families unlocked
+
strength of corroborating evidence
```

This prevents spending disproportionate effort on low-value mappings while large supported leagues remain blocked.

---

# 21. PROGRAMME ARTIFACTS

Create/reuse:

```text
.local/v4-market-intelligence/
├── IMPLEMENTATION_MANIFEST.json
├── PROGRESS.md
├── DATA_ACCESS_POLICY_RECONCILIATION.json
├── R3_STATUS.json
├── PROVIDER_CAPABILITY_REGISTRY.json
├── PROVIDER_DATA_GAP_MATRIX.json
├── MARKET_DATA_REQUIREMENTS.json
├── MARKET_CAPABILITY_REGISTRY.json
├── FEATURE_HISTORY_DEPTH.json
├── MARKET_SEMANTIC_COMPATIBILITY.json
├── PLAYER_IDENTITY_COVERAGE.json
├── MARKET_OUTCOME_COVERAGE.json
├── DATA_COLLECTION_PLAN.json
├── MANDATED_PROVIDER_STATUS.json
├── NEW_PROVIDER_REQUIREMENTS.json
├── SELF_LEARNING_ARCHITECTURE.md
├── decisions/
├── evidence/
└── phases/
```

Reference immutable evidence instead of copying it.

---

# 22. DATA ACCESS POLICY RECONCILIATION ARTIFACT

Create:

```text
DATA_ACCESS_POLICY_RECONCILIATION.json
```

Include:

- files searched;
- contradictory current-policy text found;
- code assumptions found;
- historical records intentionally preserved;
- current documents updated;
- source-policy code changed if any;
- tests updated;
- explicit confirmation that MatchForge internal admin/auth behavior was not changed by this decision.

---

# 23. PROVIDER CAPABILITY REGISTRY

For each provider/resource:

```json
{
  "provider": "",
  "feature_family": "",
  "provider_field_or_endpoint": "",
  "access_path": "",
  "access_classification": "",
  "available": "YES|NO|UNKNOWN",
  "currently_requested": false,
  "currently_retained": false,
  "currently_normalized": false,
  "currently_qualified": false,
  "currently_modeled": false,
  "historical_depth": null,
  "competition_coverage": [],
  "player_identity_required": false,
  "point_in_time_semantics": "",
  "semantic_definition": "",
  "status": "",
  "blocker": null,
  "evidence": []
}
```

`access_classification` should distinguish:

```text
OFFICIAL_API_SUPPORTED
PUBLIC_JSON_ENDPOINT_ACCESSIBLE
PUBLIC_WEB_ENDPOINT_ACCESSIBLE
COMMUNITY_WRAPPER_ACCESSIBLE
PUBLIC_HTML_SCRAPABLE
OPEN_DATASET_AVAILABLE
RETAINED_DATA_AVAILABLE
CURRENTLY_INACCESSIBLE
UNKNOWN
```

---

# 24. CAPABILITY STATES

Use/reconcile with existing repository terminology:

```text
QUALIFIED
PARTIAL
AVAILABLE_AND_INGESTED
AVAILABLE_NOT_INGESTED
FETCHED_NOT_PERSISTED
RETAINED_NOT_NORMALIZED
NORMALIZED_NOT_QUALIFIED
QUALIFIED_NOT_MODELED
SEMANTIC_MISMATCH
INSUFFICIENT_HISTORY
CURRENTLY_INACCESSIBLE
UNKNOWN
```

Do not mark an unofficial/public source inaccessible merely because it is unofficial.

---

# 25. PHASE 1 — EXISTING PROVIDER CAPABILITY AUDIT

Audit every currently registered provider.

At minimum:

- FotMob;
- PitchAPI;
- API-Football;
- football-data.org;
- Football-Data.co.uk;
- OpenFootball;
- StatsBomb where relevant;
- every provider discovered at HEAD.

Ask:

```text
WHAT EXISTS?
WHAT IS ACCESSIBLE?
WHAT DO WE FETCH?
WHAT DO WE RECEIVE?
WHAT DO WE KEEP?
WHAT DO WE DISCARD?
WHAT DO WE NORMALIZE?
WHAT DO WE QUALIFY?
WHAT DO WE MODEL?
```

---

# 26. FOTMOB — DEEP AUDIT

Inspect actual accessible resources for:

### Fixture

- schedules;
- results;
- statuses;
- periods;
- competition;
- season;
- venue;
- referee.

### Match stats

Potentially:

- possession;
- shots;
- SOT;
- blocked shots;
- off-target;
- corners;
- fouls;
- cards;
- offsides;
- saves;
- big chances;
- passing;
- tackling;
- interceptions;
- clearances;
- xG;
- xGOT.

Discover actual fields rather than assuming.

### Events

- goals;
- penalties;
- own goals;
- cards;
- substitutions;
- VAR;
- disallowed goals;
- minute;
- added time;
- player/team.

### Shotmaps

Where accessible:

- player;
- coordinates;
- situation;
- body part;
- shot type;
- xG;
- xGOT;
- result;
- assist relationship;
- score state.

### Lineups/player stats

- starters;
- substitutes;
- formation;
- player IDs;
- positions;
- minutes;
- match stats.

### History

Use dynamic season discovery per competition.

Measure feature depth independently.

---

# 27. API-FOOTBALL

Inspect both documented and actually accessible capabilities under the current project credentials/plan.

Potential resources:

- fixtures;
- results;
- events;
- statistics;
- lineups;
- players;
- injuries;
- formations;
- managers;
- standings;
- cards;
- corners;
- shots;
- saves;
- venue;
- referee.

Do not stop at documentation.

Actually test bounded requests.

Record plan limitations accurately.

---

# 28. FOOTBALL-DATA.CO.UK

Inspect historical fields such as:

- FT;
- HT;
- shots;
- SOT;
- corners;
- fouls;
- offsides;
- yellow/red;
- referee;
- other stable metrics.

Version provider semantic changes over time.

---

# 29. PITCHAPI

Audit retained/current capabilities:

- fixtures;
- results;
- shots;
- xG;
- penalties;
- situations;
- teams;
- players where available;
- events;
- rich data already retained.

Do not reopen frozen evaluations merely because new data is discovered.

---

# 30. FOOTBALL-DATA.ORG / OPENFOOTBALL

Use for:

- fixtures;
- results;
- competitions;
- teams;
- schedules;
- standings where available;
- identity corroboration;
- historical history.

Inspect any additional useful public resources.

---

# 31. STATSBOMB

Use within existing dataset/evaluation governance.

Potentially:

- events;
- shots;
- xG;
- lineups;
- player data;
- location/sequence information.

Do not expose protected evaluation targets.

---

# 32. EXISTING PROVIDER EXPANSION

For useful resource gaps:

1. identify access path;
2. implement/reuse adapter;
3. fetch bounded sample;
4. retain immutable source data;
5. hash/register;
6. preserve native IDs;
7. normalize;
8. qualify;
9. test;
10. measure.

Do not invent zeroes for missing fields.

---

# 33. PUBLIC ENDPOINT / SCRAPER ENGINEERING

Where a provider does not expose a suitable official API but public resources exist:

Codex may:

- inspect normal browser requests;
- inspect page bootstrap JSON;
- inspect public XHR/fetch endpoints;
- inspect open-source wrappers;
- inspect scraper implementations;
- implement direct HTTP acquisition;
- parse public HTML;
- reproduce ordinary request parameters;
- maintain local cache;
- implement pagination;
- implement retry/cooldown;
- detect response schema changes.

Prefer the simplest maintainable path.

Do not introduce headless-browser infrastructure unless simpler HTTP acquisition is insufficient and the existing development environment justifies it.

---

# 34. WRAPPER POLICY

Open-source wrappers are acquisition references, not architecture authorities.

For each wrapper:

- inspect code;
- understand requests;
- evaluate maintenance;
- evaluate dependencies;
- reproduce only useful functionality where appropriate.

MatchForge may:

- depend on wrapper;
- wrap wrapper;
- vendor small extraction logic where license permits;
- implement equivalent provider requests itself.

Do not force the project to retain a fragile dependency solely because a prompt originally named it.

---

# 35. EXISTING FIXTURE ENRICHMENT

For fixtures already in MatchForge but lacking rich data:

use verified provider fixture IDs to fetch:

- stats;
- events;
- shots;
- lineups;
- player data;
- other relevant resources.

Avoid blind full re-download.

Reuse:

- hashes;
- caches;
- scopes;
- quotas;
- cooldowns;
- worker fencing;
- cancellation.

---

# 36. PHASE 2 — UNDERSTAT

Investigate:

- current Understat public resources;
- `soccerdata` support;
- maintained alternatives;
- direct public HTTP acquisition.

Target:

- fixture results;
- team xG;
- shot xG;
- shot locations;
- shot outcome;
- shot situation;
- player attribution;
- attacking/defensive context.

Keep Understat source identity.

---

# 37. CLUB ELO

Investigate public ClubElo data.

Target:

- team rating;
- observation date;
- club identity;
- historical rating sequence.

Store ratings point-in-time.

Do not use future Elo observations for earlier forecasts.

---

# 38. SOFASCORE

Investigate:

- `soccerdata`;
- public web endpoints;
- maintained wrappers;
- direct HTTP routes.

Target accessible:

- fixtures;
- results;
- live state;
- statistics;
- events;
- shots;
- lineups;
- formations;
- players;
- player stats;
- standings;
- tournament/season metadata.

Sofascore should be treated as an important rich/live candidate, not rejected merely because the route is unofficial.

---

# 39. ESPN

Investigate accessible public data.

Target:

- schedules;
- results;
- live state;
- events;
- teams;
- players;
- statistics;
- competition context.

Measure actual coverage by competition.

---

# 40. FBREF

Investigate:

- `soccerdata`;
- publicly accessible pages/data;
- stable table extraction.

Target:

- team statistics;
- player statistics;
- shooting;
- passing;
- defending;
- goalkeeping;
- match logs;
- competition/season data.

Retain table/schema version because columns may change.

---

# 41. WHOSCORED

Investigate current technically viable public acquisition routes.

Target where accessible:

- match events;
- formations;
- tactical context;
- player positions;
- player actions;
- team statistics;
- match statistics.

Do not reject merely because acquisition is through public-page extraction rather than an official API.

Record exact blockers where technically inaccessible.

---

# 42. FLASHSCORE

Inspect:

- existing proposed scraper;
- maintained alternatives;
- current public web data path.

Target:

- live scores;
- status;
- clock;
- fixtures;
- historical matches;
- period results;
- events;
- cards;
- substitutions;
- stats;
- lineups;
- standings.

Measure reliability carefully for live use.

---

# 43. SOCCERWAY

Inspect:

- existing proposed project;
- direct public acquisition;
- maintained alternatives.

Target:

- historical fixtures;
- results;
- competition/season history;
- team history;
- match stats where available;
- historical gaps;
- live state only when verified.

Reuse acquisition ideas, not the upstream prediction model.

---

# 44. MANDATED PROVIDER COMPLETION

A mandated provider may finish as:

```text
FUNCTIONAL
PARTIAL_FUNCTIONAL
CURRENTLY_INACCESSIBLE
```

`CURRENTLY_INACCESSIBLE` requires evidence.

It cannot mean simply:

```text
no official API
```

---

# 45. PHASE 3 — CANONICAL IDENTITY / PROVENANCE

Preserve provider-native identities for:

- competition;
- season;
- team;
- fixture;
- player;
- manager;
- referee.

Canonical identity cannot rely on names alone.

Handle:

- aliases;
- renamed clubs;
- duplicate names;
- transfers;
- provider ID variation;
- reschedules;
- orientation differences;
- contradictory scores.

---

# 46. PLAYER IDENTITY

Build/reuse first-class player identity.

Use evidence including:

- provider ID;
- team;
- competition;
- season;
- lineup;
- fixture overlap;
- birth date where available;
- position;
- explicit crosswalk.

Transfers are time-aware.

---

# 47. RAW PROVENANCE

Retain where practical:

- source;
- source URL/identifier;
- provider IDs;
- raw bytes/text;
- checksum;
- parser version;
- request timestamp;
- acquisition timestamp;
- source-reported timestamp;
- football event timestamp;
- normalization version.

Public scraping does not remove provenance requirements.

---

# 48. PHASE 4 — FEATURE-AWARE HISTORICAL ACQUISITION

Use durable scope:

```text
provider
competition
season
feature_family
```

Prioritize:

1. results;
2. period scores;
3. match stats;
4. corners/cards/shots/SOT;
5. player appearances/minutes;
6. player detailed stats;
7. events;
8. shotmaps;
9. xG/xGOT;
10. lineups;
11. managers/referees;
12. Elo;
13. other market-relevant features.

---

# 49. BACKFILL PIPELINE

Use:

```text
DISCOVER
→ RETAINED CHECK
→ FETCH
→ HASH
→ REGISTER
→ PARSE
→ NORMALIZE
→ IDENTITY
→ SEMANTICS
→ QUALIFY
→ STORE
→ COVERAGE
```

Do not call a download successful coverage until downstream qualification is known.

---

# 50. HISTORICAL DEPTH

Measure per:

```text
provider
competition
season
feature
```

Report:

- earliest available;
- latest;
- fixtures;
- rows;
- teams;
- players;
- missingness;
- semantic consistency;
- identity coverage;
- PIT usability.

---

# 51. POINT-IN-TIME RULES

Keep separate:

- football event time;
- public observation time where knowable;
- acquisition time;
- admission time;
- knowledge cutoff.

Newly acquired old data is not automatically retrospectively known to MatchForge.

Post-match target data never enters that match's pre-match features.

---

# 52. CANONICAL RICH DATA

Reuse or extend current structures for:

```text
MATCH_STATISTICS
EVENTS
SHOTMAP
LINEUP
PLAYER_MATCH_STATISTICS
TEAM_STATISTICS
INJURIES
MANAGERS
REFEREES
TEAM_RATING
```

Do not create duplicate stores unnecessarily.

---

# 53. MATCH STATS

Support where available:

- corners;
- shots;
- SOT;
- blocked;
- big chances;
- possession;
- passes;
- accurate passes;
- crosses;
- fouls;
- offsides;
- saves;
- tackles;
- interceptions;
- cards;
- throw-ins;
- goal kicks;
- woodwork;
- additional verified metrics.

---

# 54. PERIOD STATISTICS

Distinguish:

- H1;
- H2;
- regulation;
- ET;
- full event including ET where explicitly defined.

Never mathematically split full-match observations and represent them as observed half statistics.

---

# 55. SHOT OBSERVATIONS

Where available retain:

- shooter;
- team;
- period/minute;
- coordinates;
- body part;
- situation;
- result;
- SOT;
- xG;
- xGOT;
- assist/pass relation;
- score state;
- source event ID.

---

# 56. PLAYER OBSERVATIONS

Where available:

- starts;
- bench;
- minutes;
- position;
- goals;
- assists;
- shots;
- SOT;
- xG/xA;
- passes;
- key passes;
- tackles;
- interceptions;
- fouls;
- cards;
- saves.

Missing ≠ zero.

---

# 57. CONTEXT

Acquire/qualify where possible:

- manager;
- appointment dates;
- tactical style;
- formation;
- predicted lineup;
- confirmed lineup;
- injuries;
- suspension;
- referee;
- venue;
- rest;
- congestion;
- travel;
- historical strength.

---

# 58. MANAGER INTELLIGENCE

Preserve the existing manager-intelligence objective.

Collect when obtainable:

- manager identity;
- tenure;
- formations;
- preferred formation;
- formation frequency;
- tactical characteristics;
- pressing;
- possession;
- directness;
- defensive shape;
- substitutions;
- manager vs manager;
- manager vs opponent;
- cup vs league tendencies;
- squad usage;
- lineup continuity.

Use multiple sources where useful.

---

# 59. LINEUP SEMANTICS

Distinguish:

```text
PREDICTED
PROBABLE
CONFIRMED
ACTUAL_STARTERS
HISTORICAL_FALLBACK
UNKNOWN
```

Actual lineup information after forecast cutoff cannot leak into previous forecasts.

---

# 60. SEMANTIC REGISTRY

For every statistic/model target define:

- source meaning;
- canonical meaning;
- period;
- inclusion/exclusion;
- ET handling;
- penalty handling;
- player participation;
- corrections;
- void/incomplete conditions;
- compatible sources.

Compatibility:

```text
EXACT_OR_VERIFIED_EQUIVALENT
TRANSFORMABLE_WITH_EVIDENCE
NORMALIZABLE
RESEARCH_COMPATIBLE_ONLY
INCOMPATIBLE
UNKNOWN
```

---

# 61. SPORTYBET / OPTA SEMANTICS

Where MatchForge wants a market analogous to SportyBet:

create a versioned target contract.

Examples:

```text
TOTAL_CORNERS_V1
PLAYER_SHOTS_ON_TARGET_V1
PLAYER_TACKLES_V1
GOALKEEPER_SAVES_V1
```

Do not assume provider definitions match sportsbook settlement definitions.

---

# 62. MARKET CAPABILITY REGISTRY

Each market needs:

- ID;
- target version;
- required observations;
- identity requirements;
- feature requirements;
- providers;
- history;
- competition coverage;
- semantic compatibility;
- model;
- calibration;
- evaluation;
- publication state;
- blocker.

---

# 63. MARKET STATUS

Operational:

```text
SUPPORTED
SHADOW
RESEARCH
ENGINEERING_READY
UNAVAILABLE
DISABLED
BLOCKED
```

Reasons:

```text
DATA_COLLECTION_REQUIRED
INSUFFICIENT_HISTORY
INSUFFICIENT_PLAYER_DATA
SEMANTIC_MISMATCH
INSUFFICIENT_LINEUP_CONFIDENCE
UNVERIFIED_IDENTITY
INCOMPLETE_LABELS
UNQUALIFIED_MODEL
CALIBRATION_FAILURE
PROVIDER_UNAVAILABLE
RESEARCH_REQUIRED
```

---

# 64. GOAL/RESULT MARKETS

Support coherently from the score distribution where possible:

- 1X2;
- DC;
- DNB;
- exact score;
- goals O/U;
- team totals;
- BTTS;
- clean sheet;
- winning margin;
- goal range;
- compatible handicaps;
- result × totals;
- result × BTTS.

Do not unnecessarily model these independently.

---

# 65. PERIOD MARKETS

Target:

- H1 result;
- H1 totals;
- H1 team totals;
- H1 BTTS;
- H2 result;
- H2 totals;
- HT/FT;
- most-goals half;
- scoring intervals.

Use real period data/models.

Do not divide FT goal intensity by two blindly.

---

# 66. CORNERS

Reuse current corner architecture.

Develop from qualified data:

- total corners;
- team corners;
- H1 corners;
- handicaps;
- corner races;
- ranges.

Candidate models:

- Poisson;
- Negative Binomial;
- hierarchical counts;
- time-aware count models;
- correlated counts.

Evidence decides.

---

# 67. CARDS

Potential features:

- team discipline;
- opponent style;
- referee;
- competition;
- tactical matchup;
- game state.

Potential markets:

- total;
- team;
- halves;
- handicap;
- card points;
- player card.

Use appropriate count/event distributions.

---

# 68. SHOTS / SOT

Build separate qualified models for:

- team shots;
- team SOT;
- player shots;
- player SOT.

Do not derive all shot products solely from goal intensity.

---

# 69. OTHER TEAM STATISTICS

Where coverage permits:

- fouls;
- offsides;
- saves;
- tackles;
- throw-ins;
- goal kicks;
- woodwork.

Do not force every variable into one statistical distribution family.

---

# 70. PLAYER PARTICIPATION

First estimate:

- start probability;
- substitute probability;
- nonappearance;
- expected minutes;
- role.

Then model conditional player event production.

---

# 71. PLAYER MARKETS

Potentially:

- goals;
- assists;
- shots;
- SOT;
- passes;
- tackles;
- fouls;
- cards;
- saves.

Inputs may include:

- expected minutes;
- position;
- tactical role;
- opponent;
- team strength;
- formation;
- historical usage;
- availability;
- transfers;
- cold-start priors.

---

# 72. JOINT MARKET MODELING

Do not multiply correlated probabilities naïvely.

Dependencies include:

- result × goals;
- goals × corners;
- goals × cards;
- corners × cards;
- shots × SOT;
- player shots × team shots;
- player goals × team goals;
- fouls × cards;
- participation × player events.

Use validated dependency models.

---

# 73. LIVE MULTI-PROVIDER SYSTEM

Evaluate:

- FotMob;
- PitchAPI;
- API-Football;
- Sofascore;
- ESPN;
- Flashscore;
- Soccerway where capable;
- any other verified live provider.

Do not assume Understat/ClubElo/FBref/WhoScored are live sources without evidence.

---

# 74. LIVE OBSERVATIONS

Normalize:

- status;
- period;
- minute;
- added time;
- score;
- HT;
- ET;
- penalties;
- events;
- cards;
- substitutions;
- live statistics;
- provider observation time;
- acquisition time;
- freshness.

---

# 75. LIVE RECONCILIATION

Handle:

- stale source;
- conflicting score;
- conflicting clock;
- delayed update;
- disallowed goal;
- suspension;
- interruption;
- postponement;
- abandonment;
- ET;
- shootout;
- correction.

Retain all evidence.

---

# 76. PROVIDER FALLBACK

Use:

1. identity confidence;
2. competition support;
3. capability;
4. freshness;
5. success;
6. historical reliability;
7. cost/quota/cooldown.

No single provider should be hardcoded as universally authoritative where multi-provider evidence exists.

---

# 77. FEATURE ENGINEERING

Potential team features:

- league environment;
- league home advantage;
- team attack;
- team defence;
- opponent-adjusted form;
- Elo;
- rest;
- congestion;
- travel;
- manager;
- tactics;
- referee;
- formation;
- rivalry;
- cup/league distinction.

All features must be label-safe and PIT-safe.

---

# 78. INTERACTIONS

Potential preregistered interactions:

- manager × opponent manager;
- tactics × opponent formation;
- availability × tactical role;
- referee × team discipline;
- rest × squad depth;
- league environment × team strength.

A feature rejected alone may still contribute through a justified interaction.

Do not mine sealed outcomes.

---

# 79. FORECAST ARTIFACTS

Every supported market forecast must retain:

- fixture;
- market;
- market version;
- model;
- calibration;
- feature snapshot;
- training/data version;
- cutoff;
- issue time;
- distribution;
- uncertainty;
- provenance;
- hashes;
- revision lineage.

Published forecasts are immutable.

---

# 80. OUTCOME SETTLEMENT

After matches:

```text
collect
→ verify identity
→ verify semantics
→ reconcile
→ settle
→ score
→ calibrate
→ drift analysis
```

Corrections append new settlement revisions.

---

# 81. SELF-LEARNING REGISTRY

Store logically equivalent:

```text
forecast_id
market
market_version
prediction
issue_time
knowledge_cutoff
actual_outcome
outcome_source
semantic_version
verified_at
evaluation_status
```

Never mutate the original prediction.

---

# 82. METRICS

Categorical:

- log loss;
- Brier;
- RPS;
- calibration.

Count:

- count likelihood;
- CRPS;
- mean calibration;
- variance calibration;
- threshold calibration;
- tail calibration.

Player markets separately score:

- participation;
- performance conditional on participation.

---

# 83. DRIFT

Detect:

- model calibration drift;
- feature drift;
- league drift;
- team-strength drift;
- provider-definition drift;
- missingness drift;
- coverage drift.

Drift triggers challenger/review.

It does not change the champion automatically.

---

# 84. CHALLENGER PIPELINE

Use:

```text
new qualified data
→ immutable dataset
→ chronological split
→ candidate
→ development evaluation
→ validation
→ frozen candidate
→ authorized final evaluation
→ shadow
→ promotion decision
```

No auto-promotion.

---

# 85. SCIENTIFIC FIREWALL

Before authoritative evaluation freeze:

- hypothesis;
- features;
- labels;
- model;
- baseline;
- split;
- metrics;
- required coverage;
- calibration criteria;
- stopping rule;
- promotion criteria.

No target/post-match leakage.

---

# 86. API / FRONTEND / ADMIN

Reuse current systems.

Do not create duplicate APIs.

Expose:

- live state;
- market capability;
- probabilities;
- blockers;
- model;
- cutoff;
- horizon;
- semantics;
- uncertainty;
- context.

Frontend should organize:

- goals;
- halves;
- corners;
- cards;
- shots/stats;
- players;
- combinations;
- live/context.

Do not display empty unsupported markets as if predictions exist.

---

# 87. ADMIN DATA OPERATIONS

Extend existing admin/data-sync controls for:

- fixtures;
- historical data;
- rich match stats;
- players;
- events;
- shots;
- lineups;
- live data;
- provider health;
- coverage;
- feature depth;
- request activity;
- retries;
- cancellations;
- identity review;
- market readiness;
- model/evaluation status.

Do not alter MatchForge's existing internal admin authorization merely because this prompt expands external data access.

---

# 88. PROVIDER TESTS

Test:

- sample retrieval;
- cache;
- pagination;
- malformed data;
- changed schema;
- missing field;
- empty data;
- retry;
- timeout;
- response codes;
- duplicate resource;
- resume;
- rate limits;
- provider failure isolation.

For scraper/public-endpoint adapters also test:

- HTML/layout changes;
- missing bootstrap state;
- endpoint shape changes;
- alternate field representations.

---

# 89. IDENTITY TESTS

Cover:

- same names;
- renamed teams;
- transfers;
- duplicate player names;
- competition mismatch;
- provider-ID changes;
- fixture rescheduling;
- orientation conflicts;
- conflicting scores;
- correction lineage.

---

# 90. PIT TESTS

Cover:

- newly acquired old history;
- late xG;
- later lineups;
- corrections;
- post-match exclusion;
- same-kickoff batches;
- protected outcomes.

---

# 91. MARKET DATA TESTS

Cover:

- missing vs zero;
- period;
- semantics;
- shot/SOT consistency;
- player attribution;
- participation;
- ET;
- cards;
- official corrections;
- incompatible provider labels.

---

# 92. LIVE TESTS

Cover:

- scheduled;
- live;
- H1;
- HT;
- H2;
- added time;
- ET;
- penalties;
- final;
- suspended;
- postponed;
- abandoned;
- conflict;
- stale;
- fallback;
- correction.

---

# 93. MODEL TESTS

Cover:

- normalization;
- numerical stability;
- coherence;
- half/full compatibility;
- player/team marginals;
- dependency models;
- cold start;
- calibration;
- artifact reproducibility;
- unsupported-market suppression.

---

# 94. PERFORMANCE

Prevent:

- repeated public-page downloads;
- unbounded scraping;
- N+1 provider calls;
- repeated immutable retrieval;
- giant DB transactions;
- one DB transaction per stat;
- full historical rescans;
- repeated model loading.

Use:

- bounded requests;
- cache;
- content hashes;
- scopes;
- checkpoints;
- incremental processing;
- request scheduling.

---

# 95. PROVIDER POLITENESS / RESOURCE CONTROL

Even in development:

- use caching;
- avoid unnecessary repeated retrieval;
- use bounded concurrency;
- reuse immutable resources;
- use sensible delays/cooldowns where needed;
- stop retry storms;
- isolate provider failure.

This is operational correctness, not a prohibition on public-data access.

---

# 96. REQUIRED PROVIDER REPORT

For all existing and new providers report:

| Field                   | Meaning                                                 |
| ----------------------- | ------------------------------------------------------- |
| Provider                | Source identity                                         |
| Access class            | Official/Public endpoint/Wrapper/Scraper/Open data/etc. |
| Fixtures                | capability                                              |
| Stats                   | capability                                              |
| Events                  | capability                                              |
| Shots                   | capability                                              |
| xG                      | capability                                              |
| xGOT                    | capability                                              |
| Lineups                 | capability                                              |
| Player data             | capability                                              |
| Manager/tactics         | capability                                              |
| Live                    | capability                                              |
| Earliest usable history | measured                                                |
| Competition coverage    | measured                                                |
| Qualification           | measured                                                |
| Blocker                 | precise                                                 |

---

# 97. REQUIRED MANDATED PROVIDER REPORT

For each of the eight report:

- acquisition implementation;
- access classification;
- resources;
- history;
- competitions;
- live capability;
- player support;
- semantic quality;
- identity quality;
- tests;
- blocker;
- incremental value.

`CURRENTLY_INACCESSIBLE` must contain actual technical evidence.

---

# 98. REQUIRED MARKET REPORT

For each market family:

- operational state;
- blocker;
- required data;
- sources;
- history;
- coverage;
- semantics;
- model;
- calibration;
- evaluation;
- next action.

---

# 99. ADDITIONAL PROVIDER REQUIREMENTS

Only after existing + eight mandated provider work create:

```text
NEW_PROVIDER_REQUIREMENTS.json
```

Include only truly unresolved data gaps.

---

# 100. REQUIRED POLICY REPORT

In the final report include a dedicated section:

## Data-access policy reconciliation

Report:

1. current owner decision recorded;
2. current authoritative docs updated;
3. contradictory docs corrected;
4. historical evidence intentionally preserved;
5. code restrictions removed/generalized, if any;
6. provider adapters affected;
7. tests added/changed;
8. confirmation that MatchForge internal application/admin access-control behavior was not changed by this decision.

---

# 101. PHASE EXECUTION ORDER

Execute:

### Phase A — Policy and current state

1. inspect repository;
2. reconcile R3 state;
3. locate data-access policy conflicts;
4. record new owner decision;
5. update current authoritative docs;
6. preserve historical evidence;
7. update source-policy code assumptions where genuinely necessary;
8. verify MatchForge internal admin access remains unaffected.

### Phase B — R3 high-value identity

9. resolve high-value competition identities;
10. resolve team identities;
11. resolve player identities as needed;
12. resolve fixture representations;
13. resume unlocked history.

### Phase C — Existing providers

14. audit every existing source;
15. inspect ignored payload fields;
16. inspect unused endpoints;
17. inspect additional public provider resources;
18. implement useful collection;
19. measure history by feature.

### Phase D — Eight mandated integrations

20. Understat;
21. ClubElo;
22. Sofascore;
23. ESPN;
24. FBref;
25. WhoScored;
26. Flashscore;
27. Soccerway.

### Phase E — Canonical rich football data

28. normalize;
29. provenance;
30. identity;
31. backfill;
32. player identity;
33. semantics;
34. capability registry.

### Phase F — Live

35. live discovery;
36. source fallback;
37. reconciliation;
38. UI integration.

### Phase G — Forecasting

39. current goal products;
40. halves;
41. manager/tactical features;
42. corners;
43. cards;
44. shots/statistics;
45. player participation;
46. player props;
47. combination models.

### Phase H — Learning

48. settlement;
49. scoring;
50. calibration;
51. drift;
52. challenger pipeline.

### Phase I — Product/operations

53. API;
54. frontend;
55. admin/data tooling.

### Phase J — Verification

56. full tests;
57. integration;
58. coverage measurements;
59. final market-capability report;
60. additional-provider gap report.

---

# 102. DO NOT STOP AT PLANNING

Implement all unblocked engineering work.

Do not respond with only:

- architecture notes;
- TODOs;
- suggested providers;
- proposed schema.

Actual implementation, tests and evidence are required.

---

# 103. FINAL DELIVERABLES

At minimum:

```text
DATA_ACCESS_POLICY_RECONCILIATION.json
PROVIDER_CAPABILITY_REGISTRY.json
PROVIDER_DATA_GAP_MATRIX.json
MARKET_DATA_REQUIREMENTS.json
MARKET_CAPABILITY_REGISTRY.json
FEATURE_HISTORY_DEPTH.json
DATA_COLLECTION_PLAN.json
EXISTING_PROVIDER_EXPANSION_RESULTS.json
MANDATED_PROVIDER_STATUS.json
PLAYER_IDENTITY_COVERAGE.json
MARKET_SEMANTIC_COMPATIBILITY.json
MARKET_OUTCOME_COVERAGE.json
NEW_PROVIDER_REQUIREMENTS.json
SELF_LEARNING_ARCHITECTURE.md
FINAL_MARKET_DATA_REPORT.md
FINAL_IMPLEMENTATION_REPORT.md
```

Update only necessary durable docs.

Keep `PLAN.md` concise.

---

# 104. FINAL REPORT

Return:

1. branch;
2. starting SHA;
3. ending SHA;
4. owner data-access decision;
5. current docs changed;
6. historical docs deliberately left immutable;
7. code policy assumptions changed;
8. confirmation internal MatchForge access-control behavior was not changed;
9. R3 status;
10. unresolved identities;
11. existing providers audited;
12. existing-provider capabilities newly discovered;
13. existing provider endpoints/resources newly implemented;
14. eight mandated provider dispositions;
15. provider access classifications;
16. historical coverage;
17. feature-specific depth;
18. competitions;
19. players;
20. manager/tactical coverage;
21. live coverage;
22. live fallback;
23. semantic compatibility;
24. markets supported;
25. shadow markets;
26. research markets;
27. data-blocked markets;
28. semantic-blocked markets;
29. existing models reused;
30. new models engineered;
31. scientific evaluations performed;
32. outcome settlement;
33. drift detection;
34. challenger pipeline;
35. API changes;
36. frontend changes;
37. admin/data tooling changes;
38. tests;
39. regressions;
40. additional provider requirements;
41. remaining blockers;
42. exact next action.

---

# 105. FINAL ACCEPTANCE — DATA ACCESS POLICY

Require:

- official API status is no longer treated as the sole definition of source usability;
- public endpoints may be used;
- public website acquisition may be used;
- community wrappers may be used;
- maintained scrapers may be used;
- public request formats may be investigated/reimplemented;
- access class is explicit;
- source provenance remains intact;
- no fabricated data;
- current authoritative docs match this policy;
- historical evidence is not rewritten;
- MatchForge's own admin/application access control has not been mistakenly changed.

---

# 106. FINAL ACCEPTANCE — PROVIDERS

Require:

- all current providers audited;
- useful current-provider resources exploited;
- all eight mandated providers investigated/implemented;
- inaccessible provider claims have technical evidence;
- source identities remain distinct;
- raw data retained;
- historical work resumable.

---

# 107. FINAL ACCEPTANCE — DATA QUALITY

Require:

- canonical identity;
- semantics;
- source lineage;
- PIT integrity;
- feature-specific coverage;
- missing ≠ zero;
- incompatible source definitions not silently blended.

---

# 108. FINAL ACCEPTANCE — MARKETS

Require:

- existing goal markets remain coherent;
- period markets use appropriate period models;
- corners/cards/stats use qualified models;
- player markets include participation uncertainty;
- combination markets account for dependencies;
- unsupported markets output no fabricated probability.

---

# 109. FINAL ACCEPTANCE — SELF-LEARNING

Require:

- forecasts immutable;
- outcomes versioned;
- automatic scoring;
- calibration measurement;
- drift detection;
- reproducible challenger training;
- governed promotion;
- corrections append-only.

---

# 110. EXECUTE NOW

Start immediately:

1. inspect the current branch and applicable `AGENTS.md`;
2. verify R3/current repository state;
3. search the repository for data-access-policy wording contrary to this decision;
4. record the new owner data-access decision using existing governance;
5. update current authoritative docs and code comments accordingly;
6. preserve immutable/historical evidence rather than rewriting it;
7. confirm MatchForge internal admin/API access controls are unchanged;
8. identify policy-level code that blocks public/unofficial data solely because it is not an official API;
9. safely generalize those restrictions where necessary;
10. run focused tests for policy-related code changes;
11. continue R3 identity qualification;
12. audit every current provider;
13. inspect ignored fields and retained resources;
14. inspect unused official and public endpoints;
15. implement useful existing-provider acquisition;
16. build the provider capability registry;
17. measure feature-specific history;
18. implement all eight mandated sources;
19. use direct public acquisition when wrappers are inadequate and the resource is technically accessible;
20. retain and hash raw evidence;
21. normalize provider-neutral observations;
22. qualify identities;
23. qualify semantics;
24. perform bounded historical enrichment;
25. establish player identity;
26. build the market capability registry;
27. expand multi-provider live intelligence;
28. implement manager/tactical/context data;
29. implement qualified market models;
30. implement outcome settlement/evaluation/drift;
31. implement controlled challenger learning;
32. expose capabilities through existing API/frontend/admin systems;
33. run all applicable quality gates;
34. report actual before/after capability;
35. only then evaluate whether providers beyond the mandated eight are required.

**Do not treat “unofficial API” as synonymous with “unusable”.**

**Do not treat “website data” as automatically prohibited.**

**Do not reject a public endpoint solely because it is undocumented.**

**Do not reject a maintained scraper solely because it is a scraper.**

**Do not reject a community wrapper solely because the source does not provide an official SDK.**

**Actually test technically viable public acquisition paths.**

**Do not fabricate access when data genuinely cannot be obtained.**

**Do not confuse external football-data acquisition policy with MatchForge's own internal admin/API authorization.**

**Do not weaken identity, PIT, provenance, concurrency or scientific safeguards.**

**Do not rewrite historical evidence to make it agree with today's decision. Supersede it prospectively.**

**Do not stop after generating another plan. Execute the work.**

The intended result is a development-first MatchForge that uses the widest technically viable public football-data ecosystem, preserves rigorous provenance and point-in-time correctness, supports broad SportyBet-style statistical forecasting, learns systematically from outcomes, and is not artificially limited to officially documented production APIs.
