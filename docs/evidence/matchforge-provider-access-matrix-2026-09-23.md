# MatchForge provider access matrix — 2026-09-23

Status: `RESEARCH_ONLY`. Observed from official public pages on 2026-09-23.
No account was created, credential used, API called, provider contacted, file
downloaded, source ingested, or dataset admitted.

This sentence describes the initial public-only pass. The owner later confirmed
that credentials already existed and authorized a bounded follow-up. Its
sanitized results are recorded in the
[controlled API qualification report](matchforge-controlled-provider-api-qualification-2026-09-23.md).
No credential was created by MatchForge or exposed.

Authorization is recorded in
[the owner decision](owner-decision-authorize-multisource-provider-qualification-2026-09-23.md).
Initial historical scope is men's Bundesliga 2023/24 and Ligue 1 2022/23.

Status meanings:

- `VERIFIED`: stated by current official public evidence.
- `PARTIAL`: some required facts are verified, but the requirement is incomplete.
- `UNKNOWN`: no adequate official public evidence was found.
- `REJECTED`: available evidence fails the requirement.

## Summary

| Provider | Proposed role | Public qualification result | Acquisition allowed now | Blocking evidence |
| --- | --- | --- | --- | --- |
| football-data.org | Tier B fixtures/results | `PARTIAL` | Controlled probe complete; no further acquisition | Bundesliga 2023/24 is available; Ligue 1 2022/23 is denied; permanent raw-response retention remains unknown |
| API-Football | Tier B/C statistics/odds | `PARTIAL` | Controlled probe complete; no further acquisition | Both fixture lists are available and aggregate statistics were sampled; historical odds are unavailable and retention remains unknown |
| Football-Data.co.uk | Manual Tier B/C historical CSV | `PARTIAL — MANUAL ONLY` | No file download in this qualification | Candidate files are advertised, but model-training/reuse, immutable retention, exact completeness, and correction history are unresolved; automation is rejected |
| PitchAPI | Tier A shot xG | `PARTIAL; NOT QUALIFIED` | Controlled probe complete; no further acquisition | Both fixture lists are available and one Bundesliga match has shot xG; upstream model, full-season shots, rights, retention, corrections, and stable versions remain unproved |
| Understat | Fallback Tier A shot xG | `REJECTED FOR EVALUATION QUALIFICATION` | None; public-page research only | No official bulk/API permission, versioned shot export, explicit period field, model version, retention, or correction history |

No provider is approved for ingestion, canonical publication, a frozen-contract
change, model input, or Evaluation V2. No free source currently proves the two
remaining StatsBomb-compatible groups and 220 eligible targets.

## football-data.org

| Requirement | Status | Exact finding |
| --- | --- | --- |
| Cost | `VERIFIED` | Free plan is €0. Statistics and odds are separate €15/month add-ons and are outside the zero-purchase authorization. |
| Acquisition method | `VERIFIED` | Official REST API for competitions, matches, teams, standings, and related fixture/result resources. |
| Credentials | `VERIFIED` | Owner confirmed an existing ignored `.env` token. It was used only for the controlled follow-up and never exposed. |
| Limit | `VERIFIED` | Free authenticated plan: 10 calls/minute. Unauthenticated access: 100 requests/day and limited area/competition-list resources. |
| Free competitions | `VERIFIED` | Twelve competitions include Bundesliga and Ligue 1. This proves competition support, not historical-season entitlement. |
| Bundesliga 2023/24 | `UNKNOWN` | Public pricing does not prove this season is available to a free account. Ten-season history is advertised with a paid ML Pack. |
| Ligue 1 2022/23 | `UNKNOWN` | Same limitation. |
| Current fixtures/results | `VERIFIED` | Free plan advertises delayed fixtures, scores, schedules, and tables for covered competitions. Exact delay and season completeness need an account probe. |
| Free statistics/odds | `REJECTED` | Not included in the free plan. |
| IDs and time | `VERIFIED` | Match, team, and competition IDs; UTC kickoff; match status; and `lastUpdated` are documented. |
| Corrections/version history | `UNKNOWN` | `lastUpdated` marks a changed record but is not an immutable prior-version archive. No correction-history endpoint was found. |
| API permission | `VERIFIED` | Programmatic use is offered after registration and acceptance of provider terms and fair-use rules. |
| Attribution | `VERIFIED` | Required wording: “Football data provided by the Football-Data.org API”. |
| Raw-response retention | `UNKNOWN` | Public registration terms do not clearly grant permanent immutable internal retention after access or subscription ends. |
| Qualification result | `PARTIAL` | Suitable for a separately authorized current fixture/result account probe. Historical candidates and immutable retention remain blocked. |

Official sources:
[coverage](https://www.football-data.org/coverage),
[pricing](https://www.football-data.org/pricing),
[registration terms](https://www.football-data.org/client/register),
[API policies](https://docs.football-data.org/general/v4/policies.html), and
[match resource](https://docs.football-data.org/general/v4/match.html).

## API-Football / API-Sports

| Requirement | Status | Exact finding |
| --- | --- | --- |
| Cost | `VERIFIED` | Free plan is $0 and requires no payment card. |
| Acquisition method | `VERIFIED` | Official REST API. Public plan lists fixtures, events, lineups, statistics, pre-match odds, and in-play odds endpoint types. |
| Credentials | `VERIFIED` | Owner confirmed an existing ignored `.env` key. It was used only for the controlled follow-up and never exposed. |
| Published free limit | `VERIFIED` | 100 requests/day and 10 requests/minute. Dashboard daily quota resets at 00:00 UTC. |
| Account-specific limit/entitlement | `UNKNOWN` | Actual competition-season entitlement was not observed because no authorized account exists. Provider says free availability may change without notice. |
| Bundesliga 2023/24 | `UNKNOWN` | Public material says “recent seasons” but publishes no exact free depth. Authenticated league-season coverage metadata is required. |
| Ligue 1 2022/23 | `UNKNOWN` | Same limitation. |
| Statistics completeness | `UNKNOWN` | Endpoint type is included, but coverage varies by competition and season. |
| Odds completeness/history | `UNKNOWN` | Endpoint type is included, but public evidence does not prove candidate-season coverage, bookmaker completeness, capture times, or ended-match retention. |
| IDs/corrections | `UNKNOWN` | Provider IDs exist, but no public immutable revision or correction-history contract was found. Update frequencies are indicative rather than guaranteed. |
| API permission | `VERIFIED` | Terms permit API-based projects and prohibit direct resale. They do not grant rights in all underlying data. |
| Attribution | `UNKNOWN` | No general attribution requirement was found in the reviewed public terms. Absence of a rule is not a waiver. |
| Raw-response retention | `UNKNOWN` | Public terms do not clearly grant permanent immutable private-research retention after access ends. |
| Qualification result | `PARTIAL` | Strongest free statistics/odds candidate, but all candidate-specific values require separately authorized account metadata checks and retention clarification. |

Official sources:
[pricing](https://www.api-football.com/pricing),
[coverage overview](https://api-sports.io/sports/football),
[quota and coverage guidance](https://www.api-football.com/news/post/how-to-optimize-api-sports-calls-and-quota-usage), and
[terms](https://api-sports.io/terms).

## Football-Data.co.uk

| Requirement | Status | Exact finding |
| --- | --- | --- |
| Cost | `VERIFIED` | Public season CSVs are available without payment or an account. |
| Acquisition method | `PARTIAL` | Direct season CSVs exist. Owner authorization permits controlled manual research only. No file was downloaded. |
| Credentials | `VERIFIED` | None. |
| Automated access | `REJECTED` | Published data-page restriction excludes automated bot, scraper, and AI-based acquisition/use. Separate written permission and owner authorization are required. |
| Bundesliga 2023/24 | `PARTIAL` | Official Germany page advertises a season file with results, aggregate match statistics, match odds, total-goals odds, and Asian-handicap odds. Exact counts/nulls/duplicates were not checked. |
| Ligue 1 2022/23 | `PARTIAL` | Official France page advertises the same categories. Exact counts/nulls/duplicates were not checked. |
| Shot-level xG | `REJECTED` | Not supplied. |
| IDs | `REJECTED` | No stable provider match/team ID contract is published. Explicit MatchForge mappings are required. |
| Corrections/version history | `REJECTED` | Mutable current files have no snapshot version, row correction time, or prior-revision archive. Acquisition time and local hash cannot prove earlier provider versions. |
| Private research/model use | `UNKNOWN` | Site allows private-individual use but its restriction mentions data-training products. MatchForge model-training and long-term use require written clarification. |
| Attribution | `UNKNOWN` | No explicit downstream rule was found. Upstream data sources are named in field notes and must remain in source details. |
| Raw-file retention | `UNKNOWN` | No explicit permanent immutable internal-retention grant was found. |
| Qualification result | `PARTIAL — MANUAL ONLY` | Candidate files are advertised, but permission, retention, exact completeness, and reproducibility remain blocked. |

Official sources:
[data and use notice](https://football-data.co.uk/data),
[Germany seasons](https://football-data.co.uk/germanym.php),
[France seasons](https://football-data.co.uk/francem.php), and
[field notes](https://football-data.co.uk/notes.txt).

## PitchAPI

| Requirement | Status | Exact finding |
| --- | --- | --- |
| Cost | `VERIFIED` | Provider advertises no charge, card, trial, or expiry. |
| Acquisition method | `VERIFIED` | Official HTTPS REST API returning JSON; official Python client is documented. |
| Credentials | `VERIFIED` | Owner confirmed an existing ignored `.env` token. It was used only for the controlled follow-up and never exposed. |
| Limit | `PARTIAL` | Provider advertises no daily allowance. An undisclosed burst guard returns `429` with `Retry-After`; numeric ceiling is unknown. |
| Shot-level pre-shot xG | `VERIFIED` | `shots[].expected_goals`, range `[0, 1]`, is described as chance quality before execution. |
| Penalty identification | `VERIFIED` | `shots[].situation` includes `Penalty`. |
| Period identification | `PARTIAL` | Shot endpoint groups by half and exposes `period`, including `FirstHalf`. Event-feed period must not be inferred from minute without separate validation. |
| Upstream xG provider/model | `UNKNOWN` | Documentation says xG is joined from shot data rather than modelled by PitchAPI. Opta is named only for 26 rebuilt leagues, not for either candidate season. |
| Model version/consistency | `UNKNOWN` | No model name, version, training cutoff, change history, or guarantee of one model across the two candidate seasons. |
| Bundesliga 2023/24 | `UNKNOWN` | Generic big-five/history-from-2021 claims do not prove a named catalog row, 306 matches, or complete shots. |
| Ligue 1 2022/23 | `UNKNOWN` | Generic claims do not prove a named catalog row, 380 matches, or complete shots. |
| Current-season continuity | `PARTIAL` | Changelog claims whole-season fixture catalogs, daily kickoff synchronization, and post-match analytics. This is not an SLA. |
| Catalog size | `UNKNOWN` | Signup/plan text says 42 leagues. Changelog says 26 rebuilt plus 44 other leagues, implying 70. Public text is internally inconsistent. |
| Stable IDs | `REJECTED` | Documentation calls IDs stable, but the 19 September 2026 changelog says source rebuilding changed IDs and old IDs now return `404`. |
| Corrections/version history | `UNKNOWN` | Fixtures update in place. No correction ledger, prior revision access, immutable data release, or source snapshot ID is documented. |
| Programmatic private-research permission | `UNKNOWN` | Programmatic access is offered, but no public legal terms identifying the operator or governing MatchForge research use were found. |
| Attribution | `UNKNOWN` | No public rule found. |
| Raw-response retention | `UNKNOWN` | No caching, archival, or immutable-retention grant found. |
| Qualification result | `REJECTED FOR EVALUATION QUALIFICATION` | Useful technical shape, but provider/model identity, exact coverage, rights, retention, revisions, and stable IDs fail the current gate. |

Official sources:
[documentation and changelog](https://pitchapi.dev/) and
[free-key page](https://pitchapi.dev/get-api-key).

## Understat

| Requirement | Status | Exact finding |
| --- | --- | --- |
| Cost/public viewing | `VERIFIED` | League, team, and match pages load without payment or login. |
| Acquisition method | `REJECTED FOR QUALIFICATION` | No official documented league-wide shot API or immutable/versioned export was found. A rendered team page lists CSV/JSON/XLSX choices, but scope, content, rights, and stability are undocumented. |
| Credentials | `PARTIAL` | Public viewing needs none; optional login exists. Export/bulk credential requirements are unknown. |
| Limit | `UNKNOWN` | No official automated/bulk rate policy found. |
| Automated/bulk permission | `UNKNOWN` | No current official permission or reuse license found. Third-party scraper existence grants no rights. |
| Bundesliga 2023/24 | `PARTIAL` | Official season page exists. Complete matches, shots, lifecycle, and xG are unknown. |
| Ligue 1 2022/23 | `PARTIAL` | Official season page exists. Complete matches, shots, lifecycle, and xG are unknown. |
| Current-season continuity | `PARTIAL` | Current Bundesliga and Ligue 1 pages resolve to 2026/27. Completeness, cadence, and SLA are unknown. |
| Shot-level xG | `PARTIAL` | Official pages describe Understat xG and show shot maps/totals. No official shot-field contract was found. |
| Penalty identification | `PARTIAL` | Third-party client evidence observes `situation=Penalty`; this is schema discovery only, not an official contract. |
| Period identification | `REJECTED` | No explicit official first/second-half shot field was verified. Minute alone does not satisfy the frozen period rule. |
| Model identity/version | `REJECTED` | Official homepage describes a neural model trained on more than 100,000 shots and more than ten parameters, but gives no model ID/version, change history, or cross-season guarantee. |
| Corrections/version history | `UNKNOWN` | No correction timestamps, revision archive, immutable release, or source hash is provided. |
| IDs/reproducibility | `REJECTED` | Public URLs/IDs exist, but no official immutable export identity, checksum, version, or retention guarantee exists. |
| Attribution | `UNKNOWN` | No official rule found. |
| Raw-data retention | `UNKNOWN` | No public retention right or immutable-snapshot guarantee found. |
| Qualification result | `REJECTED FOR EVALUATION QUALIFICATION` | Keep excluded until written permission and a complete, stable, versioned shot-data contract exist. |

Official sources:
[homepage](https://understat.com/),
[Bundesliga 2023/24](https://understat.com/league/Bundesliga/2023),
[Ligue 1 2022/23](https://understat.com/league/Ligue_1/2022),
[current Bundesliga](https://understat.com/league/Bundesliga),
[current Ligue 1](https://understat.com/league/Ligue_1),
[match example](https://understat.com/match/14828),
[team example](https://understat.com/team/Paris_Saint_Germain/2022), and
[login](https://understat.com/login).

Third-party [client documentation](https://github.com/amosbastian/understat/blob/master/docs/classes/understat.rst)
supports schema discovery only. It does not establish permission, completeness,
stability, or an official data contract.

## Evaluation V2 conclusion

Public evidence does not qualify any new Evaluation V2 group:

- football-data.org, API-Football, and Football-Data.co.uk do not provide the
  required frozen shot-xG series;
- PitchAPI and Understat do not prove one licensed, retained, versioned xG
  series across the requested seasons;
- exact complete-season checks and eligible-target counts remain `NOT_RUN`;
- the qualified StatsBomb Serie A group cannot be mixed with PitchAPI or
  Understat xG; and
- protected EPL and development La Liga data remain unopened and excluded.

Existing Decision 1 and Decision 2 therefore remain unchanged. Existing source
evidence, baselines, immutable forecasts, and the mandatory Rust simulation
requirement remain intact.

## Recommended next actions requiring separate approval

1. Send bounded, non-binding written clarification requests:
   - PitchAPI: legal entity, governing terms, private automated research,
     retention, attribution, exact candidate catalogs/counts/shot completeness,
     xG supplier/model/version consistency, corrections, ID migrations,
     immutable export, and numeric limits.
   - Understat: bulk/private-research permission, rate limits, exact shot export,
     penalty/period fields, IDs, model/version consistency, corrections,
     retention, attribution, cost, and update cadence.
   - Football-Data.co.uk: private model-research use, one controlled manual
     acquisition per candidate season, immutable internal retention, hashing,
     and attribution.
   - football-data.org and API-Football: permanent internal raw-response
     retention and post-access use.
2. After satisfactory written answers, separately authorize free account
   creation and acceptance of terms for football-data.org, API-Football, and,
   only if its response is acceptable, PitchAPI.
3. Then authorize metadata-only authenticated checks for the two candidate
   seasons. Freeze exact request ceilings and credential storage before calls.
4. Return exact catalog IDs, match/resource counts, update delay, field
   completeness, correction behavior, and account entitlements for owner review.
5. Only after another owner decision may isolated data acquisition or provider
   contract registration begin.

Do not amend Decision 1 or Decision 2 unless one alternative shot-xG provider
first proves a lawful, complete, immutable and single-model source contract.
