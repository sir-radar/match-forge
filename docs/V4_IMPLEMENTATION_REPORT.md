# MatchForge V4 implementation report

## Phase 00 — current-state reconciliation

Status: PASS. This is a code/runtime inventory checkpoint, not acceptance of later
feature, scientific, R3 or migration work. The original prompt is a historical
coverage reference. CURRENT_TASK.md and the owner's latest authority correction
control implementation; the reference's claim to be the single implementation
authority is superseded.

Starting branch/SHA: `main` / `8b82dd637449a18ea6086853344e8bc7b0e0f2e2`.
Task branch: `ft/v4-execution-programme`. Routing: L3 (architecture, historical
integrity, identity and governance). No active Wayfinder map is recorded in the
current project status. This programme uses independent phase commits.

### Code and operating database are different evidence

The operating `.env` database is `football`. A read-only repeatable-read
transaction on 2026-10-31 observed 244,393 product fixtures, 13,067 forecasts,
53,723 source snapshots, 55,531 resources and 43,448 work items, through migration
`202610310500`. Seven real football provider namespaces are registered; the 37
provider rows include test namespaces and must not be counted as 37 integrations.
V2 resource observation artifacts, scoped capabilities, resource authority,
provider/canonical coverage, runtime model registrations and post-match
evaluations each have **zero operating rows**. Do not translate implemented
schemas/tests or shadow database results into an operating deployment claim.
PostgreSQL and Redis containers were healthy. No task operating writes occurred.
A separate 20:39 UTC preservation snapshot hashes 13,067 original forecasts,
21,759 identity admissions, 1,889,307 mapping decisions, 5,230 artifact
registrations and 55,653 source resources. Ordinary background acquisition
continued between snapshots; its new resources are not attributed to this task.
The exact count receipt is [Phase 00 evidence](evidence/matchforge-v4-phase-00-2026-10-31.json).

The seven-source, 33-route normalizer map is present in
`providers/normalization/pipeline.py`. The champion remains
`transferable-rolling-goals-poisson-v1`, artifact
`e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4`.
`forecasting/products.py` provides 1X2, double chance, BTTS, totals, exact scores,
team goals and clean sheets. Tail/censored buckets retain explicit semantics.
`forecasting/corner.py` already supplies Poisson and NB corner baselines.
`forecasting/postmatch.py` scores categorical results and champion goal CRPS;
it does not establish broad statistical-market settlement or operating learning.

R3 remains `R3_PARTIAL_REMAINING_BLOCKERS`. Its 2026-10-16 checkpoint reports
253,098 eligible history rows and 2,409 forecastable fixtures. These are not the
2026-10-31 Resolution Center population: 4,160 unresolved mappings, 108
contradictions, 984 unsafe shared groups, 33 missing source resources and three
missing physical dataset files in `football_architecture_v2_shadow_20261016`.
The frozen 4,253 owner-proof population is also separate. None was recomputed or
relabelled by this phase. Existing current-status evidence remains authoritative
for each dated population.

Architecture V2 has code/evidence for phases 0–34 and 37. Phase 35 production
cutover and phase 36 retirement remain blocked: authentic evidence, full
production parity, explicit acceptance, 59 generic Elo conflicts and 327
insufficient-history targets remain unresolved. The Resolution Center is
implemented through phase 10 with warnings; its bounded approved workflows are
the owner for identity review/recovery and isolated migration preparation.

### Sources and tests used by the matrix

Paths below are repository-relative. Python production paths share the prefix
`python/football/src/football/`; unit tests share `python/football/tests/`.
Test pointers identify existing regression evidence; phase receipts distinguish
new executions from prior reports.

| Evidence group | Existing source/contracts | Existing tests/evidence |
| --- | --- | --- |
| Baseline | `docs/project-status.json`, `AGENTS.md`, `Makefile`, `docs/git-delivery.md` | `tests/test_architecture_v2_baseline.py`; Phase 00 runtime receipt |
| Policy | `docs/source-acquisition.md`, `README.md`, `docs/MVP-OPERATIONAL-PROVIDERS.md` | Prior owner-decision records; policy diff review |
| Governance | `forecasting/governance.py`, `forecasting/evaluation_protocol.py`, `docs/model-governance.md` | `test_forecasting_governance.py`; `docs/project-status.json` closed routes |
| Acquisition | `providers/sources/http.py`, `ingestion/acquisition.py`, `storage/raw.py`, `providers/runtime_policy.py` | `test_source_acquisition.py`, `test_provider_sources.py`, `test_provider_runtime_policy.py`, `test_provider_sync_policy.py` |
| Providers | `providers/{fotmob,pitchapi,statsbomb,football_data_uk}.py`, `product/{api_football,football_data_org,openfootball}.py` | Provider-specific unit tests; `tests/integration/test_operational_provider_sync.py` |
| Normalization | `providers/native/`, `providers/normalization/`, `normalization/football_data_uk.py` | `test_provider_native_records.py`, `test_resource_normalization.py`, `test_football_data_uk_normalization.py` |
| Observations | `contracts/observations.py`, `contracts/observations_v2.py`, `observations/storage.py` | `test_observation_contracts_v2.py`, `tests/integration/test_resource_observation_artifacts.py` |
| Identity | `product/{identity_admission,identity_trust,identity_crosswalks,resolution_identity,resolution_recovery}.py`, `identity/repository.py` | `tests/integration/test_product_identity_admission.py`, `tests/integration/test_resolution_recovery.py`; Resolution Center baseline/report |
| Capability | `providers/{resource_capabilities,capability_registry,resource_authority}.py` | `test_resource_capabilities.py`, `test_resource_authority.py`, `tests/integration/test_provider_resource_capabilities.py` |
| Coverage | `coverage/resources.py`, `coverage/storage.py`, `product/history_coverage.py` | `test_resource_coverage.py`, `tests/integration/test_resource_coverage_storage.py` |
| Work | `work/contracts.py`, `work/storage.py`, `product/history_work.py`, `product/provider_history_scopes.py` | `test_work_contracts.py`, `tests/integration/test_work_orchestration.py`, `tests/integration/test_lock_order.py` |
| Context | `context/live.py`, `context/contextual_features.py`, `context/historical_corpus.py` | `test_live_context.py`, `test_context_research.py`, `test_historical_context_corpus.py` |
| Live | `product/live_resources.py`, `product/operational_provider_sync.py`, `context/live.py` | `test_live_resources.py`, `test_operational_live_transitions.py`, `tests/integration/test_live_context.py` |
| Products | `forecasting/products.py`, `forecasting/model_contracts.py` | `test_forecast_products.py`, `test_multi_model_forecasting.py` |
| Models | `forecasting/{corner,model_runner,runtime_models,experiments,artifacts,snapshot}.py` | `test_corner_model.py`, `test_model_artifacts.py`, `test_feature_snapshots.py`, `tests/integration/test_runtime_model_registry.py` |
| Monitoring | `forecasting/{postmatch,postmatch_storage,postmatch_contract}.py` | `test_postmatch.py`, `tests/integration/test_postmatch.py` |
| Admin | `product/resolution_center.py`, `go/api/internal/app/`, `web/components/resolution-center.tsx` | `tests/integration/test_resolution_views.py`, `go/api/internal/app/resolution_center_test.go`, `web/components/resolution-center.test.tsx`, `web/e2e/` |
| Tests | Existing resource/identity/live/model suites in the groups above | New extensions must add domain-specific coverage; existing tests do not qualify missing providers/models |

### Requirements coverage matrix

Each row covers every functional bullet in the linked original numbered section;
its remaining work applies to the complete section. Repeated requirements share
implementation owners/phases rather than becoming duplicate tasks. `PARTIAL`
means `EXISTS_NEEDS_EXTENSION`; `PARTIAL_WITH_BLOCKER` means an existing
implementation has an explicit data/owner/scientific blocker; `SUPERSEDED` means the instruction/representation
is replaced prospectively, while its functional requirements remain mapped.
`ALREADY_COMPLETE_VERIFIED` is limited to the identified existing primitive/rule,
not a new operating rollout or a later-phase acceptance claim.

| Original section | Baseline classification | Source/test group | Current phase owner | Remaining work / disposition |
| --- | --- | --- | --- | --- |
| [0. CRITICAL OWNER DECISION — DEVELOPMENT DATA ACCESS](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Policy | 01 | Public acquisition already exists; record the broader current decision. |
| [1. IMPORTANT BOUNDARY — DO NOT MISINTERPRET THIS DECISION](references/matchforge-v4-original-110-section-prompt.md) | ALREADY_COMPLETE_VERIFIED | Admin | 01,23 | Internal authentication is separate; preserve existing controls. |
| [2. EXTERNAL DATA ACCESS — PRACTICAL BOUNDARY](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Acquisition | 01,03,06–13 | Keep explicit access classes and test ordinary public access. |
| [3. EMPIRICAL ACCESS POLICY](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Capability | 03,05–13 | Measure bounded access; adapter declarations alone are insufficient. |
| [4. REPOSITORY POLICY RECONCILIATION — MANDATORY](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Policy | 01 | Reconcile current docs/comments; preserve safeguards. |
| [5. UPDATE CONTRADICTORY REPOSITORY DOCUMENTATION](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Policy | 01 | Update only contradictory current policy. |
| [6. HISTORICAL DOCUMENTS / EVIDENCE MUST NOT BE REWRITTEN](references/matchforge-v4-original-110-section-prompt.md) | ALREADY_COMPLETE_VERIFIED | Governance | 01,23 | Historical decisions and reference text remain unchanged. |
| [7. CODE COMMENTS / VALIDATION ASSUMPTIONS](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Acquisition | 01 | Search for official-only rejection; retain quota/schema gates. |
| [8. RECORD THE OWNER DECISION DURABLY](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Governance | 01 | Append the current public development acquisition owner decision. |
| [9. EXISTING PROVIDERS FIRST](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Normalization | 03–05 | Audit retained and ignored resources before new providers. |
| [10. EIGHT MANDATED ADDITIONAL SOURCE INTEGRATIONS](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Providers | 06–13 | No adapters for the eight mandated providers exist at this baseline. |
| [11. MANDATORY DOES NOT MEAN BLIND](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Providers | 06–13 | Inspect wrappers, direct routes and actual bounded failures separately. |
| [12. ADDITIONAL PROVIDERS BEYOND THE MANDATED EIGHT](references/matchforge-v4-original-110-section-prompt.md) | NOT_APPLICABLE | Providers | 23 | No ninth provider is justified before the required audit and eight sources. |
| [13. MISSION](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Observations | 04,14,15 | Extend only measured gaps across all listed resource/context families. |
| [14. SPORTYBET-STYLE MARKET COVERAGE OBJECTIVE](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Products | 15,17–20,22 | Seven goal groups exist; broad qualified statistical markets do not. |
| [15. SELF-LEARNING ARCHITECTURE](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Monitoring | 21 | Reuse post-match monitoring and governed experiments for the complete feedback loop. |
| [16. SELF-CORRECTION](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Identity | 02,14,21 | Existing append-only corrections/recovery; extend qualified outcomes only. |
| [17. REPOSITORY RECONNAISSANCE](references/matchforge-v4-original-110-section-prompt.md) | ALREADY_COMPLETE_VERIFIED | Baseline | 00 | Startup status, source history, schema and runtime were inspected. |
| [18. CLASSIFY CURRENT IMPLEMENTATION](references/matchforge-v4-original-110-section-prompt.md) | SUPERSEDED | Baseline | 00 | Use CURRENT_TASK.md classifications and this coverage reference, not a second task system. |
| [19. R3 REMAINS FOUNDATIONAL](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL_WITH_BLOCKER | Identity | 02,14 | R3 remains partial; prospective evidence-backed recovery only. |
| [20. R3 PRIORITIZATION](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Identity | 02 | Prioritize verified impact; never infer proof from ranking. |
| [21. PROGRAMME ARTIFACTS](references/matchforge-v4-original-110-section-prompt.md) | SUPERSEDED | Baseline | 00–23 | Reuse current status, existing registries and one programme ledger; no parallel authoritative JSON stores. |
| [22. DATA ACCESS POLICY RECONCILIATION ARTIFACT](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Policy | 01 | Record searched policy, changed files, preserved evidence and unchanged auth in the programme report. |
| [23. PROVIDER CAPABILITY REGISTRY](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Capability | 03 | Existing scoped registry owns capability; attach access route evidence without replacing it. |
| [24. CAPABILITY STATES](references/matchforge-v4-original-110-section-prompt.md) | SUPERSEDED | Capability | 03,15 | Reconcile with current provider availability and market status vocabularies. |
| [25. PHASE 1 — EXISTING PROVIDER CAPABILITY AUDIT](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Providers | 03 | Seven real provider namespaces exist; test namespaces are not additional football sources. |
| [26. FOTMOB — DEEP AUDIT](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Normalization | 03,05,14 | Audit every listed FotMob fixture/stat/event/shot/player field and feature-specific season depth. |
| [27. API-FOOTBALL](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL_WITH_BLOCKER | Providers | 03,05 | API-Football fixture/competition/lineup/availability decode exists; plan access needs current evidence. |
| [28. FOOTBALL-DATA.CO.UK](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Normalization | 03,05 | CSV FT and six statistic pairs normalize; HT/referee/additional stable fields need gap review. |
| [29. PITCHAPI](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Normalization | 03,05 | Retained PitchAPI fixtures/shots/xG/events/player/lineup resources; frozen evaluations stay closed. |
| [30. FOOTBALL-DATA.ORG / OPENFOOTBALL](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Providers | 03,05 | Reuse existing fixture/history/identity and standings owners. |
| [31. STATSBOMB](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Providers | 03,05 | Pinned StatsBomb resources exist; protected research scopes remain isolated. |
| [32. EXISTING PROVIDER EXPANSION](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Acquisition | 05 | Measured retained-to-qualified enrichment remains to be executed. |
| [33. PUBLIC ENDPOINT / SCRAPER ENGINEERING](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Acquisition | 04–13 | Reuse bounded HTTP, cache, pagination, retry and raw retention; no new browser service without need. |
| [34. WRAPPER POLICY](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Providers | 06–13 | Review wrapper requests/licences and prefer small direct adapters where appropriate. |
| [35. EXISTING FIXTURE ENRICHMENT](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Identity | 05,14 | Use qualified fixture IDs, retained checks and shared work before new downloads. |
| [36. PHASE 2 — UNDERSTAT](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Providers | 06 | Understat results, shots/xG and attacking/defensive context require actual source investigation. |
| [37. CLUB ELO](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Providers | 07 | ClubElo dated ratings require verified native identity and availability times. |
| [38. SOFASCORE](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Providers | 08 | Sofascore rich/history/live resources require actual source investigation. |
| [39. ESPN](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Providers | 09 | ESPN schedules/results/live/events/statistics require actual source investigation. |
| [40. FBREF](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Providers | 10 | FBref team/player tables and histories require actual source investigation. |
| [41. WHOSCORED](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Providers | 11 | WhoScored events/formations/tactics require actual source investigation. |
| [42. FLASHSCORE](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Providers | 12 | Flashscore history/live/statistics require actual source investigation. |
| [43. SOCCERWAY](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Providers | 13 | Soccerway historical and independently proven live capability require actual source investigation. |
| [44. MANDATED PROVIDER COMPLETION](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Providers | 06–13 | One evidence-backed functional/partial/blocked disposition per source. |
| [45. PHASE 3 — CANONICAL IDENTITY / PROVENANCE](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Identity | 02,14 | Team/competition/fixture mappings exist; qualify player/coach/referee evidence without name-only merges. |
| [46. PLAYER IDENTITY](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Identity | 14 | Native/canonical player references exist; membership, transfer and duplicate-name coverage require measurement. |
| [47. RAW PROVENANCE](references/matchforge-v4-original-110-section-prompt.md) | ALREADY_COMPLETE_VERIFIED | Acquisition | 04–14,23 | Existing immutable raw manifests retain exact bytes, clocks, hashes and processing versions. |
| [48. PHASE 4 — FEATURE-AWARE HISTORICAL ACQUISITION](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Capability | 04,14 | ResourceScope already has provider/resource/competition/season; wire missing consumers only. |
| [49. BACKFILL PIPELINE](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Acquisition | 04,05,14 | Existing acquisition/normalization/identity/coverage owners must compose into resumable enrichment. |
| [50. HISTORICAL DEPTH](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Coverage | 03,14 | History depth must be measured per feature; operating V2 coverage tables are empty. |
| [51. POINT-IN-TIME RULES](references/matchforge-v4-original-110-section-prompt.md) | ALREADY_COMPLETE_VERIFIED | Observations | 04–23 | Separate knowledge/acquisition/provider/valid clocks; late old history cannot become earlier knowledge. |
| [52. CANONICAL RICH DATA](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Observations | 04,14 | Existing resource observations/storage cover most families; investigate rating/referee/manager gaps. |
| [53. MATCH STATS](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Normalization | 04,05 | Existing named team statistics are narrower than all requested fields. |
| [54. PERIOD STATISTICS](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Observations | 04,15,17 | Period strings exist; require explicit observed H1/H2/regulation/ET definitions and qualification. |
| [55. SHOT OBSERVATIONS](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Observations | 04,05,14 | Shots retain IDs/xG/time/coordinates where verified; xGOT/body/situation/relations need measured extension. |
| [56. PLAYER OBSERVATIONS](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Normalization | 04,05,14 | Lineup/limited player statistics exist; all listed minutes/shot/passing/defensive metrics need review. |
| [57. CONTEXT](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Context | 04,14,18 | Existing coach/availability/lineup/rest/travel features; measure qualified referee/venue/context coverage. |
| [58. MANAGER INTELLIGENCE](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Context | 04,14,18 | Tenure and coach preferences already exist; tactical/manager-matchup coverage and inputs remain gaps. |
| [59. LINEUP SEMANTICS](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Context | 04,14,15 | Existing predicted/probable/confirmed/fallback semantics must remain time-aware; audit actual starters. |
| [60. SEMANTIC REGISTRY](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Observations | 15 | Provider resource contracts exist; target-specific compatibility/settlement definitions remain missing. |
| [61. SPORTYBET / OPTA SEMANTICS](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Products | 15 | Do not infer SportyBet/Opta equivalence from provider field names. |
| [62. MARKET CAPABILITY REGISTRY](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Products | 15 | Market readiness is distinct from existing provider resource capability. |
| [63. MARKET STATUS](references/matchforge-v4-original-110-section-prompt.md) | SUPERSEDED | Products | 15 | Use current plan publication states plus separate diagnostic reasons; do not create competing enums. |
| [64. GOAL/RESULT MARKETS](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Products | 17 | Reuse score_products; audit DNB, ranges, handicaps, result combinations and censored tails. |
| [65. PERIOD MARKETS](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Products | 17 | Qualified half/interval models and period labels are prerequisites; no halved FT intensity. |
| [66. CORNERS](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Models | 18 | Existing Poisson/NB corner engines remain; additional team/period/race/dependence products need qualified labels. |
| [67. CARDS](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Models | 18,19 | Cards/card-points/player bookings require qualified targets and research gates. |
| [68. SHOTS / SOT](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Models | 18,19 | Separate qualified team/player shots/SOT models; preserve SOT<=shots where definitions permit. |
| [69. OTHER TEAM STATISTICS](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Models | 18 | Fouls/offsides/saves/tackles/throw-ins/goal-kicks/woodwork need appropriate data/distributions. |
| [70. PLAYER PARTICIPATION](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Context | 19 | Lineup prediction exists; calibrated participation/minutes distributions are not established. |
| [71. PLAYER MARKETS](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Models | 19 | Conditional player performance requires time-aware identity, usage and settlement targets. |
| [72. JOINT MARKET MODELING](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Products | 20 | Goal score joint distribution exists; cross-statistic dependence requires validated joint models. |
| [73. LIVE MULTI-PROVIDER SYSTEM](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Live | 16 | Reuse FotMob/PitchAPI live lanes; new providers join only with verified capability. |
| [74. LIVE OBSERVATIONS](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Live | 16 | Audit all requested period/clock/score/event/observation/freshness fields. |
| [75. LIVE RECONCILIATION](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Live | 16 | Existing lifecycle/conflict handling must extend to verified providers without response-time authority. |
| [76. PROVIDER FALLBACK](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Capability | 16 | Existing resource authority/quota/cooldown; no universal provider priority. |
| [77. FEATURE ENGINEERING](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Context | 14,18 | Reuse eligible attack/defence/Elo/rest/congestion/travel/coach features; extend referee/tactics/cup context only with evidence. |
| [78. INTERACTIONS](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL_WITH_BLOCKER | Models | 18–20 | Preregister manager/tactic/referee/availability/rest interactions; no sealed-outcome mining. |
| [79. FORECAST ARTIFACTS](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Models | 17–21 | Existing immutable model/forecast snapshots; market-specific target/uncertainty lineage needs extension. |
| [80. OUTCOME SETTLEMENT](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Monitoring | 21 | Existing corrected result settlement; extend qualified statistical targets and revisions. |
| [81. SELF-LEARNING REGISTRY](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Monitoring | 21 | Reuse immutable post_match_evaluations rather than a second feedback registry. |
| [82. METRICS](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Monitoring | 21 | Categorical log loss/Brier/RPS and champion-goal CRPS exist; broader count/calibration/participation diagnostics need extension. |
| [83. DRIFT](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Monitoring | 21 | Current monitoring review limits exist; statistical/feature/source/missingness/coverage drift needs measured extension. |
| [84. CHALLENGER PIPELINE](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Models | 21 | Existing experiments/governance own candidates; automate reproducible preparation only, never promotion. |
| [85. SCIENTIFIC FIREWALL](references/matchforge-v4-original-110-section-prompt.md) | ALREADY_COMPLETE_VERIFIED | Governance | 17–21,23 | Existing frozen protocol/firewalls remain binding on every new scientific route. |
| [86. API / FRONTEND / ADMIN](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Admin | 22 | Extend existing Go/Next fixture panel/Admin with truthful capabilities and version/cutoff/horizon/semantics. |
| [87. ADMIN DATA OPERATIONS](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Admin | 22 | Existing sync/Resolution Center owns controls; add rich-data/market diagnostics without another Admin. |
| [88. PROVIDER TESTS](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Tests | 04–14 | Existing cache/schema/retry/quotas/fencing tests; each new source needs its own meaningful regressions. |
| [89. IDENTITY TESTS](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Identity | 02,14 | Existing identity/orientation/correction tests; extend for verified player transfers and provider-ID changes. |
| [90. PIT TESTS](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Observations | 04–23 | Existing cutoff/correction/same-batch tests must cover new resource consumers. |
| [91. MARKET DATA TESTS](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Tests | 04,14,15,18–21 | Existing missing/zero and period/unknown-value tests; add target-specific semantic/participation/correction tests. |
| [92. LIVE TESTS](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Live | 16 | Existing lifecycle tests; cover each new provider transition/conflict/fallback. |
| [93. MODEL TESTS](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Models | 17–21 | Reuse model/numerical/artifact tests; new qualified products require matching coherence/cold-start tests. |
| [94. PERFORMANCE](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Work | 04–23 | Reuse cached hashes, scopes, batch work and model loading; verify bounded incremental consumers. |
| [95. PROVIDER POLITENESS / RESOURCE CONTROL](references/matchforge-v4-original-110-section-prompt.md) | ALREADY_COMPLETE_VERIFIED | Acquisition | 05–16 | Existing runtime policies/accounting provide bounds/cache/cooldown/failure isolation; preserve in new adapters. |
| [96. REQUIRED PROVIDER REPORT](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Coverage | 03,14,23 | Provider report must use measured access/depth/qualification, not declarations. |
| [97. REQUIRED MANDATED PROVIDER REPORT](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Providers | 06–13,23 | Per-provider report records tests, blockers, incremental value and all requested resource fields. |
| [98. REQUIRED MARKET REPORT](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Products | 15,23 | Per-market readiness report must include semantics, history, model, evaluation and next action. |
| [99. ADDITIONAL PROVIDER REQUIREMENTS](references/matchforge-v4-original-110-section-prompt.md) | NOT_APPLICABLE | Providers | 23 | Assess additional sources only after existing plus eight-source evidence. |
| [100. REQUIRED POLICY REPORT](references/matchforge-v4-original-110-section-prompt.md) | NOT_IMPLEMENTED | Policy | 01,23 | Include explicit policy reconciliation and preserved internal auth in delivery report. |
| [101. PHASE EXECUTION ORDER](references/matchforge-v4-original-110-section-prompt.md) | SUPERSEDED | Baseline | 00–23 | CURRENT_TASK.md phases 00–23 and separate commits replace the older A–J ordering. |
| [102. DO NOT STOP AT PLANNING](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Baseline | 00–23 | Implement unblocked engineering after reconnaissance; ledger alone is not delivery. |
| [103. FINAL DELIVERABLES](references/matchforge-v4-original-110-section-prompt.md) | SUPERSEDED | Baseline | 00–23 | Deliver equivalent evidence through existing registries and concise reports, not duplicate authoritative systems. |
| [104. FINAL REPORT](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Baseline | 23 | Report actual before/after, commits, evidence, limitations and exact resume actions. |
| [105. FINAL ACCEPTANCE — DATA ACCESS POLICY](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Policy | 01,23 | Verify every external-access acceptance item and preserved internal authorization. |
| [106. FINAL ACCEPTANCE — PROVIDERS](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Providers | 03–14,23 | Audit existing and eight sources, retain bytes/native IDs and resumable qualification. |
| [107. FINAL ACCEPTANCE — DATA QUALITY](references/matchforge-v4-original-110-section-prompt.md) | EXISTS_NEEDS_EXTENSION | Observations | 04–23 | Revalidate identity/semantics/PIT/lineage/missingness for new consumers. |
| [108. FINAL ACCEPTANCE — MARKETS](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL_WITH_BLOCKER | Models | 17–20,23 | Production/statistical qualification cannot be asserted without frozen evaluations and qualified data. |
| [109. FINAL ACCEPTANCE — SELF-LEARNING](references/matchforge-v4-original-110-section-prompt.md) | PARTIAL | Monitoring | 21,23 | Extend existing immutable scoring/corrections/drift/challenger loop under promotion governance. |
| [110. EXECUTE NOW](references/matchforge-v4-original-110-section-prompt.md) | SUPERSEDED | Baseline | 00–23 | Execute CURRENT_TASK.md; retain all functional coverage and explicit owner gates from this reference. |

### Requirements carried into existing phases

The reference adds detail to existing phases, without authorizing another system:

- Phase 04/14 includes manager tenure, tactical characteristics, referee/venue
  observations, dated strength ratings, all requested shot/player/team fields,
  lineup-state distinctions and time-aware player membership when supported by
  actual source evidence. Existing coach, lineup, rest and travel builders remain.
- Phase 15 owns target-level compatibility, nonappearance/void/correction rules,
  explicit publication status separate from blocker reasons, and every market
  group in reference sections 64–72.
- Phase 18 owns evidence-backed manager/tactic/referee/rest/travel/cup-context
  features and preregistered interactions alongside team-statistic models. This
  does not authorize training, reopening closed routes or promotion.
- Phase 21 owns broader calibration/count/participation/tail metrics, versioned
  settlements, coverage/missingness/provider-definition drift and reproducible
  challenger preparation through existing monitoring/experiment owners.
- Phase 23 reports feature depth, provider/player/market/outcome qualification and
  actual additional-source needs using existing evidence rather than duplicating
  authoritative capability/work/identity registries.

### Checkpoints

Phase 00 verification and commit are recorded in the phase evidence and local
`CURRENT_TASK_STATUS.md`. Future phases append receipts here or link their
existing durable evidence. No phase 01+ feature work, source request, identity
approval, model fit, evaluation, promotion, production cutover or retirement was
performed during reconciliation.

Phase 00 verification: `make check integration` exited 0. Python unit tests:
1,758 passed; Rust: 16 passed; frontend: 107 passed. Format, lint, types,
architecture, project status, package/Go/frontend builds, fresh-database migrations
and storage/API integration passed. Seven upstream NumPy deprecations and one
pre-existing ESLint unused-parameter warning remain. The 111-section coverage,
original-reference checksum and unchanged prior project-status fields were also
checked. `git diff --check` passed. No production schema migration was executed.

## Phase 01 — development data-access policy

Phase 00 commit: `bfb581e14f2a97917e5f7da87919b88aec479bf1` (parent
`8b82dd637449a18ea6086853344e8bc7b0e0f2e2`). Pushed to the programme branch;
review: https://github.com/sir-radar/match-forge/pull/178.

The new append-only owner decision records public JSON/browser/HTML, embedded
state, feeds, datasets and community wrapper/scraper routes as valid development
options. `docs/source-acquisition.md` owns the current policy and README links it.
An official API is not required; empirical access, source use conditions, retained
bytes, identity, semantics and PIT qualification still apply. Already-authorized
V4 requests need a documented budget within that scope, not repeated routine
approval. Frozen evaluations, production cutover and promotion remain gated.

Policy review searched AGENTS.md, README.md, local PLAN.md, current docs, provider
clients, capability/configuration/credential contracts, source transports and
scripts for official-only, undocumented/public/browser-endpoint and scraping
restrictions. Existing FotMob acquisition already uses public endpoints. No
production code rejects a source solely for being unofficial. The bounded
PitchAPI/FotMob development preview allowlist reflects implemented feature
compatibility and stays unchanged. The older blanket live-call approval wording
in the current source policy now distinguishes an already-authorized V4 scope
from separately frozen scientific scopes.

Historical owner decisions, source/evaluation evidence, ADR 0003, the original
reference, internal admin contracts/code and authentication tests are unchanged.
MVP operational-provider documentation already permits ordinary public FotMob
requests with explicit technical restrictions; no contradictory change was
needed there. No adapter, authentication flag, environment variable, migration,
production model, provider request or operating data changed in this phase.

Phase 01 verification: `make project-status-check` exited 0;
`. ./scripts/toolchain.sh; uv run --locked --no-sync pytest python/football/tests/test_project_status.py`
exited 0 (21 passed); `git diff --check` passed. No executable code or
API/authentication tests changed. Baseline aggregate checks from Phase 00 remain
applicable; no additional build/integration run was needed for policy metadata.

## Phase 02 — retained identity review

Status: BLOCKED_WITH_EVIDENCE. Phase 01 commit:
`6331628f66951b995ce690121558ac26f23d7003` (parent
`bfb581e14f2a97917e5f7da87919b88aec479bf1`).

Read-only operating Resolution Center queries found 108 recorded contradictions
and zero recorded NEEDS_REVIEW cases; these are current review classifications,
not a replacement for the separate frozen audit populations. The three largest
pending competition impacts cover 287/263/255 upcoming stored fixtures and
7,823/3,602/2,714 total stored fixtures respectively. Their existing admission
previews reject `UNSUPPORTED_ORIGIN_ALGORITHM`. The three largest contradictory
team impacts cover 301/293/243 stored fixtures; their previews reject
`ORIGIN_UUID_MISMATCH`. Two retained correction previews additionally reject the
source pair because the current correction owner requires retained FDO and
API-Football mappings. Counts describe per-case stored impacts and are not summed
or relabelled as newly qualified history.

[Exact case/source/hash evidence](evidence/matchforge-v4-phase-02-2026-10-31.json)
records read-only preview versions and resume points. No exact independent target
proof or owner case approval was supplied. No new identity algorithm, name-only
merge, admission, file recovery or history replay was invented. Task changes:
zero qualified identities, corrected contradictions, unlocked history rows or
forecastability changes. These are task deltas, not a global population delta
while ordinary synchronization continues. R3 remains partial.

Resume: obtain source-backed origin/crosswalk evidence for the exact listed native
IDs, refresh the existing previews, obtain the required case approval, then run
existing scoped recovery and remeasure eligibility. Raw/provider capability
investigation in Phase 03 is independent and can continue. Canonical/model use
of these affected cases remains blocked.

Phase 02 verification: read-only case review, impact ranking and retained previews
exited 0. `make project-status-check` and `git diff --check` exited 0. Existing
workflow regression suites passed in Phase 00; executable code is unchanged.

## Phase 03 — existing-provider capability and market-data audit

Status: PASS_WITH_WARNINGS. Phase 02 blocker checkpoint commit:
`956d0f7950c89cc1b7bdbacc1605cbd75435bc66` (parent
`6331628f66951b995ce690121558ac26f23d7003`). Identity-qualified use of its
affected cases remains blocked; this audit is independent.

The new `football.providers.data_audit` command reads the existing source,
operational observation and capability/authority/coverage tables in one read-only
repeatable-read transaction. It streams native statistic rows and writes an
immutable diagnostic report through the current file store. It does not create
a registry, acquire data, decide eligibility or fit a model. The documented
operator command is in `docs/source-acquisition.md`.

The final operating snapshot contains 8,838 source-field/competition/season/period
groups and 1,305 recorded resource scopes. FotMob reports 46 distinct statistic
keys and PitchAPI 41. Recorded statistic fixture dates span 2–31 October 2026;
this does not establish finalized labels, qualified historical coverage or matching
depth for the much older fixture-history corpus. Current competition display
labels never substitute for stored canonical season IDs. Unknown IDs stay null.

Measured gaps include Offsides, blocked/off-target shots, passing, tackling,
interceptions, woodwork and xGOT outside the current named statistic vocabulary.
Nonnumeric headings remain distinguishable from usable numeric measurements.
A byte-verified current Football-Data.co.uk archive contains 2,027 rows with
non-null HT scores/results and 934 referee fields. It has no offsides, woodwork
or free-kick columns; none are fabricated. One retained resource from each of
the seven existing providers passed its registered checksum check. StatsBomb
verification used only its competition catalog, without protected match/events.

[Phase 03 evidence](evidence/matchforge-v4-phase-03-2026-10-31.json) contains the
seven-provider inventory, all 18 requested resource-family gaps, unused decoder
paths, field-depth summaries, exact sample hashes, access route classes and the
prioritized existing-provider expansion. The full local immutable report is
`4ace1ff3681e7aeff46ffbd1f3fc93e5d86d345a197b83d35654937bd23a4e89`.
Registrations and sampled bytes are separate from whole-scope access/retention.
Legacy AVAILABLE/ELIGIBLE flags are retained as recorded facts, not relabelled
as new identity, target-semantic, PIT or model qualification.

Priority: preserve/use already retained numeric fields, observed CSV HT/referee
data and existing routes before additional requests; then measure existing-source
entitlements and rich historical depth. New provider phases follow that measured
work. API-Football standings already has a source method but lacks a V2 decoder;
football-data.org standings already has both and must not be rebuilt. Existing
coach/context, raw-file, normalizer and work owners remain in place.

Verification: the focused unit and PostgreSQL suite passed 9 tests in a disposable
database/data root. Tests prove revision/fixture separation, repeated-measurement
counts, zero versus missing, rejection of nonfinite measurements, unknown-field
and unknown-provider reporting, no qualification invention, read-only operation
and preservation of caller transactions. Ruff/format, strict mypy on the changed
Python files, architecture checks and shell syntax passed. Existing storage
integration now includes the new transaction tests. The final operating audit,
seven checksum samples and CSV measurement each exited 0. No operating mutation,
provider request, identity approval, scientific evaluation or promotion occurred.

Python sdist/wheel build also exited 0. Archive inspection confirms the exact new
audit module is packaged and credentials, local caches and Git metadata are
excluded. The build emitted a cache-location warning; exclusion was checked
directly. Final project-status and diff checks passed.

## Phase 04 — rich source observation contracts

Status: PASS (contract/engineering checkpoint). Phase 03 commit:
`1b431b7fcbdaaa0cc55d146141258a544621e0f1` (parent
`956d0f7950c89cc1b7bdbacc1605cbd75435bc66`).

Immutable registered V1/V2 schemas cannot be widened. V3 therefore defines rich
team/player counts, shot context/xGOT, observed period scores, referee assignments
and source calendar ratings. Existing resource scopes, source references, artifact
registration, retry/storage and temporal eligibility are reused. No SQL migration,
provider client, canonical identity, forecasting model or operating routing changed.
Existing coach, formation, lineup and availability contracts remain in place.

Unknown measurements/semantic versions remain null. Compatible count subsets,
paired shot context and period/score basis are validated; invalid values are not
clipped. Referee labels retain exact source references without name-derived IDs.
Calendar rating dates cannot supply an unknown football event time. Semantic
version claims are data, not qualification decisions. The owning rules are
documented in `docs/data-model.md`.

[Phase 04 evidence](evidence/matchforge-v4-phase-04-2026-10-31.json) records the
six contracts and frozen schema hashes. V1 remains `5028f7b2…40beac14`; V2 remains
`f1490653…6eecfbc`; V3 is `eeb6e65f…0dfab4b5`. Full hashes are in the receipt.
The final focused unit/normalizer/PostgreSQL run passed 179 tests in disposable
storage. Further focused checks passed after pinning V3 and adding count/rating
boundaries. Integration proves V3 retry/load, unchanged prior V2 bytes/schema, and
exclusion of calendar ratings with unknown event time from football history.
Ruff/format, strict mypy on four changed Python files, architecture and shell
syntax passed. No operating write, provider call, evaluation, fit or promotion ran.
Phase 05 must supply actual measured decoders; schema support is not source or
market availability. R3 and production migration gates remain unchanged.

## Phase 05a — retained CSV half-time and referee observations

Status: PASS. Phase 04 commit: `82d9784cf915f7023ec0f9dfb1ed0acc72426ca2`.

The existing statistics decoder now emits observed first-half scores and referee
assignments using V3. The collector selects the contract's own metadata version;
existing V2 outputs retain their prior version strings. Invalid or contradictory
half-time scores are reported independently without deleting valid team/referee
observations. Referee names retain source references without creating identities.
No second-half score, missing zero, or historical publication time is inferred.

The checksum-verified registered 2026/27 archive produced 2,027 first-half scores,
934 referee assignments and the existing 4,054 team-statistic observations, with
no findings. The prior decoder emitted neither new family. This is measured
source-normalization improvement; identity, market and PIT qualification remain
separate. The immutable local replay report is
`3b4b1efcb0b6d5f8ffdd5370b92c80f54262d3fb4b8781ac4f12a2f4c65df7ed`.

[Phase 05a evidence](evidence/matchforge-v4-phase-05a-2026-10-31.json) records the
source hash and counts. Focused CSV/existing-normalizer tests passed 49 cases;
Ruff/format, strict mypy on changed files and architecture checks passed. Replay
used a read-only connection and local report files. No operating observations,
identities, forecasts, artifacts or source bytes were written; no provider calls,
fits, evaluations or promotions ran. Existing migration gates remain unchanged.

## Phase 05b — retained FotMob/PitchAPI rich measurements

Status: PASS_WITH_WARNINGS. Phase 05a commit: `14ef312`.

Existing decoders now retain measured off-target/blocked shots, offsides, passes,
accurate passes/crosses, tackles, interceptions, clearances, woodwork and xGOT.
Player observations add source-reported pass totals, accurate passes, SOT,
tackles, interceptions, fouls, saves, xG and xA. Shots retain source body-part and
situation strings and xGOT. V3 is selected only when new fields are present; old
V2-only payloads remain V2. No existing schema or observation bytes were rewritten.

Count-plus-percentage text is parsed strictly only for the measured passing
fields. Player pass totals come from the explicit source fraction total, never
from dividing by a rounded percentage. Conflicting duplicates remove the
ambiguous field. Missing values, zeroes and unsupported source fields remain
distinct. Coordinates remain unknown without a verified frame. Category strings
and source counts do not establish sportsbook equivalence.

Six checksum-verified retained resource/decoder replays produced 12 rich team
observations across full match/H1/H2, 60 rich player observations and 48 rich
shots. These fields were previously absent from named outputs. Existing xG and
participant outputs remain. The samples concern two matches, not whole-provider
coverage. Unknown measurements and partial-period xG are still reported;
PitchAPI has 30 pre-existing empty-key Shotmap findings.

[Phase 05b evidence](evidence/matchforge-v4-phase-05b-2026-10-31.json) records exact
source/report hashes, non-null counts and findings. The existing/rich suite
passed 52 cases; the expanded boundary suite passed 15. Ruff/format, strict mypy
on six changed files and architecture checks passed. No provider request,
operating mutation, fit, evaluation or promotion occurred.
