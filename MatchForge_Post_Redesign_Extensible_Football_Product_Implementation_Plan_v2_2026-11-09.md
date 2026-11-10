# MatchForge — Post-Redesign Football Information, Product Intelligence & Operational Refinement Plan

**Revision 2 — extensible implementation roadmap | 9 November 2026 (Africa/Lagos) | Begin after verified relevant foundations of the unified redesign.** The unified redesign is tracked as [docs/architecture/unified-redesign-2026-11-10/](docs/architecture/unified-redesign-2026-11-10/README.md) with [ADR 0005](docs/adr/0005-unified-architecture-evolution.md). The v3 draft this plan was written against (`MatchForge_Unified_Architecture_Redesign_v3_Extensible_Foundation_and_Continuous_Learning_2026-11-09.md`) is not tracked in the repository; use the tracked docs.

> **Authority.** This is a follow-on roadmap under root [PLAN.md](PLAN.md) and [AGENTS.md](AGENTS.md). It sequences product work and authorizes nothing. `docs/project-status.json` and resolved owner decisions outrank it, and PLAN.md's invariants hold for every phase: point-in-time integrity, immutable forecasts, display-only context with no forecast effect, research acceptance separate from promotion and production enablement, and no model change without its own owner decision. Each F-ticket needs its own task authorization.

**Scope:** The 25 non-P0 items from the 40-item architecture gap audit, **except A01 (Probability Filter, excluded by owner)**, plus the actual delivery of future team/player, squad, lineup, formation and injury capabilities whose **contracts**, but not full features, are reserved in the unified plan. This is a follow-on **implementation plan**, not a new architectural investigation and not automatic approval to mutate operating data, acquire new provider data or start scientific research.

## 0. Primary decision and relationship to the unified redesign

The updated unified plan owns the **foundation**: canonical team/player/fixture identity; source provenance and compatibility; bitemporal facts; league-rule and market semantics; forecast validity; guarded learning, scientific approval and feature-parity boundaries; single job authority, running-version truth, worker/event architecture; backup/recovery; privacy/permissions; and UI compatibility. This plan owns **bounded features and refinements after those foundations are sufficiently verified**. Every feature must reuse the unified redesign’s `EXT-01–EXT-09` extension contracts, be independently deployable and have evidence-based backward compatibility. **Do not build a second architecture to implement these features.**

**Explicitly excluded:** The standalone percentage-based **Probability Filter** and its frontend/API implementation. Do not reopen, reproduce, re-estimate or schedule that task here. **A02 market semantics are core architecture**, not a backdoor authorization to rebuild that filter.

Do **not** delay an independent verified team information page until every optional Architecture V2 or scientific challenger milestone is done. Conversely, no future data product may bypass still-applicable canonical-identity, access-right, point-in-time, backup, privacy or release gates. The unified investigation is planning-only; implementation of any phase below requires a new explicit task/owner authorization under existing repository rules.

### Source and implementation reality to verify before work

| Existing repository asset/evidence | Implication for the subsequent plan |
|---|---|
| `python/football/src/football/context/live.py` | Existing `AvailabilityObservation`, `LineupObservation`, `PredictedLineupV1`, formation and coach/accuracy logic. **Reuse and validate**, do not create competing systems. |
| `python/football/src/football/product/context_sync.py` | Supports `INJURIES`/`LINEUPS`, but all three context/lineup/injury config gates default disabled. Activation needs explicit entitlement, quota, provider-coverage and rollout checks. |
| `docs/contracts/live-match-context-v1.md` | Context is display-only for current champion; context-only source updates do **not** create new predictive forecasts. |
| `docs/evidence/matchforge-context-feature-evaluation-v1-2026-10-08.md` | On 8 Oct: zero qualified availability/lineup/coach and lineup accuracy observations; no predictive context family admitted. Recheck **current** runtime evidence, never repeat dated counts as current. |
| `docs/data-model.md` and existing player/lineup participation migrations | Preserve canonical player identities, temporal membership, source observations, provider crosswalk, corrections. |
| `docs/roadmap/implementation-phases.md` | Historical proposal already discusses dynamic team context, lineups, predicted XI, player effects and training-serving parity; **proposal ≠ approval or deployed capability**. |
| `docs/frontend/api-requirements.md` and `docs/api/openapi.yaml` | Reconcile Go API → frontend parse contracts, missing/null semantics, market capability, authenticated endpoints and version compatibility before adding new screens. |
| `docs/CODEBASE_REMEDIATION_REPORT.md` | Multiple prior code defects are marked fixed in isolated tests but operating adoption was separate. Verify before declaring a new defect or rebuilding work. |
| PR #178 (Architecture V2 / remediation), PR #179 (data status remediation) and PR #182 (post-remediation integration) | Merged to `main` on 10 November. Respect their migration ownership and the existing scientific/identity gates; this plan does not rewrite or supersede them. Architecture V2 is still `IN_PROGRESS` with no cutover in `docs/project-status.json`. |

**Caveat:** Source files and reports establish implementation and *dated* evidence; they do not certify today's local service is synchronized, entitlement-approved or running the current branch.

## 1. Implementation principles and release boundaries

1. Extend one canonical identity/evidence truth and one existing Work Orchestrator; no second entity registry, model registry, context scheduler, SQL decision table or publication service.
2. Qualified data may be **shown** without being **used to train**. Model-input eligibility is a separately authorized, protected research step.
3. Never infer 'fit' or `AVAILABLE_CONFIRMED` from no reported injury; never invent missing player, coach, formation or training evidence.
4. Separate source observation time, source publication time, MatchForge knowledge time, fixture kickoff and effective membership periods. Any historical read must reproduce what was known at the historical cutoff.
5. Provider capability is scope-specific (provider, competition, season, field, account permission, update cadence, semantic version, source lineage). Prefer useful partial coverage to fake full coverage.
6. Preserve the owner's desired **no permanent sidebar**, responsive clean fixture/research navigation and **inline collapsible fixture detail**, not modal-first UX; use `shadcn/ui` + Tailwind and authoritative `web/ui-designs/*.html`.
7. Next.js SSR/server components for initial page data when appropriate; Go/Python SQL/API reuse; server-side sorting/filtering/page boundaries; streamed backend events where real-time changes matter.
8. Non-forecast static/team information can launch even when optional science is blocked. No injury/player-feature input can alter current official champion until a distinct governed evaluation and promotion decision.
9. Every slice requires code owner, parent dependency, disposable and source-backed tests, feature switch/rollback, cost and Mac disk/CPU budget, accessible empty/degraded state and precise deployment verification.
10. **Do not quietly start the Probability Filter initiative** through generic selection, horizon or query improvements. If a ticket overlaps it, record the boundary and defer that piece to its independent owner.
11. Every feature must identify a verified **extension point and domain owner**, use a typed/source-backed contract, preserve other consumers and record its change-impact/rollback scope before implementation. Refactor an insufficient seam **once**, in a bounded authorized ticket, instead of copying logic around it.
12. Prefer **modular in-process code, conventional typed Python/Go/TypeScript, SSR UI composition and existing versioned SQL**; no plugin marketplace, microservice, bespoke workflow engine or generic schema merely to promise future flexibility.
13. Every release must test additive old/new compatibility, optional enable/disable behavior, null/unknown/partial source states and no changes to the current model/market/forecast semantics unless separately governed. Document deliberate deprecations and preserve immutable historical evidence.

## 2. Entry gates from the unified redesign

Do not mark the whole redesign `COMPLETE` as a condition for every small feature; use these **specific independently verifiable** gates:

| Gate | Needed by | Evidence required |
|---|---|---|
| `BASE-IDENTITY` | Team/player/roster/lineup/injury | Verified team/player/coach/fixture identity semantics, time-bounded crosswalk, correction/version rules and no unresolved false merge in selected cohort |
| `BASE-SOURCE` | All new providers/context | Resource/competition/season capability, account permission, retention rules, known-at, meaningful coverage and quota owner |
| `BASE-API` | All new pages | Stable versioned Go API DTOs, pagination/error/null semantics, Next.js parser compatibility and tested SSR initial response |
| `BASE-EVENT` | Live lineup/availability views and watchlists | Committed event identity, replay/resume and correct revalidation or a justified non-real-time alternative |
| `BASE-PRIVACY` | Injury status, player media | Privacy/rights/attribution/minimization, minors and deletion/correction policy plus access controls |
| `BASE-SCIENCE` | Predicted-XI scientific claims, model-impact challengers | Point-in-time historical corpus, unspent development targets, immutable input manifests, feature-parity and scientific governance |
| `BASE-OPS` | New background work | True lease/heartbeat/status telemetry, Mac sleep recovery, quota fairness, backup/restore and runtime commit/migration verification |
| `BASE-RULES` | Standings/markets | Verified competition-specific standing policy and source semantics; compatible market/period/settlement contract |
| **`BASE-EXTENSION`** | **All F1–F11 feature work** | **Verified EXT-01–EXT-09 interface owner and version, acceptable change-impact radius, versioned SQL/API/event/model compatibility, source/authorization and resource budget, additive migration and flag/rollback playbook, associated fitness tests. This gate is scope-specific; a blocked optional injury adapter does not block an unrelated team page.** |

**Blocked dependency policy:** A failed `BASE-SCIENCE` must block *model influence*, not the entire confirmed-lineup UI. A restricted injury provider must block the source intake, not team profiles built from qualified results. A missing image licence must fall back to a placeholder, not block player-name records.

## 3. Delivery sequence and independent workstreams

This is a **dependency graph, not an all-or-nothing waterfall**. Use one active small Codex implementation task per overlapping code owner; disjoint bounded backend worker jobs can continue within their ordinary authority. Commit/verify each ticket before the next dependent slice.

| Phase | Main deliverable | Primary gap IDs | Prerequisite | Definition of Done |
|---|---|---|---|---|
| **F0: Reconcile and freeze contracts** | Inventory deployed vs drafted APIs/context, choose supported initial league/provider and freeze scoped evidence | A03, A04, B06, C07, D03, E06 | Applicable BASE gates for inspection only | Gap/owner matrix; no duplicate implementation; chosen limited pilot and rollback plan |
| **F1: Team hub** | Team pages, verified fixtures/results/form, standings & coach info; league-rule-safe partial views | A05, A07, A08, D01 | BASE-IDENTITY, BASE-API, BASE-RULES | Source-backed team view navigable from fixtures; partial/unknown states and mobile/a11y tests |
| **F2: Player and squad hub** | Player profiles/search, historical rosters/transfer/loan/registration intervals, stats | A06, B01, B09, B10 | F1 + BASE-IDENTITY, BASE-SOURCE, BASE-PRIVACY for images | No future-roster leakage or duplicated identity; reliable links and no unlicensed media |
| **F3: Confirmed lineups and formations** | Formation/pitch + list view, starters/bench, corrections, coach, timestamps | B02, B03, B07, D03, D04, D05 | F1/F2 minimally + BASE-SOURCE, BASE-API | Verified source sample, 11-player/team checks, no predicted→confirmed label errors |
| **F4: Match availability** | Publicly sourced fixture injury, suspension, doubtful and unavailable statuses with freshness | B04, B05, B06, D02, D03, D04 | F2 + BASE-PRIVACY, BASE-SOURCE, BASE-OPS | Provider/competition entitlement PASS, minimal facts, no empty-feed=healthy, revocable pilot |
| **F5: Predicted XI and accuracy** | Validate existing predicted lineup, confidence, accuracy and replacement logic; UI labelled predicted | B08, B09, C06 | F3/F4 data if qualified + BASE-SCIENCE | Genuine pre-kickoff historical scoring, independent naive prior-XI baseline, no current champion change |
| **F6: Optional contextual forecasting research** | Separate registered lineups/availability/squad/rest challengers, ablations and scientific evaluation | B08, C05, C06, E07, E08 | F5 and independent scientific authorization | Explicit reject/accept evidence, proper-score+coverage parity, no leaked data/promotion |
| **F7: Forecast context and readiness UX** | Reasons for unavailable forecasts, horizon/model selection clarity, market and settlement wording | A03, A04, C06, D04, D05 | BASE-API, BASE-RULES, existing forecast-readiness owner | One authentic gate explanation; old forecasts preserved; no unsupported market claims |
| **F8: Operational drilldowns** | One run/issue/deployed-truth view, fixture processing trace, Mac wake handling, learning maturity | C07, E04, E05, E06 | BASE-OPS, BASE-EVENT where needed | Human-readable blocker, specific lease, source→forecast trace, verified commit and correct stale-status labels |
| **F9: Product/API polish** | Cross-page navigation, saved non-probability research context, API cache/index/contract tests, UI/a11y/perf | A07, A08, E06, E09 | BASE-API, F1/F7 | Faster measured workflow, no sidebar, collapsible inline panels, robust bad-network states |
| **F10: Source maturity and advanced context** | Source methodology-change and entitlement handling, league-specific details, coach/travel/rest and tactics history | B09, D03, D05, E07 | F2–F4 as applicable | Qualifying source/version proof, no historical contamination, no model impact without F6 |
| **F11: Optional research lists and alerts** | Watch teams/competitions, fixture or lineup-change notices when real utility is demonstrated | E10, A07 | F1/F8/F9 + BASE-EVENT, privacy | Opt-in, bounded/no spam, no new notification server unless justified |

**Suggested practical order:** F0 + verify `BASE-EXTENSION` → F1 → F7 (in parallel where safe) → F2 → F3 → F4 → F5 → F6. F8/F9 can occur throughout once their foundations are stable. F10/F11 are optional. **No fixed delivery durations are promised**; provider gaps and authorization may delay particular items while unrelated phases proceed.

## Extensibility-first feature delivery contract (applies to F0–F11)

**Definition of success:** once the unified redesign's reusable seams are accepted, adding a qualified new team attribute, football data source, match-detail section, lineup variant, availability source or candidate model should be a **small independently testable and reversible feature**, not another global architecture rewrite. Retain the right to perform a targeted refactor where real evidence shows the existing seam is too weak.

### Required per-feature implementation record

Before each F-ticket, Codex must complete this concise record and include it in the implementation PR/task status:

| Field | Minimum evidence |
|---|---|
| Extension owner | Actual code module, database writer, API owner, currently deployed vs designed status, known dependencies |
| Approved extension point | Which EXT contract/owner, its existing version, consumer version range and whether code already supports it |
| Source and eligibility | Provider × resource × competition/season entitlement, identity evidence, historical knowledge time, data quality and permissions |
| Typed change set | Additive schema/observation, Go DTO/OpenAPI, TypeScript parser, event payload, optional feature section or governed model manifest; **precise files to touch** |
| Version compatibility | Old↔new Go/Next.js/SSE consumers, field/null/enum defaults, API cache behavior, historical and current snapshots |
| Scope and resources | One small testable capability, target cohort, API query cost, provider quota, local CPU/memory/WAL/disk footprint, concurrency with live service |
| Isolation and rollback | Feature flag, safe fallback/unavailable states, reversible route and worker configuration, retained immutable originals and artifacts |
| Quality evidence | Disposable DB migration/restore, contract fixtures, bitemporal/leakage tests, UI and a11y acceptance, actual operating version if deployed |
| Future-proofing check | The next analogous feature can reuse the same extension without duplicating the service/registry; no unrelated code or scientific model changed |

### Fixed feature-extension matrix

| Feature phase | Existing extension seam to prefer | Required future extension proof |
|---|---|---|
| **F1 team page** | Canonical team ID + qualified competition/standing read model + typed SSR section | A new verified team statistic is additive; current fixture pages stay unchanged |
| **F2 player/squad** | Existing player identities, memberships, source observations and roster validity intervals | A new player profile field, transfer/loan season and source are point-in-time safe |
| **F3 formation/confirmed lineup** | `LineupObservation` + position/grid + qualified provider adapter + inline match detail composition | A new formation/source representation is displayed without replacing the fixture viewer |
| **F4 injuries/availability** | `AvailabilityObservation` and existing source capability/permission gates | A second provider or new *reported* availability type does not imply an empty feed proves fitness |
| **F5 predicted XI** | `PredictedLineupV1` plus immutable forecast-time context, known-at and confirmed-XI evaluation | A new nonofficial line-up heuristic can be tested in shadow without changing published result forecasts |
| **F6 optional model context** | Versioned model/feature registration, protected split/evaluation and champion-governance layer | A challenger can be added/rejected without editing champion artifacts or prior forecasts |
| **F7 readiness UX** | Existing forecast reason owner, market taxonomy, typed status API and SSR collapsible section | An extra reason/unsupported capability degrades safely in older clients |
| **F8 operator trace** | Work Orchestrator and source→canonical→model lineage, committed event contract | Another job type is visible without adding a separate tracker or scheduler |
| **F9 navigation/API UX** | Versioned Go endpoint, typed Next.js client, shared shadcn/ui components | New section works with SSR, event streams, keyboard/mobile and existing URLs |
| **F10 advanced context** | Domain-specific typed source observation with semantics/version proof | Adding a new coach/travel/league rule cannot contaminate historic fixture or model results |
| **F11 optional lists** | Existing source-scoped API/events and small per-user app state, if justified | A new alert topic requires no new background delivery service by default |

### Safe extension sequence (repeat for each authorized feature)

1. **Reconcile:** inspect whether the desired capability or contract is already implemented, documented, shadow-only, blocked or deployed. Avoid duplicate tables, routes, workers and tests.
2. **Prove the seam:** run or design the unified architecture's `EXT-09` representative change-impact case. If it fails, open a small **seam improvement ticket** with named owner, bounded scope and regression tests.
3. **Expand:** add typed source/DTO/section/model declarations and feature flag without breaking existing consumers; record version and source/rights constraints.
4. **Verify:** use a small qualified pilot and run old/new compatibility, same-kickoff/known-at where relevant, missing/unknown data, backfill/retry, pagination/SSR/accessibility and output-parity tests.
5. **Roll out:** independently activate the feature after its required gate; compare resource/performance baselines; preserve original evidence and allow fast rollback of the new surface.
6. **Contract later:** deprecate old consumers or migrations only with usage evidence, explicit authorization, backup/restore and rollback proof. Do not treat successfully built code as proof of operating adoption.

**The standalone Probability Filter remains out of scope at every step**. Market definitions and forecast diagnostics may be shared prerequisites but must not become a percentage threshold UI or API implementation ticket in this plan.

## 4. Detailed bounded delivery tickets

Each ID below is a ticket *proposal*. Before execution, inspect whether it is already satisfied in operating code. Do not recreate fixed work. Required deliverables are source evidence, code/test changes where separately authorized, and one small diff per ticket.

### F0 — Readiness audit and pilot selection

- `POST-F0-00`: Verify the unified `BASE-EXTENSION` handoff, including real module-owner inventory, old/new typed contract fixtures, seven future-change proof records, active API/model/worker versions, and a small future-feature playbook. Mark missing seams `GAP_WITH_TARGETED_SEAM` rather than declaring the entire redesign incomplete. No new plugin framework.
- `POST-F0-01`: Match `docs/project-status.json`, active migrations, operating binary `/version`, PR branches, sources, DTOs and owned jobs. Classify `DOCUMENTED_ONLY`, `CODE_IMPLEMENTED`, `SHADOW_TESTED`, `OPERATING_VERIFIED`, `BLOCKED`, `UNVERIFIED` with dated evidence.
- `POST-F0-02`: Select **one** competition-season/provider pilot for team info and separate pilot scopes for formations and availability only if entitlements permit; measure actual source coverage and costs rather than assuming support.
- `POST-F0-03`: Freeze a minimal REST DTO + source provenance + nullable capability contract and a rollback path; compare against existing Go APIs and HTML design source. No new domain store before auditing reuse.

**DoD:** Clear Go/Python/data owners, source/rights matrix, bounded pilot with explicit unavailable states, no unapproved ingestion or migration.

### F1 — Team information workspace

- `POST-F1-01`: Introduce/reuse server-side team summary read model with name, identity, verified active season/competition, coach/venue where available, recent fixtures, results, home/away form and known historical metadata. Avoid N+1 joins and cross-team duplicates.
- `POST-F1-02`: Provide competition-context standings using approved rule versions: points deductions, awards/abandonments, playoffs/splits, tie breaks, promotion/relegation and source provenance; unknown rules yield partial status, not an authoritative false ranking.
- `POST-F1-03`: Ship SSR team page with links from match rows, compact fixtures and results, standings, recent performance, collapsible detail and mobile/keyboard navigation. No sidebar, technical IDs behind advanced disclosure.

**DoD:** For a qualified team a user can move fixture → team → relevant fixtures without external lookup; source fields exactly match canonical evidence; unknown/stale/missing and disallowed context have distinct labels; deterministic API/E2E tests pass.

### F2 — Player, squad and registration workspace

- `POST-F2-01`: Review player ID, registration and transfer/loan schemas; implement only missing time-bounded team membership queries, preserving real knowledge-time and effective-time. Competition participation and national duty are separate from official club registration.
- `POST-F2-02`: Reuse qualified roster/squad provider data where permitted, with per-season snapshots, position, appearances, minutes and only semantics-proven player stats. Show roster coverage explicitly; a today roster must not backfill historical facts.
- `POST-F2-03`: Build SSR player and squad pages, search, links from team/lineup, and safe badges/photos when licensing permits; otherwise fallbacks. Distinguish same-name players, reserves, youth and women's squads.

**DoD:** Loan/transfer, duplicate-name and 2024/2026 historical correction tests pass; no unusable image rights dependency blocks text-based profiles.

### F3 — Confirmed lineup and formation product

- `POST-F3-01`: Audit native PitchAPI/FotMob/API-Football lineup coverage and existing `LineupObservation` and `player_position_stints`; qualify starter/bench, coach, nominal shape, grid positions, known-at and source correction semantics.
- `POST-F3-02`: Implement a **formation pitch diagram** with accessible list/table alternative, mobile reflow, player links, status and original source timestamp; use existing shadcn primitives and Tailwind, custom CSS only if necessary.
- `POST-F3-03`: Show pre-match `CONFIRMED` vs `PREDICTED` vs partial/unknown, bench, substitutions, period-specific tactical changes if authentic, and corrected announcements without altering earlier match evidence.

**DoD:** 11 starters per verified team where source claims complete lineup; duplicate players/opposing team orientation rejected; no stale lineup as confirmed now, no post-kickoff data injected into earlier forecasts.

### F4 — Injury, suspension and availability product

- `POST-F4-01`: Approve a narrow provider/league capability, entitlement, lawful processing, source correction and retention policy **before** new acquisition. Do not infer entitlement from published API docs or the presence of existing functions.
- `POST-F4-02`: Reuse disabled context scheduling only after a controlled source pilot; quotas reserved for urgent provider sync, known-at and freshness recorded, live player source identity verified, retries/failures distinct from unrelated fixture work.
- `POST-F4-03`: Publish minimal match-relevant availability state with reason categories and certainty, last verified source time, coverage restrictions, corrections, accessible UI and safe handling of minors/medical detail.

**DoD:** Empty injury feed≠fully fit; suspension≠injury; doubt≠confirmed absence; a player confirmed available later is versioned, not retroactively changed; provider failure cannot corrupt score sync.

### F5 — Predicted XI evaluation (independent from official outcome forecasting)

- `POST-F5-01`: Qualify historical pre-match lineup/availability snapshots and *later* confirmed XI with hard knowledge-time firewalls, same fixture/team identity, source-version/formation semantics, clear coverage denominator and protected/unspent target status.
- `POST-F5-02`: Run deterministic `PredictedLineupV1` and a naive repeat-previous-XI baseline on the same independent targets, with accuracy/coverage by position, coach, minutes and confidence; do not optimize against protected targets.
- `POST-F5-03`: Display predicted XI only when evidence/calibration supports it; label it **predicted** even if it matches later confirmed XI, show missing slots and confidence meaning, and retain original prediction versions.

**DoD:** Zero-data state declines prediction rather than fabricating an XI. Research failure blocks modelling claims but not confirmed lineup pages. Current champion unchanged.

### F6 — Optional context-aware champion challenger (requires new authority)

- `POST-F6-01`: Register **one** authorized feature-family hypothesis (e.g. lineup continuity or player unavailability, not several features at once) with frozen policy, exact source family/version and a newly qualified independent development/holdout corpus.
- `POST-F6-02`: Build strict feature-parity and leakage tests; fit a reproducible challenger within resource and quota budgets, compare with champion on matched fixtures/lead times using proper scores, calibration and coverage.
- `POST-F6-03`: Retain/reject candidate by protocol. Promotion requires separate decision, tested canary/rollback and immutable old champion; no injury headline or verified lineups alone may silently revise probabilities.

**DoD:** Governed artifact/fit manifests, original forecast bytes intact, abort on insufficient coverage, no CPU/SSD starvation of urgent source workers, no automatic production adoption.

### F7 — Forecast/readiness and research UX (excluding percentage filtering)

- `POST-F7-01`: Reuse existing readiness owners for exact failure chain: unresolved canonical fixture, missing qualified history, unavailable score basis/source, artifact missing or retired, quota/worker state, model market unsupported. Provide concise actionable messages without inventing new top-level status authority.
- `POST-F7-02`: Show issued-at, knowledge cutoff, model identity, approved horizon/variant and corrected fixture state. Distinguish selection of latest currently eligible vs an older lead-time forecast; never rewrite historical published records.
- `POST-F7-03`: Present prediction-market and External Predictions comparison terminology from core A02 contract, with explicit score basis and compatibility, not misleading confidence/accuracy language. No custom probability threshold/query control in this plan.

**DoD:** No forecast uses correct backend reason; user can inspect historical version and understand missing data; unapproved/research candidate never impersonates public champion.

### F8 — Operations and traceability

- `POST-F8-01`: Extend existing Admin work state API with realistic progress, owner/lease, retry deadline, dependency and last successful run; separately display Code task acceptance/rollout status. No second durable job tracker.
- `POST-F8-02`: Build read-only fixture provenance drilldown from provider resource → mapping/admission → canonical fixture → history eligibility → forecast artifact → eventual verified result/evaluation. Provide advanced exact IDs without exposing secrets.
- `POST-F8-03`: Test sleep/network/reboot catch-up, rebuild missed work bounded by provider budgets, show source freshness, plus model `MONITORING_ONLY` vs `TRAINING_ACTIVE` states based on actual scheduler evidence.

**DoD:** An old `IN_PROGRESS` Codex issue and expired backend worker cannot look like two running workers; trace includes evidence for a blocked forecast, not a guessed explanation.

### F9 — API performance, UX and accessibility

- `POST-F9-01`: Measure API source/backend query plans, cache correctness, batch relations, pagination and stable sort across Go/Python/Next.js; add only evidence-backed indexes and bounded queries. Do not build duplicate reads for already healthy endpoints.
- `POST-F9-02`: Implement consistent URL state for team/league/date research, keyboard/back-forward navigation, SSR first paint, responsive compact fixture scanning and inline collapsible match content. Avoid sidebar and modal-first navigation.
- `POST-F9-03`: Expand accessible pitch fallback, live-region update throttling, forced-colors/zoom, slow network, partial source and Admin error recovery. Make advanced technical material progressive disclosure.

**DoD:** Representative full workflows fit measured latency/resource bounds, nullability and enum contracts pass across staged old/new APIs, tested browser/a11y cases have no false green badges.

### F10 — Advanced context/source semantics

- `POST-F10-01`: Audit source methodology revisions (formation, positions, player appearances, injury status and xG vendor/version), choose one qualified stable mapping and preserve raw source revisions plus compatibility dispositions.
- `POST-F10-02`: Add audited coach tenure, squad transition and rest/travel context as truthful display data; no automatic champion feature activation.
- `POST-F10-03`: Model competition-specific two-leg aggregate, extra time, relegation stages, playoffs and official tie breakers in the correct league/fixture context while preserving regulation-time settlement distinctions.

**DoD:** Source semantic drift is detected; no false historical continuity, bogus standings, or cross-market result comparison.

### F11 — Optional saved research/watchlists

- `POST-F11-01`: Research whether saved teams/competitions and fixture/update notifications reduce repeated navigation in a local single-user app; prefer URL/bookmarks and local app state before adding persistent data.
- `POST-F11-02`: If justified and separately authorized, use existing backend SSE events with opt-in, topic filters, deduplication and bounded retention; no unsolicited notifications or duplicate subscription engine.

**DoD:** Small opt-in feature with measurable workflow value; no background infrastructure merely to show a decorative alert.

## 5. Rollout, data protection and acceptance policy

### Before an implementation ticket is authorized

For each ticket record: current code/owner, **BASE-EXTENSION seam and change-impact evidence**, precise gap/dated evidence, feature gate, source data rights and known-at support, versioned output contract, backfill/repair scope, resource and DB migration impact, representative source examples, isolated test suite, rollout/rollback control, preservation checks and any independent scientific approval. A job which merely executes is not evidence that source acquisition, qualification, serving, model evaluation or deployment succeeded.

### Version and API strategy

- Additive schema/API changes first; support older consumers until parity tests and owner-approved retirement are complete. Apply the core **expand → migrate → contract** sequence; do not invent a parallel compatibility framework. Document safe old producer/new consumer and new producer/old consumer behavior in Go, Next.js and any long-lived SSE stream.
- Prefer backend pagination and deterministic ordering except the existing **External Predictions** deliberately unpaginated UX. No frontend in-memory pagination of bulk lists.
- Validate null vs zero vs missing and enum evolution in Go API, SQL and Next.js parsers; typed `UNKNOWN`, `UNAVAILABLE`, `RESTRICTED`, `PARTIAL` where evidence supports.
- Prefer backend-generated events only after transaction commit, with SSR initial snapshot and reconnection; no browser timer driving provider acquisition.
- Defer models and user-facing probabilities until the existing champion/governance rules permit; direct context read-only views must have a strict no-forecast-effect contract.

### Safe feature flag and rollback matrix

| Feature | Release mode | Rollback means | Must remain immutable |
|---|---|---|---|
| Team hub | Read-only shadow/API pilot → selected league visible | Disable route/flag, retain sourced facts | Canonical identities, history |
| Player/roster hub | Scoped source and UI pilot | Hide view/stop acquisition; no silent deletion | Original registration/membership observations |
| Formation/confirmed lineup | Verified one competition/source pilot | Revert UI/consumer flag, keep original source | Historical lineup publication and clocks |
| Availability | Disabled-by-default → approved source pilot → carefully enabled | Stop separate context work/disable display, maintain access/retention compliance | Original approved observations, corrections, nonmedical provenance |
| Predicted XI | Shadow evaluation first, explicit nonofficial label | Disable predicted view, keep evaluation bytes | Prior prediction snapshots, held-out evaluation |
| Optional model context | Governed research → independent tests → separate approval | Switch back to approved champion and preserve route/event lineage | Historic forecasts, artifacts, protected targets |
| Team/forecast/ops UI | SSR read-only rollout, no permanent sidebar | Restore older UI route while preserving API contract | Source facts, worker ownership, published forecasts |

### Non-negotiable quality and negative tests

- Team names/squads/ages/youth/reserve and nationality must not establish provider equivalence alone.
- Historic loans and transfers must not leak future team membership into earlier fixtures or backtests.
- Late lineup revisions, simultaneous kickoffs and restarted sources must honor knowledge time.
- Provider lacks injury entitlement; application must not show 'No injuries'.
- Empty, stale, unqualified and confirmed-zero are independent states for every API/context/metric.
- Pitch formation has a usable text/list alternative, readable names, non-overlapping coordinates and keyboard navigation.
- A verified provider score corrected after kickoff creates new downstream evaluation/settlement versions, not overwritten forecast probabilities.
- Live provider work and team/injury acquisition have separate bounded budgets; fit work yields CPU/memory/storage under pressure.
- `RETIRED`/missing champion artifact never creates an implicit substitute from research.
- API schema and initial SSR server and subsequent event update agree on source, model, history and nullability.
- Operating service provenance matches the tested release; dashboard never reports unverified rollout as deployed.
- E2E user can select a team from fixture, inspect squad/formations, see uncertainty/availability and return without opening a third-party football site on a supported coverage cohort.
- Adding a second qualified source or a new player statistic uses the same typed resource/field contract; no parallel canonical entities, unbounded JSON fields or hidden training input expansion.
- New formation/availability sections can be toggled on/off without changing unrelated public forecast probabilities, bringing back a permanent sidebar, or breaking older client parsers.
- Old/new schema, API, event and model-contract versions pass mixed-release compatibility; stopped/backfilled migrations are idempotent and supported by a verified restore.
- F5/F6 shadow-learning variations cannot silently promote a challenger, consume protected heldouts or rewrite champion/forecast bytes.

## 6. Definition of complete and handoff to Codex

For every F-phase, Codex should return: (a) owner and current state before edits; (b) affected API and source contracts **plus EXT interface/compatibility version and path-level change-impact**; (c) migration/deployment effect; (d) source evidence and unknown coverage; (e) proposed small tickets; (f) isolated test hashes/commands and preserved historical bytes; (g) actual operating evidence if separately rolled out; (h) remaining blockers and next independent task; (i) clean branch/commit and PR scope; (j) evidence that the next analogous feature reuses the same domain seams without creating duplicate infrastructure. No hidden background completion or unverified 'already done' claims.

**End state:** An independently extendable MatchForge product in which a qualified new field, provider, team/player resource, formation, injury feed, match section or candidate model is normally a small reversible update on verified shared contracts—not another full rearchitecture. A usable first-class MatchForge football information application with team/player pages, qualified squads, confirmed and clearly predicted lineups, tactical formations, source-backed match availability, true forecast-readiness explanations and improved navigation/operations, which can progressively add scientifically validated player/lineup-aware forecasting **without** destabilizing the unified data reliability and continuous-learning architecture.

**Important:** This is a staged *follow-on implementation roadmap*. Do not begin implementation or access restricted provider data solely because the plan exists; use its applicable gates after the corresponding unified-foundation decisions and follow normal task approval. **The standalone Probability Filter is excluded.**
