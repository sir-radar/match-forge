# P09-01 executable plan: dataset-wide historical completeness

**Status: PROPOSED / NOT AUTHORIZED.** This expands roadmap ticket [P09-01](roadmap.md) into executable steps. It authorizes nothing. Phases marked *owner approval* need a decision event before they run on the operating database; acquisition phases also need the access and quota rules in [source acquisition](../../source-acquisition.md).

## Principles

1. **Cohorts are predicates, not lists.** Every phase selects its targets with a query over the whole corpus. No step names a team, fixture, competition, country or provider string, and the seed fixtures from the P02 report are test cases, not the scope.
2. **Evidence first, acquisition last.** A gap is closed from retained, checksum-verified provider bytes when they exist. A new provider request happens only when no retained evidence can answer the predicate.
3. **Nothing is invented.** A result enters the corpus only from a provider response that shows it. A gap with no evidence stays visible with a typed reason.
4. **Append-only and known-time honest.** History decisions are stamped with the time they were made; published forecasts, artifacts and read reports are never edited. A phase that changes inputs of past forecasts updates the [affected-forecast inventory](../../governance/p02-forecast-reevaluation-proposal.md), not the forecasts.
5. **Every phase is idempotent, checkpointed, dry-runnable and gated by preservation hashes** ([`scripts/p02/preservation.sql`](../../../scripts/p02/preservation.sql)).

## Cohort register

Figures are from the read-only investigation of the operating database and the second rehearsal on a restored copy, both on 11 November 2026 ([evidence](../../evidence/p02-remediation-rehearsal-2-2026-11-11.json)). Owner and phase show where each cohort closes.

| ID | Predicate | Cause | Size before | Closes in | Needs |
| --- | --- | --- | --- | --- | --- |
| C1 | Unresolved fixture more than 4 h after kickoff whose latest retained API-Football response, acquired after kickoff, shows a terminal status | A retained ad hoc response (`recovery-*`, `stale-fixture-*`) was recorded but never stored; MVP status map sent `AWD`/`WO` to `SCHEDULED` | 949 of 1,669 overdue API-Football fixtures | P02 rollout (reconciliation phase of `history_requalification` v2) | Runbook approval |
| C2 | `FINISHED` `REGULATION_90` API-Football result without history whose final score appears in a retained non-dated response | Replay v1 read only `fixtures-*` snapshots | 4, plus C1 results that become finished; 0 left after the rehearsed rollout | P02 rollout (qualification phase v2) | Runbook approval |
| C3 | API-Football result without history that collided at team/kickoff with another canonical fixture during qualification | Duplicate canonical identity of one match (team or competition alias split) | 487 after the rehearsed rollout: 483 already in history through the duplicate with the same score; 4 where the duplicate's score differs | Phase 3 | Identity-resolution authority |
| C4 | Unresolved fixture more than 4 h after kickoff with no scheduled path that will observe it again | API-Football dated sync requests only yesterday and today; the operational recovery view covers FotMob and PitchAPI only | 720 API-Football after C1 (about 36 kickoff dates); 543 FotMob, PitchAPI, football-data.org and unmapped fixtures that the recovery view does not cover | Pre-P03 for mapped routes; Phase 4 for gaps | Verified scope and quota |
| C5 | Unresolved fixture whose latest retained observation after kickoff is still not terminal | Provider had not settled the match when last asked | Part of C4: 405 API-Football; 308 more were never observed after kickoff | Pre-P03 for mapped routes; Phase 4 for gaps | Authentic source evidence |
| C6 | `FINISHED` with `UNKNOWN` score basis | football-data.co.uk and openfootball publish no duration (not a defect); 5,159 API-Football rows from earlier code paths | 93,387 | Phase 2 (API-Football subset from retained status codes); others stay flagged | Runbook-class approval |
| C7 | League season with at least 80 % of its double round-robin pairings present and some missing | Candidate missing matches | 178 seasons, 3,923 candidate matches; 721 seasons with partial coverage | Phase 5 | Acquisition approval |
| C8 | Two providers disagree on a result; history score differs from the fixture | Cross-provider conflict | 1,845 conflicts; 3 history mismatches | P08-01 (official vs on-field scores) | Separate ticket |
| C9 | Extra-time or shootout result | Not forecast-eligible by policy | 212 API-Football | None (policy) | — |

## Phases

### Phase 1: apply the P02 rollout (C1, C2)

Covered by the [re-qualification runbook](../../operations/runbooks/p02-history-requalification.md). Exit: C1 and C2 at zero on the operating database; preservation hashes unchanged; affected-forecast inventory regenerated.

### Phase 2: recover score basis from retained responses (C6, API-Football subset)

- **Select:** `FINISHED` fixtures with `result_score_basis='UNKNOWN'` and an active API-Football mapping.
- **Evidence:** the latest retained API-Football row for that fixture whose `goals` equal the stored score; its `status.short` maps the basis (`FT`, `AET`, `PEN`).
- **Apply:** through `ProductSyncStorage._store_fixtures` with the citing snapshot, then `_qualify_finished_history`. Rows with no matching evidence keep `UNKNOWN` and are listed.
- **Build:** a `--basis` phase in `history_requalification` with the same dry-run, checkpoint and preservation gates, plus an integration test with a mismatched-score negative case.
- **Exit:** count of API-Football `UNKNOWN` rows with retained evidence is zero; football-data.co.uk and openfootball rows remain flagged `UNKNOWN_SCORE_BASIS` by design.

### Phase 3: resolve duplicate identities (C3)

- **Select:** `fixture_identity_ingestion_conflicts` with stage `HISTORY_QUALIFICATION`, grouped by the canonical fixtures they name.
- **Classify:** `integrity_audit.remaining_gaps` already separates *result already in history through the duplicate*, *score disagrees* and *other fixture without history*.
- **Resolve:** for each pair, the identity-correction owner proposes a `fixture_identity_resolutions` record (and, where a team alias split caused it, a team alias), with the evidence of both providers. Admission follows the existing identity-review workflow; nothing is merged automatically.
- **Exit:** every C3 fixture is resolved as a duplicate, a distinct match, or an open review with a reason. The score-disagrees subset goes to P08-01.
- **Note:** form is not short of these results today when the duplicate already carries them; resolving removes double counting risk and the conflict noise.

### Phase 4: remaining overdue result gaps (C4, C5)

The historical counts above remain the November 11 baseline. Use the
[pre-P03 result recovery path](design.md#pre-p03-result-recovery) for eligible
FotMob, PitchAPI and API-Football mappings. P09-01 owns the remaining authentic
gaps, including missing native mappings, unsupported or partial provider
coverage and fixtures with insufficient proof. On 14 November that was 925
provider-scoped fixtures awaiting identity admission and 11 verified fixtures
with no recurring route
([verification record](../../evidence/pre-p03-recovery-verification-2026-11-14.md)).
Compare those cohorts after pre-P03 rollout. Keep unavailable sources and nonterminal responses visible
and reuse the existing worker when new evidence becomes eligible.

### Phase 5: league-season pairing gaps (C7)

- **Select:** `league_coverage` records in state `CANDIDATE_MISSING_MATCHES`.
- **Verify first:** check each season's format (splits, groups, conferences) from the competition's own provider metadata; an absent pairing in a split league is legitimate and is marked so.
- **Acquire:** league-season requests only for seasons where a pairing is still unexplained, under P09-02 acquisition rules.
- **Exit:** each candidate pairing is found, explained by format, or recorded as `MISSING_SOURCE` with the providers asked.

## Detection that keeps the cohorts closed

| Check | Where it runs | What it catches |
| --- | --- | --- |
| `incremental_findings.finished_without_history` | Every `refresh-public-reports` run | A stored regulation-time result that missed qualification |
| `incremental_findings.overdue_api_football` + reconciliation of the newest retained responses | Every `refresh-public-reports` run | A retained terminal response that was recorded but not stored (C1) |
| `incremental_findings.overdue_without_scheduled_recovery` | Every `refresh-public-reports` run | An overdue fixture no schedule will re-observe (C4) |
| `remaining_gaps` and `domains` in the global audit | Each global audit | All cohorts, grouped as source completeness, reconciliation, report freshness and forecast correctness |

## Acceptance for the ticket

- Each cohort above has a before/after count from the same audit version, and the union of targets is listed by predicate with a hash.
- No published forecast, artifact or read report hash changes; new records only.
- Newly eligible results are counted as such; source-only rows are not counted as forecasts gained.
- Rollback for each phase is the step-1 backup of the runbook; partial phases resume from their checkpoint.
