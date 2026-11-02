# MatchForge data status audit and remediation plan

Audit date: **2026-11-02**. Source checkout: `e5b9b88` (`ft/data-status-audit`).
The original audit is preserved below. **Execution checkpoints added on 2026-11-02 are in section L; its results supersede the audit-only delivery state for subsequent remediation work.**

Delivery of the original audit: audit and plan only. **No database changes, recovery jobs, acquisition, migrations, model fits, evaluations, publication, or cutover were performed by this audit.** Local audit evidence and this report were written. Existing workers continued independently.

## A. Executive summary

The retained data is usable in established scopes, but data acquisition, identity qualification, historical coverage, and derived reporting are at different stages. A provider response or a `published` registration does not prove that its files, identity chain, historical eligibility, market labels, or model qualification are valid.

The operating database has **131 base tables, 18 views, and 15,545,157 stored table rows** in snapshot S1. This is a metadata census, not a claim that every football value was independently validated. Table rows include revisions, events, metrics, historical decisions, and overlapping representations of the same matches. **There is no defensible global count of unique affected matches obtained by adding these populations.**

| Population / evidence | Inspected | Healthy or accepted | Unresolved / failed / blocked |
| --- | --- | --- | --- |
| Registered raw resources / S1,S3 | 66,925 across 42 provider registrations | 66,892 exact-byte checks pass | 33 unverifiable registrations; 30 repeated `c` hashes and 3 repeated `f` hashes; test-shaped provenance |
| Datasets / S1,S3 | 24 published versions; 763 file rows | 2 versions pass all registered physical file checks | 22 missing manifests; 3 registered dataset files also missing; no registered input lineage on those 22 |
| Models / S1,S3 | 5,230 published registrations | 5,204 pass existing manifest/file/logical-state verification | 26 cannot verify because manifests are missing; 13 dependent forecasts all already retired under the approved test-only exclusion |
| Active team/competition mappings / S4 | 20,805 | 15,749 currently admitted | 4,947 reclassified UNRESOLVED; 108 CONTRADICTORY; 1 REVOKED; 984 unsafe shared identity groups |
| Shared work / S1 | 94,992 work IDs | 93,285 SUCCEEDED | 1,030 FAILED; 518 RETRY_WAIT; 1 RUNNING; 158 CANCELLED; zero PENDING/BLOCKED |
| Provider history scopes / S1,S2 | 1,224 provider/competition/season keys | 2 SUCCEEDED | 873 PENDING; 338 FAILED; 11 DEFERRED; zero RUNNING |
| Legacy history queue / S1,S2 | 641 distinct jobs | 135 SUCCEEDED | 506 PENDING: 495 quota/cooldown, 11 deterministic identity-conflict failures |
| Competition availability / S1 | 1,657 | 220 FORECAST_AVAILABLE | 1,022 NOT_ENOUGH_HISTORY; 361 SOURCE_DATA_INCOMPLETE; 54 NO_FIXTURES |
| Market family diagnostic / S5 | 67 unbound families in the stated pilot scope | 0 supported by this diagnostic | 53 DATA_COLLECTION_REQUIRED; 14 INSUFFICIENT_PLAYER_DATA; 0 RESEARCH_REQUIRED in operating diagnostic |
| External predictions / S1,S2 | 1,304 prediction IDs | 47 MATCHED; current settlements 19 WON + 5 LOST | 1,250 UNMATCHED; 7 AMBIGUOUS; 1,280 current PENDING settlements; these are overlapping dimensions |
| Validation / S1,S2 | 2,184 finding rows | 2,146 WARNING findings handled by existing policy | 38 QUARANTINE findings over 38 source resources/match IDs; not 38 quarantine queue rows |
| Context refresh / S2 | 228,599 fixture-generation worklist entries | 51,696 completed generations | 176,903 pending generations; no recorded error on that backlog |

The status inventory contains **486 case-sensitive status/classification values**: **282 observed across 65 persisted status dimensions and 204 definition-only values**. Of the observed values, 200 are unconstrained native provider labels, including match-clock strings. These counts describe the bounded inventory in B, not 486 independent business states or 486 problems. Computed market, identity, integrity, and API diagnostics are counted separately from persisted fields. Zero-count configured values are retained.

Highest-impact causes are unproved identity relationships, disabled/blocked historical acquisition, blanket retry classification for deterministic database failures, a large bounded report backlog, incomplete target-specific qualification, and a gap between repository migrations and deployed recovery capabilities. Source/manifest diagnostics also mix historical test lineage with real source registrations. Current provider access must be checked against permission, not just HTTP success.

Expected benefit is measurable completion of eligible scopes, fewer repeated deterministic attempts, correct identity and source diagnostics, and fresh read reports. **No numerical promise of recovered matches or newly supported markets is justified yet.** Most engineering tasks can proceed autonomously when separately invoked. Exact ambiguous identities, unavailable authentic bytes, provider permissions/spend, and new scientific authorization remain conditional or owner-dependent. Existing healthy forecasts and their champion must be preserved.

### Environment, freshness, and evidence

The local `.env` database is `football`, reached through localhost port 55433, PostgreSQL **18.6**. Credentials were used without printing or copying them. All database audit connections enforce `default_transaction_read_only=on`; collections use repeatable-read read-only transactions, followed by rollback. The original restricted sandbox denied localhost and branch creation; reviewed access then succeeded. No review rejection remains.

| ID | Local evidence | Snapshot window | Content |
| --- | --- | --- | --- |
| S1 | [`snapshot.json`](../../.local/data-status-audit/snapshot.json) | 2026-11-02 06:20:39–06:20:56 UTC | Complete table/column/check-constraint/key census and base status counts |
| S2 | [`detail.json`](../../.local/data-status-audit/detail.json) | 2026-11-02 06:23:13–06:23:44 UTC | Status breakdowns, error/age groups, latest decisions, recovery prerequisites |
| S3 | [`files.json`](../../.local/data-status-audit/files.json) | 2026-11-02 06:25:00–06:26:16 UTC | All registered raw resources, dataset file bytes, model artifacts, normalized observations/capabilities, source-manifest paths |
| S4 | [`identity-audit.json`](../../.local/data-status-audit/identity-audit.json) | 2026-11-02 06:26:01–06:26:29 UTC | Existing ProviderIdentityAuditV2; current classifications and shared-group findings |
| S5 | [`extra.json`](../../.local/data-status-audit/extra.json) | 2026-11-02 06:29:48–06:31:01 UTC | Operating market/provider diagnostics and five existing shadow/research databases |
| S6 | [`final-queries.json`](../../.local/data-status-audit/final-queries.json) | 2026-11-02 06:33:24 UTC | Artifact dependency counts, existing function signatures, report keys, stale fixtures |
| S7 | [`safety-tail.json`](../../.local/data-status-audit/safety-tail.json) | 2026-11-02 06:35:26 UTC | Retirement overlap, result-conflict breakdown, fixture lifecycle age |

All times above are UTC; Africa/Lagos is UTC+1. Each collection records its own PostgreSQL snapshot ID. **S1–S7 are separate snapshots**, not one database-wide freeze across the entire audit. In particular, S2 sees two running provider jobs where S1 saw one. Do not combine their moving totals as though simultaneous. Source files are immutable by contract; this audit did not take a filesystem or database backup and cannot prove there were no out-of-band concurrent file changes.

The ignored `.local/data-status-audit/` directory retains query SQL, parameters, results, exact collectors, status scans, and detailed file failures. Its hashes are in I. Report tables retain the important results independently; local receipts are not committed. Query recipes below can refresh counts, but an expired PostgreSQL snapshot identifier cannot reconstruct a past snapshot. Restoring an existing approved baseline into a separate database is the route to an exact historical replay.

Five existing non-operating databases were read for registry state. These observations are not operating coverage or an acceptance of their artifacts:

| Database | Latest applied migration | Observation artifacts | Canonical resolutions | Canonical coverage rows |
| --- | --- | --- | --- | --- |
| `football_architecture_v2_shadow_20261016` | 202610200100 | 3153511 | 10192 | 0 |
| `football_v4_qualification_r02_20261101` | 202610310800 | 0 | 0 | 0 |
| `football_v4_expansion_r03_20261101` | 202610310800 | 9704 | 0 | 0 |
| `football_v4_access_r04_20261102` | 202610310800 | 203721 | 0 | 0 |
| `football_v4_unblocking_r02_replay_20261102` | 202610310800 | 10 | 0 | 1 |

All four V4 research databases retain 13 `LEGACY` stage routes. The architecture shadow predates that table; its missing `resolution_stage_settings` is an expected version difference, not proof of a failed migration. The operating database is applied through **202610310500**, while the repository and V4 research databases include **202610310600/700/800**. No migration was run.

Audit limits: no remote production environment was established, no provider data endpoints were called by this audit, no entitlement/dashboard login was used, no Redis contents or external object-store backup were inspected, and no protected evaluation was executed or protected outcome content reconstructed. Player participation totals came from metadata queries. Dataset verification checked physical bytes only, not Parquet values or logical checksums; model verification used the existing full read-only verifier. A remote backup or missing original payload may exist outside this workspace. Network availability and API plan rights are not proved by retained files.

Current project status remains unchanged: Architecture V2 cutover/retirement phases 35/36 are blocked; V4 Issue 2 is incomplete despite its bounded five-fixture research milestone. Closed failed modelling routes and the protected 280 Sprint 2 targets are not reopened. No active Wayfinder ticket was claimed or mutated; this is the owner-requested audit, not map implementation.

## B. Complete status inventory

### Units and classifications

Status counts are scoped to **table + column + snapshot**, not the spelling alone. Current records, historical events, resource revisions, and findings are different units. `NULL`, empty source strings, unknown values, unsupported capability, cancellation, legitimate no-data results, and failed scientific gates are not interchangeable. A zero below means an allowed value has no rows in that queried relation; **N/A means there is no measured persisted population for a computed or dormant code path**.

The root-cause column routes mixed statuses to C; it does not declare every healthy or transitional row defective. Severity is P0 for integrity/authorization gates, P1 for recovery/reliability, P2 for diagnostics. For mixed dimensions, the unresolved subset determines the listed investigation priority.

| Status and count | Stage / persisted owner | Provider/dataset evidence | Total row population | Classification | Root cause | Severity |
| --- | --- | --- | --- | --- | --- | --- |
| `acquired` 3; zero each: `quarantined`, `validated` | `acquired_resources.status` | S1 | 3 | Healthy claims; qualification is scope-dependent | I01/I02 | P1/P2 |
| `acquired` 3; zero each: `acquiring`, `discovered`, `failed`, `quarantined`, `validated` | `acquisition_jobs.status` | S1 | 3 | Healthy claims; qualification is scope-dependent | I01/I02 | P1/P2 |
| `published` 9,985 | `baseline_forecasts.status` | S1 | 9,985 | Healthy claims; qualification is scope-dependent | I16/I17 | P1/P2 |
| `published` 1; zero each: `verified_existing` | `canonical_change_sets.status` | S1 | 1 | Healthy claims; qualification is scope-dependent | I16/I17 | P1/P2 |
| zero each: `COMPLETE`, `PARTIAL`, `UNKNOWN` | `canonical_resource_coverage.status` | S1 | 0 | Dormant; no rows | I10/I11 | P0 |
| zero each: `QUARANTINED`, `RESOLVED`, `REVIEW_REQUIRED` | `canonical_resource_resolutions.disposition` | S2 | 0 | Dormant; no rows | I16/I17 | P1/P2 |
| `published` 24 | `dataset_versions.status` | S1 | 24 | Healthy claims; qualification is scope-dependent | I01/I02 | P1/P2 |
| zero each: `AFFECTED_BY_SOURCE_CORRECTION`, `REBUILD_REQUIRED`, `SUPERSEDED` | `derived_state_events.state` | S1 | 0 | Dormant; no rows | I16/I17 | P1/P2 |
| zero each: `MATCHED`, `UNMATCHED` | `external_prediction_bindings.match_status` | S1 | 0 | Dormant; no rows | I13/I15 | P1/P2 |
| `ENABLED` 10; `NO_PREDICTIONS` 6; `TECHNICALLY_UNAVAILABLE` 4 | `external_prediction_collection_attempts.status` | S1 | 20 | Mixed; see lifecycle and root-cause sections | I13/I15 | P1/P2 |
| `NOT_APPLICABLE` 716; `VERIFIED` 588; zero each: `MISMATCH`, `UNKNOWN` | `external_prediction_date_reviews.date_status` | S1 | 1,304 | Healthy claims; qualification is scope-dependent | I13/I15 | P1/P2 |
| `FINISHED` 110; `LIVE` 77; `POSTPONED` 4; `SCHEDULED` 29; `UNKNOWN` 1,257 | `external_prediction_result_revisions.fixture_status` | S1 | 1,477 | Mixed; see lifecycle and root-cause sections | I13/I15 | P1/P2 |
| `LOST` 11; `PENDING` 1,409; `WON` 57; zero each: `VOID` | `external_prediction_result_revisions.settlement_state` | S1 | 1,477 | Mixed; see lifecycle and root-cause sections | I13/I15 | P1/P2 |
| `DISABLED` 1; `ENABLED` 5; zero each: `NOT_IMPLEMENTED` | `external_prediction_sources.adapter_status` | S1 | 6 | Mixed; see lifecycle and root-cause sections | I13/I15 | P1/P2 |
| `ALLOWED` 1; `TECHNICALLY_AVAILABLE` 4; `TECHNICALLY_UNAVAILABLE` 1; zero each: `AUTH_REQUIRED`, `PAID_ONLY`, `PARSER_BROKEN`, `REVIEW_REQUIRED`, `UNSUPPORTED_ANTI_BOT`, `UNSUPPORTED_ROBOTS`, `UNSUPPORTED_TERMS` | `external_prediction_sources.automated_access_status` | S1 | 6 | Mixed; see lifecycle and root-cause sections | I13/I15 | P1/P2 |
| `AMBIGUOUS` 7; `MATCHED` 47; `UNMATCHED` 1,250 | `external_predictions.match_status` | S1 | 1,304 | Mixed; see lifecycle and root-cause sections | I13/I15 | P1/P2 |
| zero each: `AUTHENTICATION_FAILURE`, `DISABLED_NOT_CONFIGURED`, `FIXTURE_NOT_PREDICTABLE`, `MAPPING_FAILURE`, `MISSING_PROBABILITIES`, `PLAN_RESTRICTION`, `PROVIDER_OUTAGE`, `RATE_LIMIT`, `SUCCESS`, `TIMEOUT` | `external_probability_benchmarks.collection_status` | S1 | 0 | Dormant; no rows | I13/I15 | P1/P2 |
| zero each: `AMBIGUOUS`, `MATCHED`, `UNMATCHED` | `external_probability_benchmarks.mapping_status` | S1 | 0 | Dormant; no rows | I13/I15 | P1/P2 |
| `AMBIGUOUS_QUARANTINED` 3,208; `DUPLICATE_RESOLVED` 19,883; `IMPOSSIBLE_TEAM_SCHEDULE_QUARANTINED` 11,806; `UNIQUE` 318,997 | `fixture_identity_resolutions.resolution_status` | S1 | 353,894 | Mixed; see lifecycle and root-cause sections | I03/I04 | P0 |
| zero each: `quarantined`, `succeeded` | `fixture_processing_attempts.processing_status` | S1 | 0 | Dormant; no rows | I16/I17 | P1/P2 |
| zero each: `not_published`, `published` | `fixture_processing_attempts.publication_status` | S1 | 0 | Dormant; no rows | I16/I17 | P1/P2 |
| `NULL` 10; `processing` 200; `scheduled` 247; `unscheduled` 587 | `match_observations.provider_360_status` | S1 | 1,044 | Native source labels; historical snapshots | I16/I17 | P1/P2 |
| 1,044 rows; 2 labels including NULL where present (detail below) | `match_observations.provider_status` | S1 | 1,044 | Native source labels; historical snapshots | I16/I17 | P1/P2 |
| `published` 5,230; zero each: `rejected`, `retired` | `model_artifacts.status` | S1 | 5,230 | Healthy claims; qualification is scope-dependent | I01/I02 | P1/P2 |
| zero each: `failed`, `reused`, `running`, `succeeded` | `model_fit_runs.status` | S1 | 0 | Dormant; no rows | I16/I17 | P1/P2 |
| `conflicting` 7; `consistent` 1,240 | `player_observations.fact_status` | S1 | 1,247 | Mixed; see lifecycle and root-cause sections | I12 | P1/P2 |
| zero each: `ASSUMED_AVAILABLE_NO_REPORTED_ISSUE`, `AVAILABILITY_UNVERIFIED`, `AVAILABLE_CONFIRMED`, `UNAVAILABLE_INJURY`, `UNAVAILABLE_OTHER`, `UNAVAILABLE_SUSPENSION`, `UNKNOWN` | `product_availability_observations.availability_state` | S1 | 0 | Dormant; no rows | I11 | P1/P2 |
| `FORECAST_AVAILABLE` 220; `NOT_ENOUGH_HISTORY` 1,022; `NO_FIXTURES` 54; `SOURCE_DATA_INCOMPLETE` 361; zero each: `NO_H2H`, `NO_RESULTS`, `NO_STANDINGS`, `PROVIDER_LIMIT`, `RATE_LIMIT`, `SEASON_UNAVAILABLE`, `TEAM_MAPPING_MISSING`, `TEMPORARILY_UNAVAILABLE`, `USAGE_RESTRICTION` | `product_competitions.availability_status` | S1 | 1,657 | Mixed; see lifecycle and root-cause sections | I10/I11 | P0 |
| `PROVISIONAL` 361; `VERIFIED` 1,296 | `product_competitions.metadata_status` | S1 | 1,657 | Mixed; see lifecycle and root-cause sections | I10/I11 | P0 |
| `SUPPORTED` 799; `UNSUPPORTED_BY_COMPETITION` 2,927; zero each: `PLAN_RESTRICTION`, `UNKNOWN` | `product_context_capabilities.status` | S1 | 3,726 | Mixed; see lifecycle and root-cause sections | I11 | P1/P2 |
| `FORECAST_AVAILABLE` 3,668; `NOT_ENOUGH_HISTORY` 194,161; `SOURCE_DATA_INCOMPLETE` 62,488; zero each: `TEMPORARILY_UNAVAILABLE` | `product_fixtures.forecast_availability` | S2 | 260,317 | Mixed; see lifecycle and root-cause sections | I10/I11 | P0 |
| `PROVISIONAL` 62,290; `VERIFIED` 198,027; zero each: `QUARANTINED` | `product_fixtures.identity_status` | S1 | 260,317 | Mixed; see lifecycle and root-cause sections | I03/I04 | P0 |
| `ABANDONED` 11; `AWARDED` 241; `CANCELLED` 2,236; `FINISHED` 249,299; `LIVE` 51; `POSTPONED` 287; `SCHEDULED` 8,192; zero each: `HALF_TIME`, `INTERRUPTED`, `SUSPENDED` | `product_fixtures.status` | S1 | 260,317 | Mixed; see lifecycle and root-cause sections | I14 | P1/P2 |
| `MVP_OWNER_AUTHORIZED` 14,054 | `product_forecasts.publication_mode` | S2 | 14,054 | Healthy claims; qualification is scope-dependent | I16/I17 | P1/P2 |
| `EMPTY` 20; `STORED` 247; `UNAVAILABLE` 295 | `product_history_sync_attempts.last_status` | S1 | 562 | Mixed; see lifecycle and root-cause sections | I05/I06 | P1/P2 |
| `PENDING` 506; `SUCCEEDED` 135; zero each: `FAILED`, `RUNNING` | `product_history_sync_queue.job_status` | S1 | 641 | Mixed; see lifecycle and root-cause sections | I05/I06 | P1/P2 |
| `CONTRADICTORY` 433; `CROSSWALK` 2,398; `ORIGIN_ANCHOR` 14,472; `REVOKED` 1,404; `UNRESOLVED` 3,808 | `product_identity_admissions.disposition` | S2 | 22,515 | Mixed; see lifecycle and root-cause sections | I03 | P0 |
| zero each: `ASSUMED_AVAILABLE_NO_REPORTED_ISSUE`, `AVAILABILITY_UNVERIFIED`, `AVAILABLE_CONFIRMED`, `UNAVAILABLE_INJURY`, `UNAVAILABLE_OTHER`, `UNAVAILABLE_SUSPENSION`, `UNKNOWN` | `product_lineup_players.availability_state` | S1 | 0 | Dormant; no rows | I11 | P1/P2 |
| zero each: `RESOLVED`, `UNRESOLVED` | `product_lineup_players.slot_status` | S1 | 0 | Dormant; no rows | I11 | P1/P2 |
| zero each: `INSUFFICIENT_DATA`, `INVALID_DISTRIBUTION`, `MODEL_ERROR`, `MODEL_FIT_UNAVAILABLE`, `SUCCESS`, `UNSEEN_TEAM` | `product_model_forecasts.status` | S1 | 0 | Dormant; no rows | I10/I11 | P0 |
| `AWARDED` 258; `CANCELLED` 2,450; `FINISHED` 115,816; `HALF_TIME` 262; `LIVE` 87,570; `POSTPONED` 110; `SCHEDULED` 16,835; zero each: `ABANDONED`, `INTERRUPTED`, `SUSPENDED` | `product_provider_fixture_observations.canonical_status` | S1 | 223,301 | Mixed; see lifecycle and root-cause sections | I14 | P1/P2 |
| 223,301 rows; 199 labels including NULL where present (detail below) | `product_provider_fixture_observations.provider_status` | S1 | 223,301 | Native source labels; historical snapshots | I16/I17 | P1/P2 |
| `DEFERRED` 11; `FAILED` 338; `PENDING` 873; `SUCCEEDED` 2; zero each: `RUNNING` | `product_provider_history_scopes.status` | S1 | 1,224 | Mixed; see lifecycle and root-cause sections | I05/I06 | P1/P2 |
| `AUTO_ACCEPTED` 224,884; `CONTRADICTORY` 30,048; `MANUAL_ACCEPTED` 2,845; `REVIEW_REQUIRED` 2,216,367 | `product_provider_mapping_decisions.disposition` | S2 | 2,474,144 | Mixed; see lifecycle and root-cause sections | I03/I04 | P0 |
| `AVAILABLE` 254,896 | `product_provider_resource_observations.availability_status` | S1 | 254,896 | Healthy claims; qualification is scope-dependent | I16/I17 | P1/P2 |
| `ELIGIBLE` 254,896 | `product_provider_resource_observations.point_in_time_eligibility` | S2 | 254,896 | Healthy claims; qualification is scope-dependent | I16/I17 | P1/P2 |
| `CANCELLED` 209; `FAILED` 6,200; `RUNNING` 1; `SUCCEEDED` 6,618; zero each: `QUEUED` | `product_sync_runs.status` | S1 | 13,028 | Mixed; see lifecycle and root-cause sections | I07/I08 | P1/P2 |
| 0 rows; explicit nonblank qualification text | `provider_resource_authority.qualification_state` | S1 | 0 | Dormant; no rows | I10/I11 | P0 |
| `PARTIAL` 24; `UNKNOWN` 2; zero each: `AUTHORIZATION_REQUIRED`, `PLAN_RESTRICTED`, `SUPPORTED`, `TEMPORARILY_UNAVAILABLE`, `UNSUPPORTED` | `provider_resource_capabilities.availability` | S5 | 26 | Mixed; see lifecycle and root-cause sections | I10/I11 | P0 |
| `ANONYMOUS_HOME_AWAY_SOURCE_SIDES; NO_TEAM_ADMISSION` 1; `UNASSESSED` 16; `UNASSESSED; SEPARATE_PROVIDER_NAMESPACE` 6; `UNRESOLVED_SOURCE_REFERENCES; NO_CANONICAL_ADMISSION` 3 | `provider_resource_capabilities.identity_quality` | S2 | 26 | Mixed; see lifecycle and root-cause sections | I10/I11 | P0 |
| `REGISTERED_CHECKSUM_VERIFIED_SAMPLE` 26 | `provider_resource_capabilities.retention_status` | S1 | 26 | Mixed; see lifecycle and root-cause sections | I10/I11 | P0 |
| zero each: `COMPLETE`, `PARTIAL`, `UNKNOWN` | `provider_resource_coverage.status` | S1 | 0 | Dormant; no rows | I10/I11 | P0 |
| `succeeded` 1; zero each: `failed`, `partial`, `queued`, `running`, `stopped` | `provider_sync_runs.status` | S1 | 1 | Mixed; see lifecycle and root-cause sections | I07/I08 | P1/P2 |
| `open` 1; zero each: `reprocessed`, `resolved` | `quarantine_records.status` | S1 | 1 | Mixed; see lifecycle and root-cause sections | I12 | P1/P2 |
| zero each: `resolved`, `still_quarantined` | `quarantine_resolution_outcomes.outcome` | S1 | 0 | Dormant; no rows | I12 | P1/P2 |
| `QUARANTINED` 1; zero each: `RESOLVED`, `REVIEW_REQUIRED` | `reconciliation_conflicts.disposition` | S2 | 1 | Mixed; see lifecycle and root-cause sections | I12 | P1/P2 |
| `AUTO_ACCEPTED` 10; `MANUALLY_APPROVED` 20; zero each: `MANUALLY_REJECTED`, `REVIEW_REQUIRED`, `SUPERSEDED` | `resolution_decisions.status` | S1 | 30 | Healthy claims; qualification is scope-dependent | I16/I17 | P1/P2 |
| zero each: `CHALLENGER`, `CHAMPION`, `RESEARCH`, `RETIRED` | `runtime_model_registrations.lifecycle_state` | S1 | 0 | Dormant; no rows | I10/I11 | P0 |
| `not_applicable` 1; `parsed` 66,922; `pending` 2; zero each: `failed` | `source_resources.parse_status` | S1 | 66,925 | Mixed; see lifecycle and root-cause sections | I01/I02 | P1/P2 |
| `pending` 2; `valid` 66,903; `warnings` 20; zero each: `failed`, `quarantined` | `source_resources.validation_status` | S1 | 66,925 | Mixed; see lifecycle and root-cause sections | I01/I02 | P1/P2 |
| `acquired` 34; `validated` 65,083; zero each: `acquiring`, `discovered`, `quarantined`, `superseded` | `source_snapshots.status` | S1 | 65,117 | Healthy claims; qualification is scope-dependent | I01/I02 | P1/P2 |
| `FAIL` 19; `PASS` 4; zero each: `PASS_WITH_WARNINGS` | `sprint2_evaluation_runs.status` | S1 | 23 | Mixed; see lifecycle and root-cause sections | I16/I17 | P1/P2 |
| `QUARANTINE` 38; `WARNING` 2,146; zero each: `FATAL`, `INFO` | `validation_findings.severity` | S1 | 2,184 | Mixed; see lifecycle and root-cause sections | I12 | P1/P2 |
| `passed` 3; `quarantined` 1; `warnings` 2; zero each: `failed` | `validation_runs.status` | S1 | 6 | Mixed; see lifecycle and root-cause sections | I12 | P1/P2 |
| `CANCELLED` 158; `FAILED` 1,030; `RETRY_WAIT` 518; `RUNNING` 1; `SUCCEEDED` 93,285; zero each: `BLOCKED`, `PENDING` | `work_items.state` | S1 | 94,992 | Mixed; see lifecycle and root-cause sections | I05/I08 | P1/P2 |

`point_in_time_eligibility=ELIGIBLE` is a recorded claim; all 254,896 legacy rich-resource rows are also `development_only=true`. This does not make target-match results eligible as pre-match features. `provider_resource_authority.qualification_state` is an open nonblank string contract, not a closed enum. An empty table does not justify inventing its possible labels.

<details>
<summary>Every observed unconstrained native provider-status label and its count</summary>

| Stage | Native label | Occurrences | Snapshot |
| --- | --- | --- | --- |
| `match_observations.provider_status` | `available` | 1,034 | S1 |
| `match_observations.provider_status` | `completed` | 10 | S1 |
| `product_provider_fixture_observations.provider_status` | `EMPTY_STRING` | 917 | S1 |
| `product_provider_fixture_observations.provider_status` | `100‎’‎` | 80 | S1 |
| `product_provider_fixture_observations.provider_status` | `101‎’‎` | 54 | S1 |
| `product_provider_fixture_observations.provider_status` | `102‎’‎` | 43 | S1 |
| `product_provider_fixture_observations.provider_status` | `103‎’‎` | 36 | S1 |
| `product_provider_fixture_observations.provider_status` | `104‎’‎` | 33 | S1 |
| `product_provider_fixture_observations.provider_status` | `105` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `105‎’‎` | 29 | S1 |
| `product_provider_fixture_observations.provider_status` | `106‎’‎` | 32 | S1 |
| `product_provider_fixture_observations.provider_status` | `107‎’‎` | 30 | S1 |
| `product_provider_fixture_observations.provider_status` | `108‎’‎` | 26 | S1 |
| `product_provider_fixture_observations.provider_status` | `109‎’‎` | 24 | S1 |
| `product_provider_fixture_observations.provider_status` | `10‎’‎` | 938 | S1 |
| `product_provider_fixture_observations.provider_status` | `110‎’‎` | 16 | S1 |
| `product_provider_fixture_observations.provider_status` | `111‎’‎` | 18 | S1 |
| `product_provider_fixture_observations.provider_status` | `112‎’‎` | 18 | S1 |
| `product_provider_fixture_observations.provider_status` | `113‎’‎` | 13 | S1 |
| `product_provider_fixture_observations.provider_status` | `114‎’‎` | 12 | S1 |
| `product_provider_fixture_observations.provider_status` | `115‎’‎` | 16 | S1 |
| `product_provider_fixture_observations.provider_status` | `116‎’‎` | 14 | S1 |
| `product_provider_fixture_observations.provider_status` | `117‎’‎` | 10 | S1 |
| `product_provider_fixture_observations.provider_status` | `118‎’‎` | 15 | S1 |
| `product_provider_fixture_observations.provider_status` | `119‎’‎` | 16 | S1 |
| `product_provider_fixture_observations.provider_status` | `11‎’‎` | 928 | S1 |
| `product_provider_fixture_observations.provider_status` | `120‎’‎` | 17 | S1 |
| `product_provider_fixture_observations.provider_status` | `121‎’‎` | 14 | S1 |
| `product_provider_fixture_observations.provider_status` | `122‎’‎` | 12 | S1 |
| `product_provider_fixture_observations.provider_status` | `123‎’‎` | 5 | S1 |
| `product_provider_fixture_observations.provider_status` | `124‎’‎` | 6 | S1 |
| `product_provider_fixture_observations.provider_status` | `125‎’‎` | 3 | S1 |
| `product_provider_fixture_observations.provider_status` | `126‎’‎` | 3 | S1 |
| `product_provider_fixture_observations.provider_status` | `128‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `129‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `12‎’‎` | 874 | S1 |
| `product_provider_fixture_observations.provider_status` | `132‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `134‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `136‎’‎` | 2 | S1 |
| `product_provider_fixture_observations.provider_status` | `138‎’‎` | 2 | S1 |
| `product_provider_fixture_observations.provider_status` | `13‎’‎` | 959 | S1 |
| `product_provider_fixture_observations.provider_status` | `140‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `141‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `144‎’‎` | 2 | S1 |
| `product_provider_fixture_observations.provider_status` | `145‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `146‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `147‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `148‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `14‎’‎` | 932 | S1 |
| `product_provider_fixture_observations.provider_status` | `150‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `152‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `153‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `155‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `156‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `157‎’‎` | 2 | S1 |
| `product_provider_fixture_observations.provider_status` | `158‎’‎` | 2 | S1 |
| `product_provider_fixture_observations.provider_status` | `159‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `15‎’‎` | 881 | S1 |
| `product_provider_fixture_observations.provider_status` | `160‎’‎` | 2 | S1 |
| `product_provider_fixture_observations.provider_status` | `161‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `162‎’‎` | 2 | S1 |
| `product_provider_fixture_observations.provider_status` | `163‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `164‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `165‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `166‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `168‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `169‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `16‎’‎` | 1,051 | S1 |
| `product_provider_fixture_observations.provider_status` | `171‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `172‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `173‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `174‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `17‎’‎` | 965 | S1 |
| `product_provider_fixture_observations.provider_status` | `180‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `182‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `18‎’‎` | 877 | S1 |
| `product_provider_fixture_observations.provider_status` | `19‎’‎` | 925 | S1 |
| `product_provider_fixture_observations.provider_status` | `1‎’‎` | 698 | S1 |
| `product_provider_fixture_observations.provider_status` | `20‎’‎` | 895 | S1 |
| `product_provider_fixture_observations.provider_status` | `21‎’‎` | 867 | S1 |
| `product_provider_fixture_observations.provider_status` | `223‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `225‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `228‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `22‎’‎` | 918 | S1 |
| `product_provider_fixture_observations.provider_status` | `230‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `231‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `233‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `235‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `237‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `238‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `23‎’‎` | 876 | S1 |
| `product_provider_fixture_observations.provider_status` | `240‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `241‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `243‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `244‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `246‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `247‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `249‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `24‎’‎` | 826 | S1 |
| `product_provider_fixture_observations.provider_status` | `25‎’‎` | 820 | S1 |
| `product_provider_fixture_observations.provider_status` | `26‎’‎` | 851 | S1 |
| `product_provider_fixture_observations.provider_status` | `27‎’‎` | 845 | S1 |
| `product_provider_fixture_observations.provider_status` | `28‎’‎` | 821 | S1 |
| `product_provider_fixture_observations.provider_status` | `29‎’‎` | 815 | S1 |
| `product_provider_fixture_observations.provider_status` | `2‎’‎` | 896 | S1 |
| `product_provider_fixture_observations.provider_status` | `30‎’‎` | 865 | S1 |
| `product_provider_fixture_observations.provider_status` | `31‎’‎` | 786 | S1 |
| `product_provider_fixture_observations.provider_status` | `32‎’‎` | 929 | S1 |
| `product_provider_fixture_observations.provider_status` | `33‎’‎` | 883 | S1 |
| `product_provider_fixture_observations.provider_status` | `34‎’‎` | 892 | S1 |
| `product_provider_fixture_observations.provider_status` | `35‎’‎` | 951 | S1 |
| `product_provider_fixture_observations.provider_status` | `36‎’‎` | 910 | S1 |
| `product_provider_fixture_observations.provider_status` | `37‎’‎` | 900 | S1 |
| `product_provider_fixture_observations.provider_status` | `38‎’‎` | 891 | S1 |
| `product_provider_fixture_observations.provider_status` | `39‎’‎` | 873 | S1 |
| `product_provider_fixture_observations.provider_status` | `3‎’‎` | 834 | S1 |
| `product_provider_fixture_observations.provider_status` | `40‎’‎` | 885 | S1 |
| `product_provider_fixture_observations.provider_status` | `41‎’‎` | 904 | S1 |
| `product_provider_fixture_observations.provider_status` | `42‎’‎` | 846 | S1 |
| `product_provider_fixture_observations.provider_status` | `43‎’‎` | 838 | S1 |
| `product_provider_fixture_observations.provider_status` | `44‎’‎` | 822 | S1 |
| `product_provider_fixture_observations.provider_status` | `45` | 10 | S1 |
| `product_provider_fixture_observations.provider_status` | `45‎’‎` | 821 | S1 |
| `product_provider_fixture_observations.provider_status` | `46‎’‎` | 1,163 | S1 |
| `product_provider_fixture_observations.provider_status` | `474‎’‎` | 1 | S1 |
| `product_provider_fixture_observations.provider_status` | `47‎’‎` | 1,131 | S1 |
| `product_provider_fixture_observations.provider_status` | `48‎’‎` | 1,044 | S1 |
| `product_provider_fixture_observations.provider_status` | `49‎’‎` | 983 | S1 |
| `product_provider_fixture_observations.provider_status` | `4‎’‎` | 920 | S1 |
| `product_provider_fixture_observations.provider_status` | `50‎’‎` | 941 | S1 |
| `product_provider_fixture_observations.provider_status` | `51‎’‎` | 909 | S1 |
| `product_provider_fixture_observations.provider_status` | `52‎’‎` | 919 | S1 |
| `product_provider_fixture_observations.provider_status` | `53‎’‎` | 840 | S1 |
| `product_provider_fixture_observations.provider_status` | `54‎’‎` | 820 | S1 |
| `product_provider_fixture_observations.provider_status` | `55‎’‎` | 920 | S1 |
| `product_provider_fixture_observations.provider_status` | `56‎’‎` | 844 | S1 |
| `product_provider_fixture_observations.provider_status` | `57‎’‎` | 917 | S1 |
| `product_provider_fixture_observations.provider_status` | `58‎’‎` | 908 | S1 |
| `product_provider_fixture_observations.provider_status` | `59‎’‎` | 939 | S1 |
| `product_provider_fixture_observations.provider_status` | `5‎’‎` | 935 | S1 |
| `product_provider_fixture_observations.provider_status` | `60‎’‎` | 968 | S1 |
| `product_provider_fixture_observations.provider_status` | `61‎’‎` | 912 | S1 |
| `product_provider_fixture_observations.provider_status` | `62‎’‎` | 936 | S1 |
| `product_provider_fixture_observations.provider_status` | `63‎’‎` | 959 | S1 |
| `product_provider_fixture_observations.provider_status` | `64‎’‎` | 901 | S1 |
| `product_provider_fixture_observations.provider_status` | `65‎’‎` | 879 | S1 |
| `product_provider_fixture_observations.provider_status` | `66‎’‎` | 908 | S1 |
| `product_provider_fixture_observations.provider_status` | `67‎’‎` | 885 | S1 |
| `product_provider_fixture_observations.provider_status` | `68‎’‎` | 875 | S1 |
| `product_provider_fixture_observations.provider_status` | `69‎’‎` | 875 | S1 |
| `product_provider_fixture_observations.provider_status` | `6‎’‎` | 855 | S1 |
| `product_provider_fixture_observations.provider_status` | `70‎’‎` | 851 | S1 |
| `product_provider_fixture_observations.provider_status` | `71‎’‎` | 847 | S1 |
| `product_provider_fixture_observations.provider_status` | `72‎’‎` | 826 | S1 |
| `product_provider_fixture_observations.provider_status` | `73‎’‎` | 815 | S1 |
| `product_provider_fixture_observations.provider_status` | `74‎’‎` | 842 | S1 |
| `product_provider_fixture_observations.provider_status` | `75‎’‎` | 836 | S1 |
| `product_provider_fixture_observations.provider_status` | `76‎’‎` | 858 | S1 |
| `product_provider_fixture_observations.provider_status` | `77‎’‎` | 874 | S1 |
| `product_provider_fixture_observations.provider_status` | `78‎’‎` | 856 | S1 |
| `product_provider_fixture_observations.provider_status` | `79‎’‎` | 878 | S1 |
| `product_provider_fixture_observations.provider_status` | `7‎’‎` | 919 | S1 |
| `product_provider_fixture_observations.provider_status` | `80‎’‎` | 894 | S1 |
| `product_provider_fixture_observations.provider_status` | `81‎’‎` | 853 | S1 |
| `product_provider_fixture_observations.provider_status` | `82‎’‎` | 924 | S1 |
| `product_provider_fixture_observations.provider_status` | `83‎’‎` | 901 | S1 |
| `product_provider_fixture_observations.provider_status` | `84‎’‎` | 854 | S1 |
| `product_provider_fixture_observations.provider_status` | `85‎’‎` | 883 | S1 |
| `product_provider_fixture_observations.provider_status` | `86‎’‎` | 917 | S1 |
| `product_provider_fixture_observations.provider_status` | `87‎’‎` | 799 | S1 |
| `product_provider_fixture_observations.provider_status` | `88‎’‎` | 919 | S1 |
| `product_provider_fixture_observations.provider_status` | `89‎’‎` | 884 | S1 |
| `product_provider_fixture_observations.provider_status` | `8‎’‎` | 870 | S1 |
| `product_provider_fixture_observations.provider_status` | `90` | 15 | S1 |
| `product_provider_fixture_observations.provider_status` | `90‎’‎` | 925 | S1 |
| `product_provider_fixture_observations.provider_status` | `91‎’‎` | 894 | S1 |
| `product_provider_fixture_observations.provider_status` | `92‎’‎` | 909 | S1 |
| `product_provider_fixture_observations.provider_status` | `93‎’‎` | 835 | S1 |
| `product_provider_fixture_observations.provider_status` | `94‎’‎` | 772 | S1 |
| `product_provider_fixture_observations.provider_status` | `95‎’‎` | 632 | S1 |
| `product_provider_fixture_observations.provider_status` | `96‎’‎` | 392 | S1 |
| `product_provider_fixture_observations.provider_status` | `97‎’‎` | 308 | S1 |
| `product_provider_fixture_observations.provider_status` | `98‎’‎` | 186 | S1 |
| `product_provider_fixture_observations.provider_status` | `99‎’‎` | 126 | S1 |
| `product_provider_fixture_observations.provider_status` | `9‎’‎` | 870 | S1 |
| `product_provider_fixture_observations.provider_status` | `AET` | 133 | S1 |
| `product_provider_fixture_observations.provider_status` | `AW` | 258 | S1 |
| `product_provider_fixture_observations.provider_status` | `Ab` | 48 | S1 |
| `product_provider_fixture_observations.provider_status` | `Can` | 2,106 | S1 |
| `product_provider_fixture_observations.provider_status` | `ET` | 9 | S1 |
| `product_provider_fixture_observations.provider_status` | `FT` | 111,559 | S1 |
| `product_provider_fixture_observations.provider_status` | `HT` | 1,704 | S1 |
| `product_provider_fixture_observations.provider_status` | `IR` | 15 | S1 |
| `product_provider_fixture_observations.provider_status` | `NULL` | 13,715 | S1 |
| `product_provider_fixture_observations.provider_status` | `PET` | 10 | S1 |
| `product_provider_fixture_observations.provider_status` | `PP` | 296 | S1 |
| `product_provider_fixture_observations.provider_status` | `Pen` | 310 | S1 |
| `product_provider_fixture_observations.provider_status` | `finished` | 3,827 | S1 |
| `product_provider_fixture_observations.provider_status` | `not_started` | 2,203 | S1 |
| `product_provider_fixture_observations.provider_status` | `postponed` | 110 | S1 |
| `product_provider_fixture_observations.provider_status` | `started` | 77 | S1 |

</details>

### Lifecycle meanings and valid exits

These apply to the exact owner named in the inventory. Shared spellings do not imply shared transition permissions.

| Owner and statuses | Meaning / classification | Entry and valid exit |
| --- | --- | --- |
| Acquisition: discovered/acquiring/acquired/validated/quarantined/failed/superseded | Discovered and acquiring are transitional; acquired means bytes retained; validated means that owner's validation passed; quarantine/failure require investigation; superseded preserves a predecessor | Discovery → permitted acquisition → retained hash/size → parser/validation proof. Failed/quarantined data exits only through the existing verified recovery/correction contract. |
| Resource parsing/validation: pending, parsed, valid, warnings, failed, quarantined, not_applicable | Pending is unassessed; parsed/valid are scoped successful claims; warnings preserve accepted limitations; failures/quarantine exclude affected uses; not_applicable is a deliberate contract result | Actual parser/validator publication and recorded policy result, not elapsed age. Frozen lifecycle rows may remain historical while later versions are processed. |
| Shared work: PENDING/RUNNING/RETRY_WAIT/SUCCEEDED/FAILED/CANCELLED/BLOCKED | Scheduling, owned execution, deferred retry, verified completed operation, terminal failure, revoked execution, and explicit dependency blocker | Claim requires availability, dependency and lease proof. Normal publication finishes a claimed generation; retry/cooldown/classification governs waits. Cancellation/supersession never restores publication rights. |
| Legacy scopes/jobs: PENDING/RUNNING/SUCCEEDED/FAILED/DEFERRED; attempts STORED/EMPTY/UNAVAILABLE | Transitional queue/scope state, validated storage, partial/failed scope, policy deferment, or actual empty/unavailable provider observation | Existing domain/shared-work adapters project the same execution. Empty is legitimate only for a valid expected scope; malformed/missing list is not empty success. |
| Identity: ORIGIN_ANCHOR/CROSSWALK/VERIFIED/AUTO_ACCEPTED/MANUAL_ACCEPTED/MANUALLY_APPROVED | Healthy accepted relation within its exact proof, provider, valid and knowledge scope | Existing automatic proof or authenticated current review; changed evidence can require prospective correction/revalidation. These are not fuzzy-match confidence labels. |
| Identity: UNRESOLVED/REVIEW_REQUIRED/NEEDS_REVIEW/CONTRADICTORY/REVOKED/BLOCKED/MANUALLY_REJECTED/SUPERSEDED | Missing proof, pending qualified review, conflicting proof, withdrawn trust, dependency block, rejected or replaced decision | Exact valid evidence and the existing decision workflow. Rejected/superseded history stays recorded; unsupported proposals never become valid solely by owner preference. |
| Fixture identity: UNIQUE/DUPLICATE_RESOLVED/AMBIGUOUS_QUARANTINED/IMPOSSIBLE_TEAM_SCHEDULE_QUARANTINED | One qualified fixture, proved duplicate membership, ambiguous equivalence, or incompatible team/time scheduling | Exact accepted member/season/orientation/time evidence and active resolution selection; preserve original IDs and quarantine until conflict is proved resolved. |
| Match lifecycle: SCHEDULED/LIVE/HALF_TIME/FINISHED/POSTPONED/CANCELLED/ABANDONED/INTERRUPTED/SUSPENDED/AWARDED/UNKNOWN | Football lifecycle facts, not operation failures. Non-played/censored cases may legitimately remain outside played-history labels | Native-specific status and score-period interpretation followed by existing allowed transitions and newer authentic source evidence. No wall-clock-only finalization. |
| Coverage: UNKNOWN/PARTIAL/COMPLETE; capability SUPPORTED/UNSUPPORTED/PARTIAL/UNKNOWN/PLAN_RESTRICTED/AUTHORIZATION_REQUIRED/TEMPORARILY_UNAVAILABLE | Unknown denominator, incomplete qualified units, complete declared units, or provider ability/entitlement state | New verified owner evidence changes coverage/capability; complete sampled coverage does not qualify other seasons, fields or markets. Unsupported/plan-restricted can be correct final states. |
| Market: DATA_COLLECTION_REQUIRED/INSUFFICIENT_HISTORY/INSUFFICIENT_PLAYER_DATA/SEMANTIC_MISMATCH/RESEARCH_REQUIRED/ENGINEERING_READY/SHADOW/SUPPORTED/BLOCKED | Missing target input/history/player evidence, incompatible semantics, unqualified model/evaluation, engineering ready but unapproved publication, approved shadow/live scope, or external/policy blocker | Recompute from exact coverage, target parameters, semantics, history/model/evaluation/publication evidence. There is no direct healthy-state override. |
| Forecast availability: FORECAST_AVAILABLE/NOT_ENOUGH_HISTORY/SOURCE_DATA_INCOMPLETE/TEMPORARILY_UNAVAILABLE/NO_FIXTURES | Eligible existing forecast, insufficient approved history, incomplete source/identity, temporary failure, or legitimate absent fixture set | Existing forecast/source owners publish or recompute after their real prerequisites pass; no fixture/model expansion to clear a status. |
| Model result/lifecycle: SUCCESS/INSUFFICIENT_DATA/UNSEEN_TEAM/MODEL_FIT_UNAVAILABLE/MODEL_ERROR/INVALID_DISTRIBUTION; RESEARCH/CHALLENGER/CHAMPION/RETIRED | Valid result, explicit inability/error, or governed immutable model role | Existing model/fit and promotion owners only. New data may resolve insufficiency; a data task cannot promote a model, clip invalid probabilities, or reopen failed science. |
| Quality: FATAL/QUARANTINE/WARNING/INFO; open/reprocessed/resolved; OPEN/RETRYABLE/NEEDS_REVIEW/RESOLVED/SUPERSEDED operation labels | Rule outcome severity, persisted case lifecycle and separate operation-level quarantine result | Apply existing rule/action and evidence-backed decision, then reprocess normally. Legitimate warnings and synthetic conflict evidence may remain. |
| External: MATCHED/UNMATCHED/AMBIGUOUS; VERIFIED/MISMATCH/UNKNOWN/NOT_APPLICABLE date; PENDING/WON/LOST | Exact binding, missing/ambiguous identity, source-date evidence and current settlement | Binding/date proof and supported authoritative finished result; original capture and previous revisions remain. An unmatched prediction cannot settle by guessed name/date. |
| Serving: READY/PENDING/FAILED/EMPTY/NO_FORECAST/UNMATCHED/UNSUPPORTED/QUARANTINED | Request-time readiness derived from actual inputs, report hash, errors, target/date and original forecast | Existing decoders/read-model owners derive these; none is a persisted report JSON field to rewrite. |
| Integrity/registration receipts: PASS/MISSING/NOT_FOUND/UNREADABLE/CHECKSUM_MISMATCH/INVALID_REGISTRATION; inserted/verified_existing/published | Observed verification result or idempotent publication receipt; success is scoped to the operation | Exact registered bytes and contract checks, or a genuinely identical prior publication. Historical registration success never substitutes for current verification. |
| Research/gates: PASS/PASS_WITH_WARNINGS/FAIL/NOT_RUN/UNPROVED/UNASSESSED and development acceptance/rejection variants | Scoped assessed result, qualified warning, frozen failure, unexecuted or unproved evidence; not generally retryable ingestion states | Existing approved research/evaluation protocol and phase owner. New evidence/results remain append-only; failed terminal routes are not reopened by cleanup. |
| Other definition-only outcomes below | Producer-specific transient, availability, correction, cold-start, publication or diagnostic result; no measured current incident population | Follow the referenced exact producer/contract. Do not infer a transition or a recovery obligation from its name alone. |

### Computed/current diagnostic populations

| Status | Stage | Provider/dataset | Count | Classification | Root cause | Severity |
| --- | --- | --- | --- | --- | --- | --- |
| VERIFIED / UNRESOLVED / CONTRADICTORY / BLOCKED | Recorded Resolution Center mapping cases | All active team/competition mappings, S2 | 15,749 / 4,942 / 108 / 6 | Current case projection; differs from fresh classifier | I03 | P0 |
| ORIGIN_ANCHOR / CROSSWALK / UNRESOLVED / CONTRADICTORY / REVOKED | Fresh identity classifier | 20,805 active mappings, S4 | 14,193 / 1,556 / 4,947 / 108 / 1 | Recomputed using retained source evidence | I03 | P0 |
| AUTO_ACCEPTED / MANUAL_ACCEPTED / REVIEW_REQUIRED / CONTRADICTORY | Latest native fixture mapping decisions | 94,956 provider+native fixture keys, S2 | 46,586 / 546 / 47,293 / 531 | Latest decisions, not all 2,474,144 historical events | I04 | P0 |
| NEEDS_REVIEW / BLOCKED | Additional fixture-record cases | 44,780 case keys, S2 | 43,035 / 1,745 | May overlap matches referenced by native mapping cases | I04 | P0 |
| DATA_COLLECTION_REQUIRED / INSUFFICIENT_PLAYER_DATA | Operating market-family diagnostic | NPFL scope cb185f33-3900-564d-83e1-578649b04224 / season 19d3ab5e-c4e6-5435-80ad-95a0bb6762be, S5 | 53 / 14 | Correct fail-closed readiness; 67 unbound families | I10/I11 | P1 |
| SUPPORTED / SHADOW / ENGINEERING_READY / RESEARCH_REQUIRED / INSUFFICIENT_HISTORY / SEMANTIC_MISMATCH / BLOCKED | Other defined MarketStatus values | Same operating diagnostic | 0 each | Defined and reachable; no instance in this scope | I10 | P1 |
| RESEARCH_REQUIRED | Previously saved bound RESULT_1X2/HOME experimental diagnostic | R02-M evidence; not a fresh operating-family count | 1 historical bound family/input result | Research-compatible pilot; does not satisfy scientific sufficiency | I10 | P1 |
| PASS / BLOCKED | Raw file verification | S3 all resource IDs | 66,892 / 33 | Exact immutable bytes; blocked includes test-shaped lineage | I01 | P1 |
| PASS / MISSING | Dataset manifests and registered files | 24 versions, S3 | 2 / 22 versions | Physical checks only; 3 missing registered data files in 3 versions | I01 | P1 |
| PASS / MISSING | Full model artifact verification | 5,230 registrations, S3 | 5,204 / 26 | Missing manifests stop full verification for those models | I01 | P1 |
| PASS / MISSING / CHECKSUM_MISMATCH | Direct source-manifest file checks | 65,117 snapshots, S3 | 65,035 / 34 / 48 | Legacy registration meaning must be assessed before corruption claims | I02 | P1 |
| PENDING / WON / LOST | Current external settlement projection | 1,304 predictions, S2 | 1,280 / 19 / 5 | Do not count all 1,477 historical settlement revisions as current cases | I13 | P1 |
| PENDING | Context refresh generation predicate | S2 generation > completed_generation | 176,903 | Derived state; not a stored status column or one shared work ID per entry | I09 | P1 |
| READY / PENDING / FAILED / EMPTY | Go performance report decoder | performance_store.go:158; latest API population not invoked | N/A for request-time results | Computed from payload/digest/count/failure; persisted report JSON has no status key | I09/I16 | P2 |
| READY / PENDING / FAILED / UNMATCHED / NO_FORECAST / UNSUPPORTED / QUARANTINED | Go prediction comparison decoder | read_reports.go:26; external_prediction_store.go:123 | N/A for request-time results | Computed from binding, matching forecast, report and date validation | I13/I16 | P2 |
| FRESH / STALE / NEVER_SUCCEEDED; CLOSED / OPEN / HALF_OPEN | Provider observability contract | observability.py and observability_store.py | N/A; full deployed snapshots unavailable | CLOSED is hardcoded by this store; not a measured circuit state | I16 | P2 |

### Definition-only statuses and outcomes

The following 204 values were found in current Python producers/types, current Go producers/comparisons, checked-in schema enums, or SQL migration checks, but not in the persisted status dimensions above. This includes transient operation receipts, research outcomes, and HTTP health diagnostics. **Count N/A** unless the owning queried table above explicitly reports zero. They are definitions, not evidence of 204 additional incidents. First source shown for traceability; the local definition inventory retains every discovered source location. Case is significant.

| Status / operation outcome | Count | Definition or producer |
| --- | --- | --- |
| `ABD` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/api_football.py:339 (short_status)` |
| `ADVERTISED_BUT_UNUSABLE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/operational_provider_sync.py:650 (status)` |
| `AFFECTED_BY_SOURCE_CORRECTION` | N/A; no persisted occurrence in audited dimensions | `derived_state_events.state` |
| `APPLIED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_actions.py:254 (status)` |
| `ASSESSED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/validation/quality.py:126 (disposition)` |
| `ASSUMED_AVAILABLE_NO_REPORTED_ISSUE` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610070200_live_context_revisions.sql:110 (availability_state)` |
| `AUTHENTICATION_FAILURE` | N/A; no persisted occurrence in audited dimensions | `external_probability_benchmarks.collection_status` |
| `AUTHORIZATION_REQUIRED` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610180300_provider_resource_capabilities.sql:12 (availability)` |
| `AUTH_REQUIRED` | N/A; no persisted occurrence in audited dimensions | `external_prediction_sources.automated_access_status` |
| `AVAILABILITY_UNVERIFIED` | N/A; no persisted occurrence in audited dimensions | `go/api/internal/app/postgres_store.go:586 (Go status producer/comparison)` |
| `AVAILABLE_CONFIRMED` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610070200_live_context_revisions.sql:110 (availability_state)` |
| `BLOCKED` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610180700_work_orchestration.sql:12 (state)` |
| `BLOCKED_EXTERNAL` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/work/contracts.py:43 (RetryClassification)` |
| `BLOCKED_HISTORY_ADMISSION` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/operational_provider_sync.py:729 (status)` |
| `BLOCKED_IDENTITY` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/operational_provider_sync.py:658 (status)` |
| `BLOCKED_RESULT_CONFLICT` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/operational_provider_sync.py:727 (status)` |
| `BLOCKED_SCORE_BASIS` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/operational_provider_sync.py:725 (status)` |
| `BT` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/api_football.py:331 (short_status)` |
| `BUSY` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_recovery.py:507 (status)` |
| `CANC` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/api_football.py:337 (short_status)` |
| `CHALLENGER` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610190300_runtime_model_registry.sql:9 (lifecycle_state)` |
| `CHALLENGER_SUPPORTED` | N/A; no persisted occurrence in audited dimensions | `schemas/contracts/pitchapi-v5-evaluation-evidence-v1.schema.json:1 (/properties/result_classification)` |
| `CHAMPION` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610190300_runtime_model_registry.sql:9 (lifecycle_state)` |
| `CHAMPION_ELIGIBLE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/replacement_holdout.py:22 (ChampionEligibility)` |
| `CHAMPION_INELIGIBLE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/replacement_holdout.py:22 (ChampionEligibility)` |
| `CHECKSUM_MISMATCH` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/integrity.py:24 (IntegrityItemStatus)` |
| `CLOSED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/providers/observability.py:11 (CircuitStateV1)` |
| `COMPLETE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/coverage/resources.py:38 (status)` |
| `COMPLETED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/operational_provider_sync.py:716 (status)` |
| `COMPLETED_WITH_ERRORS` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/multimodel_cli.py:141 (status)` |
| `COMPUTED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/products.py:272 (status)` |
| `CORROBORATED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/ingestion/conflicts.py:15 (FieldReconciliationStatusV1)` |
| `DATA_COLLECTION_REQUIRED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/market_capabilities.py:21 (MarketStatus)` |
| `DEFER_INSUFFICIENT_ELIGIBLE_TARGETS` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/h2h_incremental_signal.py:675 (final_disposition)` |
| `DEVELOPMENT_ACCEPTED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/contextual_goal.py:33 (FamilyDisposition)` |
| `DEVELOPMENT_ADMITTED_FOR_CONFIRMATION` | N/A; no persisted occurrence in audited dimensions | `schemas/contracts/transferable-rolling-npxg-dixon-coles-v2-development-evidence-v1.schema.json:1 (/properties/result_classification)` |
| `DEVELOPMENT_ADMITTED_FOR_FUTURE_CONFIRMATION` | N/A; no persisted occurrence in audited dimensions | `schemas/contracts/pitchapi-calibration-successor-development-evidence-v1.schema.json:1 (/properties/result_classification)` |
| `DEVELOPMENT_REJECTED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/contextual_goal.py:33 (FamilyDisposition)` |
| `DISABLED_NOT_CONFIGURED` | N/A; no persisted occurrence in audited dimensions | `external_probability_benchmarks.collection_status` |
| `DOMAIN_HISTORY_REQUALIFIED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_actions.py:225 (downstream_status)` |
| `ENGINEERING_READY` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/market_capabilities.py:21 (MarketStatus)` |
| `ERROR` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/validation/pitchapi.py:17 (FindingSeverity)` |
| `EXACT_OR_VERIFIED_EQUIVALENT` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/market_capabilities.py:33 (SourceCompatibility)` |
| `EXISTING_FORECAST_AND_PUBLIC_REPORT_QUEUES_OWN_REFRESH` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_recovery.py:456 (downstream_status)` |
| `EXPERIMENTAL_ONLY` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/identity/reep.py:142 (data_classification)` |
| `FAIL_CLOSED_OWNER_REVIEW_REQUIRED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/pitchapi_v3_executor.py:212 (status)` |
| `FAIL_CLOSED_PROTOCOL_VIOLATION` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/contextual_goal.py:33 (FamilyDisposition)` |
| `FATAL` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202608291530_data_validation.sql:39 (severity)` |
| `FILE_VERIFIED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_files.py:132 (status)` |
| `FITTED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/cold_start.py:18 (ArtifactTeamState)` |
| `FIXTURE_NOT_PREDICTABLE` | N/A; no persisted occurrence in audited dimensions | `external_probability_benchmarks.collection_status` |
| `FRESH` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/providers/observability.py:10 (FreshnessStatusV1)` |
| `FULL_HISTORY` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/cold_start.py:23 (HistoryTeamState)` |
| `HALF_OPEN` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/providers/observability.py:11 (CircuitStateV1)` |
| `IDENTIFIER_MIGRATION` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/validation/pitchapi_contingency.py:16 (PitchApiCorrectionClassification)` |
| `IDLE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_recovery.py:495 (status)` |
| `IMPORTED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/cli.py:1048 (status)` |
| `INCOMPATIBLE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/market_capabilities.py:33 (SourceCompatibility)` |
| `INCONCLUSIVE` | N/A; no persisted occurrence in audited dimensions | `schemas/contracts/pitchapi-calibration-successor-development-evidence-v1.schema.json:1 (/properties/result_classification)` |
| `INELIGIBLE_POST_MATCH` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610090300_operational_provider_sync.sql:84 (point_in_time_eligibility)` |
| `INFO` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202608291530_data_validation.sql:39 (severity)` |
| `INITIAL` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/validation/pitchapi_contingency.py:16 (PitchApiCorrectionClassification)` |
| `INSUFFICIENT_CONTEXT` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/context/historical_corpus.py:37 (PointInTimeReconstructionStatus)` |
| `INSUFFICIENT_DATA` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610070100_multi_model_forecasting.sql:33 (status)` |
| `INSUFFICIENT_EVENTS` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/calibration_analysis.py:23 (CalibrationStatus)` |
| `INSUFFICIENT_EVIDENCE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/fixture_crosswalk_review.py:83 (classification)` |
| `INSUFFICIENT_H2H` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/h2h_residual.py:24 (H2HResidualStatus)` |
| `INSUFFICIENT_HISTORY` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/calibration_analysis.py:23 (CalibrationStatus)` |
| `INSUFFICIENT_PLAYER_DATA` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/market_capabilities.py:21 (MarketStatus)` |
| `INSUFFICIENT_QUALIFIED_COVERAGE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/contextual_goal.py:33 (FamilyDisposition)` |
| `INT` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/api_football.py:331 (short_status)` |
| `INTERRUPTED` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610090300_operational_provider_sync.sql:17 (status)` |
| `INVALID_DISTRIBUTION` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610070100_multi_model_forecasting.sql:33 (status)` |
| `INVALID_REGISTRATION` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/integrity.py:24 (IntegrityItemStatus)` |
| `LEASE_LOST` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_files.py:171 (status)` |
| `MANUALLY_REJECTED` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202609020200_resolution_decisions.sql:15 (status)` |
| `MAPPING_FAILURE` | N/A; no persisted occurrence in audited dimensions | `external_probability_benchmarks.collection_status` |
| `MISMATCH` | N/A; no persisted occurrence in audited dimensions | `external_prediction_date_reviews.date_status` |
| `MISSING` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/integrity.py:24 (IntegrityItemStatus)` |
| `MISSING_PROBABILITIES` | N/A; no persisted occurrence in audited dimensions | `external_probability_benchmarks.collection_status` |
| `MIXED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/validation/pitchapi_contingency.py:16 (PitchApiCorrectionClassification)` |
| `MODEL_ERROR` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610070100_multi_model_forecasting.sql:33 (status)` |
| `MODEL_FIT_UNAVAILABLE` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610070100_multi_model_forecasting.sql:33 (status)` |
| `NEEDS_REVIEW` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/ingestion/quarantine.py:21 (QuarantineStatusV1)` |
| `NEVER_SUCCEEDED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/providers/observability.py:10 (FreshnessStatusV1)` |
| `NON_RETRYABLE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/work/contracts.py:43 (RetryClassification)` |
| `NORMALIZABLE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/market_capabilities.py:33 (SourceCompatibility)` |
| `NOT_APPLIED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_actions.py:77 (downstream_status)` |
| `NOT_FOUND` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/integrity.py:24 (IntegrityItemStatus)` |
| `NOT_IMPLEMENTED` | N/A; no persisted occurrence in audited dimensions | `external_prediction_sources.adapter_status` |
| `NOT_PROMOTED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/cold_start.py:30 (PromotionStatus)` |
| `NOT_PUBLISHED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/market_capabilities.py:139 (publication_status)` |
| `NOT_REQUESTED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_actions.py:217 (downstream_status)` |
| `NOT_RUN` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/contracts/foundation.py:10 (FoundationEvidenceStatusV1)` |
| `NOT_RUN_REQUIRED_PARITY_UNMET` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_migration.py:110 (rehearsal_status)` |
| `NO_CHANGE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/validation/pitchapi_contingency.py:16 (PitchApiCorrectionClassification)` |
| `NO_DATE_PAGE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/cli.py:1006 (status)` |
| `NO_FORECAST` | N/A; no persisted occurrence in audited dimensions | `go/api/internal/app/read_reports.go:30 (Go status producer/comparison)` |
| `NO_H2H` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202609290100_mvp_product.sql:18 (availability_status)` |
| `NO_RESULTS` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202609290100_mvp_product.sql:18 (availability_status)` |
| `NO_STANDINGS` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202609290100_mvp_product.sql:18 (availability_status)` |
| `OPEN` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/ingestion/quarantine.py:21 (QuarantineStatusV1)` |
| `P` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/api_football.py:331 (short_status)` |
| `PAID_ONLY` | N/A; no persisted occurrence in audited dimensions | `external_prediction_sources.automated_access_status` |
| `PARSED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/providers/native/cli.py:40 (status)` |
| `PARSER_BROKEN` | N/A; no persisted occurrence in audited dimensions | `external_prediction_sources.automated_access_status` |
| `PARTIAL_HISTORY` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/cold_start.py:23 (HistoryTeamState)` |
| `PASS_WITH_WARNINGS` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202608292100_sprint2_artifacts.sql:134 (status)` |
| `PEN` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/api_football.py:333 (short_status)` |
| `PLAN_RESTRICTED` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610180300_provider_resource_capabilities.sql:12 (availability)` |
| `PLAN_RESTRICTION` | N/A; no persisted occurrence in audited dimensions | `external_probability_benchmarks.collection_status` |
| `POINT_IN_TIME_VERIFIED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/context/historical_corpus.py:37 (PointInTimeReconstructionStatus)` |
| `PREVIEWED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_batches.py:66 (status)` |
| `PROCESSED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_files.py:169 (status)` |
| `PROMOTED_TEAM` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/cold_start.py:30 (PromotionStatus)` |
| `PROMOTE_CANDIDATE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/pitchapi_v3_executor.py:331 (result_classification)` |
| `PROMOTION_STATUS_UNKNOWN` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/cold_start.py:30 (PromotionStatus)` |
| `PROVIDER_CORRECTION` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/validation/pitchapi_contingency.py:16 (PitchApiCorrectionClassification)` |
| `PROVIDER_LIMIT` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202609290100_mvp_product.sql:18 (availability_status)` |
| `PROVIDER_OUTAGE` | N/A; no persisted occurrence in audited dimensions | `external_probability_benchmarks.collection_status` |
| `PST` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/api_football.py:335 (short_status)` |
| `PUBLISHED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/market_capabilities.py:139 (publication_status)` |
| `QUALIFIED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/identity_correction.py:401 (status)` |
| `QUEUED` | N/A; no persisted occurrence in audited dimensions | `go/api/internal/app/admin_sync.go:572 (Go status producer/comparison)` |
| `RATE_LIMIT` | N/A; no persisted occurrence in audited dimensions | `external_probability_benchmarks.collection_status` |
| `READY` | N/A; no persisted occurrence in audited dimensions | `go/api/internal/app/performance_store.go:185 (Go status producer/comparison)` |
| `REBUILD_REQUIRED` | N/A; no persisted occurrence in audited dimensions | `derived_state_events.state` |
| `RECORDED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_actions.py:217 (status)` |
| `REFERENCE_RETAINED` | N/A; no persisted occurrence in audited dimensions | `schemas/contracts/pitchapi-v5-evaluation-evidence-v1.schema.json:1 (/properties/result_classification)` |
| `REHEARSAL_FAILED_ROLLED_BACK` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_stages.py:184 (status)` |
| `REHEARSAL_PASS_ROLLED_BACK` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_stages.py:173 (status)` |
| `REJECTED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/fresh_corpus.py:18 (IdentityStatus)` |
| `REQUESTED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/datasets/contracts.py:22 (RebuildRequestStatusV1)` |
| `RESEARCH` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610190300_runtime_model_registry.sql:9 (lifecycle_state)` |
| `RESEARCH_COMPATIBLE_ONLY` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/market_capabilities.py:33 (SourceCompatibility)` |
| `RESEARCH_REQUIRED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/market_capabilities.py:21 (MarketStatus)` |
| `RESOLVED` | N/A; no persisted occurrence in audited dimensions | `canonical_resource_resolutions.disposition` |
| `RETIRED` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610190300_runtime_model_registry.sql:9 (lifecycle_state)` |
| `RETROSPECTIVE_CONTEXT_ONLY` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/context/historical_corpus.py:37 (PointInTimeReconstructionStatus)` |
| `RETRYABLE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/ingestion/partial_failure.py:6 (ResourceProcessingStatusV1)` |
| `ROLLBACK_VERIFIED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_stages.py:235 (status)` |
| `SEASON_UNAVAILABLE` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202609290100_mvp_product.sql:18 (availability_status)` |
| `SEMANTIC_MISMATCH` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/market_capabilities.py:21 (MarketStatus)` |
| `SHADOW` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/market_capabilities.py:139 (publication_status)` |
| `SOURCE_UNAVAILABLE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/resolution_retirement.py:90 (status)` |
| `STALE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/providers/observability.py:10 (FreshnessStatusV1)` |
| `SUCCESS` | N/A; no persisted occurrence in audited dimensions | `external_probability_benchmarks.collection_status` |
| `SUPERSEDED` | N/A; no persisted occurrence in audited dimensions | `derived_state_events.state` |
| `SUSP` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/api_football.py:331 (short_status)` |
| `SUSPENDED` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610090300_operational_provider_sync.sql:17 (status)` |
| `TEAM_MAPPING_MISSING` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202609290100_mvp_product.sql:18 (availability_status)` |
| `TEMPORARILY_UNAVAILABLE` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202609290100_mvp_product.sql:18 (availability_status)` |
| `TIMEOUT` | N/A; no persisted occurrence in audited dimensions | `external_probability_benchmarks.collection_status` |
| `TRANSFER_HISTORY` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/cold_start.py:23 (HistoryTeamState)` |
| `TRANSFORMABLE_WITH_EVIDENCE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/market_capabilities.py:33 (SourceCompatibility)` |
| `UNAVAILABLE_INJURY` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610070200_live_context_revisions.sql:110 (availability_state)` |
| `UNAVAILABLE_OTHER` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610070200_live_context_revisions.sql:110 (availability_state)` |
| `UNAVAILABLE_SUSPENSION` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610070200_live_context_revisions.sql:110 (availability_state)` |
| `UNPROVED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/validation/pitchapi.py:15 (SeriesStatus)` |
| `UNRATED` | N/A; no persisted occurrence in audited dimensions | `go/api/internal/app/performance_store.go:173 (Go status producer/comparison)` |
| `UNREADABLE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/integrity.py:24 (IntegrityItemStatus)` |
| `UNSCORABLE` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/postmatch.py:44 (status)` |
| `UNSEEN_TEAM` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202610070100_multi_model_forecasting.sql:33 (status)` |
| `UNSUPPORTED` | N/A; no persisted occurrence in audited dimensions | `go/api/internal/app/read_reports.go:50 (Go status producer/comparison)` |
| `UNSUPPORTED_ANTI_BOT` | N/A; no persisted occurrence in audited dimensions | `external_prediction_sources.automated_access_status` |
| `UNSUPPORTED_CENSORED_SUPPORT` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/products.py:265 (status)` |
| `UNSUPPORTED_ROBOTS` | N/A; no persisted occurrence in audited dimensions | `external_prediction_sources.automated_access_status` |
| `UNSUPPORTED_TERMS` | N/A; no persisted occurrence in audited dimensions | `external_prediction_sources.automated_access_status` |
| `USAGE_MODE_DISABLED` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/cli.py:896 (status)` |
| `USAGE_RESTRICTION` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202609290100_mvp_product.sql:18 (availability_status)` |
| `VALID` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/contracts/dependencies.py:32 (EffectiveDerivedStateV1)` |
| `VOID` | N/A; no persisted occurrence in audited dimensions | `external_prediction_result_revisions.settlement_state` |
| `ZERO_HISTORY` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/forecasting/cold_start.py:23 (HistoryTeamState)` |
| `accepted` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/providers/schema_contract.py:11 (SchemaCompatibilityStatusV1)` |
| `accepted_with_warnings` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/providers/schema_contract.py:11 (SchemaCompatibilityStatusV1)` |
| `acquiring` | N/A; no persisted occurrence in audited dimensions | `acquisition_jobs.status` |
| `discovered` | N/A; no persisted occurrence in audited dimensions | `acquisition_jobs.status` |
| `failed` | N/A; no persisted occurrence in audited dimensions | `acquisition_jobs.status` |
| `ingestion_error` | N/A; no persisted occurrence in audited dimensions | `schemas/contracts/sprint1-fixture-v1.schema.json:1 (/properties/expected/properties/outcome)` |
| `inserted` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/ingestion/conflict_storage.py:12 (ReconciliationConflictRegistrationStatusV1)` |
| `lease_lost` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/product/public_reports.py:437 (state)` |
| `live` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/providers/pitchapi.py:182 (status)` |
| `not_published` | N/A; no persisted occurrence in audited dimensions | `fixture_processing_attempts.publication_status` |
| `not_real_provider` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/ingestion/dependencies.py:22 (CorrectionPropagationStatusV1)` |
| `ok` | N/A; no persisted occurrence in audited dimensions | `go/api/internal/app/app.go:238 (Go status producer/comparison)` |
| `partial` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202609020100_provider_sync_lifecycle.sql:7 (status)` |
| `propagated` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/ingestion/dependencies.py:22 (CorrectionPropagationStatusV1)` |
| `quarantine` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/providers/football_data_uk_csv.py:128 (status)` |
| `queued` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202609020100_provider_sync_lifecycle.sql:7 (status)` |
| `ready` | N/A; no persisted occurrence in audited dimensions | `go/api/internal/app/app.go:247 (Go status producer/comparison)` |
| `ready_to_publish` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/providers/football_data_uk_f3.py:25 (F3FixtureProcessingStatusV1)` |
| `rejected` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202608292100_sprint2_artifacts.sql:48 (status)` |
| `reprocessed` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202609020100_provider_sync_lifecycle.sql:83 (status)` |
| `resolved` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202609020100_provider_sync_lifecycle.sql:83 (status)` |
| `retired` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202608292100_sprint2_artifacts.sql:48 (status)` |
| `reused` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202608292100_sprint2_artifacts.sql:15 (status)` |
| `running` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202608292100_sprint2_artifacts.sql:15 (status)` |
| `still_quarantined` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202609020700_f3_fixture_persistence.sql:101 (outcome)` |
| `stopped` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202609020100_provider_sync_lifecycle.sql:7 (status)` |
| `superseded` | N/A; no persisted occurrence in audited dimensions | `infrastructure/migrations/202608290200_canonical_storage.sql:50 (status)` |
| `unavailable` | N/A; no persisted occurrence in audited dimensions | `go/api/internal/app/app.go:244 (Go status producer/comparison)` |
| `unknown` | N/A; no persisted occurrence in audited dimensions | `go/api/internal/app/app.go:253 (Go status producer/comparison)` |
| `verified_existing` | N/A; no persisted occurrence in audited dimensions | `canonical_change_sets.status` |
| `verified_published` | N/A; no persisted occurrence in audited dimensions | `python/football/src/football/storage/parquet.py:91 (status)` |

This inventory deliberately excludes HTTP response numbers, SQLSTATE `MFL01`, market selections, score-basis constants, selectors such as `all/upcoming`, checksum values, and timestamp columns containing the word “outcome.” Native clock strings are preserved, not promoted into MatchForge lifecycle states. Free provider text can introduce future values; there is no finite global provider enum.

### Reproducible SQL and full census

Run metadata reads against an explicitly selected database without invoking `make migrate`, sync/refresh targets, or recovery entrypoints. Example session:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '60s';
SELECT current_database(), transaction_timestamp(), pg_current_snapshot()::text,
       current_setting('transaction_read_only'), current_setting('transaction_isolation');
SELECT table_name, table_type FROM information_schema.tables
WHERE table_schema='football' ORDER BY table_name;
SELECT table_name,column_name,data_type,udt_name,is_nullable
FROM information_schema.columns WHERE table_schema='football'
ORDER BY table_name,ordinal_position;
SELECT c.relname,k.conname,pg_get_constraintdef(k.oid)
FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='football' AND k.contype='c' ORDER BY c.relname,k.conname;
-- For each table in the census, quote identifiers and count exactly:
SELECT count(*) FROM football.work_items;
-- For each table.column in the persisted inventory, use this exact grouping shape:
SELECT state::text,count(*) FROM football.work_items
GROUP BY 1 ORDER BY 1 NULLS FIRST;
-- Add provider/competition/season dimensions only when present on that owner.
SELECT provider_code,provider_competition_id,season_label,status,count(*)
FROM football.product_provider_history_scopes GROUP BY 1,2,3,4 ORDER BY 1,2,3,4;
ROLLBACK;
```

The exact expanded statements for all 131 table counts and 65 status dimensions are retained in S1/S2/S5. The source-level collectors in the local evidence directory use quoted identifiers from `information_schema`, never a guessed production query or estimated `pg_class.reltuples`. Current scopes use the existing `MAPPING_CASES` and `FIXTURE_CASES` CTEs in `product/resolution_cases.py`; historical reconstruction must not copy their current-time predicates.

<details>
<summary>All operating table populations in S1</summary>

| Table | Exact stored rows |
| --- | --- |
| `acquired_resources` | 3 |
| `acquisition_jobs` | 3 |
| `artifact_retirement_events` | 17 |
| `baseline_forecasts` | 9,985 |
| `bitemporal_corrections` | 0 |
| `canonical_change_sets` | 1 |
| `canonical_resolution_evidence` | 0 |
| `canonical_resource_coverage` | 0 |
| `canonical_resource_resolutions` | 0 |
| `competition_observations` | 52 |
| `competition_provider_mappings` | 2,022 |
| `competitions` | 1,694 |
| `dataset_files` | 763 |
| `dataset_inputs` | 1,520 |
| `dataset_versions` | 24 |
| `dependency_edges` | 16,763 |
| `derived_state_events` | 0 |
| `elo_model_versions` | 0 |
| `event_catalog` | 2,609,129 |
| `event_observations` | 2,609,128 |
| `event_provider_mappings` | 2,609,129 |
| `external_prediction_bindings` | 0 |
| `external_prediction_captures` | 1,381 |
| `external_prediction_collection_attempts` | 20 |
| `external_prediction_date_reviews` | 1,304 |
| `external_prediction_refresh_work` | 1,304 |
| `external_prediction_result_revisions` | 1,477 |
| `external_prediction_results` | 40 |
| `external_prediction_sources` | 6 |
| `external_predictions` | 1,304 |
| `external_probability_benchmarks` | 0 |
| `fixture_identity_ingestion_conflicts` | 496 |
| `fixture_identity_resolutions` | 353,894 |
| `fixture_processing_attempts` | 0 |
| `fixture_sources` | 0 |
| `forecast_artifacts` | 9,990 |
| `match_corner_labels` | 760 |
| `match_kickoff_claims` | 760 |
| `match_lifecycle_claims` | 760 |
| `match_observations` | 1,044 |
| `match_player_participation_observations` | 27,354 |
| `match_player_participations` | 27,354 |
| `match_provider_mappings` | 518,721 |
| `match_team_participation_observations` | 2,069 |
| `match_team_participations` | 2,070 |
| `matches` | 774,997 |
| `model_artifact_files` | 5,230 |
| `model_artifact_inputs` | 5,230 |
| `model_artifacts` | 5,230 |
| `model_fit_runs` | 0 |
| `model_promotion_events` | 4 |
| `observation_contract_schemas` | 16 |
| `player_cards` | 3,455 |
| `player_observations` | 1,247 |
| `player_position_stints` | 26,327 |
| `player_provider_mappings` | 1,240 |
| `player_source_facts` | 48,349 |
| `players` | 1,243 |
| `post_match_evaluation_inputs` | 0 |
| `post_match_evaluations` | 0 |
| `product_availability_observations` | 0 |
| `product_coach_observations` | 0 |
| `product_competitions` | 1,657 |
| `product_context_capabilities` | 3,726 |
| `product_context_report_refresh_work` | 228,599 |
| `product_context_snapshots` | 266 |
| `product_fixtures` | 260,317 |
| `product_forecast_refresh_work` | 8,036 |
| `product_forecasts` | 14,054 |
| `product_history_resource_imports` | 26 |
| `product_history_sync_attempts` | 562 |
| `product_history_sync_queue` | 641 |
| `product_history_work` | 1,387 |
| `product_identity_admissions` | 22,515 |
| `product_lineup_accuracy` | 0 |
| `product_lineup_observations` | 0 |
| `product_lineup_players` | 0 |
| `product_match_history_decisions` | 807,733 |
| `product_model_artifacts` | 0 |
| `product_model_evaluations` | 0 |
| `product_model_forecasts` | 0 |
| `product_provider_fixture_observations` | 223,301 |
| `product_provider_history_discovery` | 559 |
| `product_provider_history_scopes` | 1,224 |
| `product_provider_mapping_decisions` | 2,474,144 |
| `product_provider_refresh_state` | 8,038 |
| `product_provider_resource_observations` | 254,896 |
| `product_provider_scope_work` | 11 |
| `product_read_reports` | 74,749 |
| `product_report_refresh_work` | 4,979 |
| `product_source_result_conflicts` | 1,845 |
| `product_standings` | 863 |
| `product_sync_runs` | 13,028 |
| `product_team_aliases` | 18,915 |
| `product_team_match_history` | 478,917 |
| `product_teams` | 17,947 |
| `provider_mapping_history` | 543,513 |
| `provider_request_budgets` | 61 |
| `provider_resource_authority` | 0 |
| `provider_resource_capabilities` | 26 |
| `provider_resource_coverage` | 0 |
| `provider_resource_cursors` | 0 |
| `provider_sync_runs` | 1 |
| `providers` | 42 |
| `quarantine_records` | 1 |
| `quarantine_reprocess_requests` | 0 |
| `quarantine_resolution_outcomes` | 0 |
| `reconciliation_conflicts` | 1 |
| `resolution_decisions` | 30 |
| `resolution_recovery_results` | 0 |
| `resolution_recovery_targets` | 0 |
| `resolution_recovery_work` | 0 |
| `resolution_review_events` | 0 |
| `resource_observation_artifacts` | 12,310 |
| `runtime_model_registrations` | 0 |
| `season_observations` | 164 |
| `season_provider_mappings` | 86 |
| `seasons` | 3,983 |
| `source_resources` | 66,925 |
| `source_snapshots` | 65,117 |
| `sprint2_evaluation_runs` | 23 |
| `team_elo_history` | 0 |
| `team_observations` | 76 |
| `team_provider_mappings` | 21,375 |
| `teams` | 18,011 |
| `validation_findings` | 2,184 |
| `validation_runs` | 6 |
| `work_attempt_metrics` | 102,037 |
| `work_dependencies` | 0 |
| `work_items` | 94,992 |
| `work_lock_metrics` | 6,349 |

</details>

### Provider and historical scope breakdowns

<details>
<summary>Every provider registration and source population, S2</summary>

| Provider | Snapshots | Resources | Registered bytes (not a retention claim) |
| --- | --- | --- | --- |
| `api_football` | 436 | 436 | 142,822,368 |
| `espn` | 3 | 3 | 431,546 |
| `flashscore` | 7 | 7 | 3,284,916 |
| `football_data_org` | 135 | 135 | 15,667,842 |
| `football_data_uk` | 56 | 56 | 19,302,712 |
| `fotmob` | 38,494 | 38,494 | 3,908,169,723 |
| `openfootball` | 1 | 291 | 30,036,862 |
| `pitchapi` | 25,934 | 25,934 | 256,982,331 |
| `provider_00bff669480149e7b91dc1d20a4cc12c` | 1 | 1 | 2 |
| `provider_1a354d1eefa649f49216abb819cff1e8` | 1 | 1 | 2 |
| `provider_1f735332c8eb40c5baca64964f5604c1` | 1 | 1 | 2 |
| `provider_2051331c15f2492884684c80e0377c14` | 1 | 1 | 2 |
| `provider_28c6caad9f464e25a68877601d8b9042` | 1 | 1 | 2 |
| `provider_2bd50b91ff8949868a31cfa8dcefe474` | 1 | 1 | 2 |
| `provider_39604579cb914b4fa4f295b6e7a2cb9c` | 1 | 1 | 2 |
| `provider_3dcb065087ef421e9c26b1d0d1ac311a` | 1 | 1 | 2 |
| `provider_4b74f681ac5f467b9b8df9eac9761a82` | 1 | 1 | 2 |
| `provider_6692cfbe364b4b25ac20fa9c73cedff8` | 3 | 3 | 8 |
| `provider_6f46fd95d285431287b92002a4b17966` | 1 | 1 | 2 |
| `provider_8141a80d60c44158afab0b7430402741` | 1 | 1 | 2 |
| `provider_8452b3e702ea4bb99961c51662f547c9` | 1 | 1 | 2 |
| `provider_96a8f9a8ee03400089d588105abff609` | 1 | 1 | 2 |
| `provider_990c6d0a7a3141a39de2e0f6ff961efb` | 1 | 1 | 2 |
| `provider_9acc6a649ddf4d978310c11da7f183fa` | 1 | 1 | 2 |
| `provider_addc7ed89b204d3e92091a11723e854c` | 1 | 1 | 2 |
| `provider_c00c9a7c76674177bf22918cbe1704ae` | 1 | 1 | 2 |
| `provider_c0917715e3964511a5f8a1ada10498d3` | 1 | 1 | 2 |
| `provider_c630d2162497442c86e92e81cf71b595` | 1 | 1 | 2 |
| `provider_cd4a6890ebe447d5a52f7f7a3a61ddb5` | 1 | 1 | 2 |
| `provider_d28943a771fa43448dbcc5f0b101bf39` | 2 | 2 | 5 |
| `provider_d4bf2c1ddd60449aab3354529619697c` | 1 | 1 | 2 |
| `provider_d8abdad398f040bbb4a28afb315d8644` | 1 | 1 | 2 |
| `provider_ec6d18f493cd43a5a454f4655dae702f` | 1 | 1 | 2 |
| `provider_f34c429bbb564454a8cb8ffe7820f569` | 1 | 1 | 2 |
| `provider_f5b1d447028746ccb27cd73704bea457` | 1 | 1 | 2 |
| `provider_f857530a87a74b9b9f2e793dad0dc60a` | 1 | 1 | 2 |
| `provider_sprint2_058a02e982c541a89c951c281bf25592` | 1 | 1 | 2 |
| `provider_sprint2_66320d12a11743cfa83e0997882f64e0` | 1 | 1 | 2 |
| `soccerway` | 7 | 7 | 2,889,812 |
| `statsbomb_open_data` | 8 | 1,526 | 2,266,588,054 |
| `understat` | 2 | 2 | 100,486 |
| `whoscored` | 1 | 1 | 556,384 |

</details>

| Provider | Current eligible historical fixture decisions | Current ineligible decisions | Ineligibility recorded |
| --- | --- | --- | --- |
| api_football | 58,051 | 858 | 856 ProductIdentityTrustV1; 2 non-played terminal status |
| football_data_org | 127 | 5,260 | ProductIdentityTrustV1 |
| football_data_uk | 131,692 | 104,837 | ProductIdentityTrustV1 |
| fotmob | 29,726 | 57,727 | ProductIdentityTrustV1 |
| openfootball | 73,828 | 16,102 | ProductIdentityTrustV1 |
| pitchapi | 11 | 698 | ProductIdentityTrustV1 |

These are latest `product_match_history_decisions` per fixture ID at S2; older reason strings do not disclose every subcondition. They are not all requalified to today's trust state, nor a proof of pre-kickoff eligibility. S5 `current_history_scopes` retains exact provider/competition/season groups, including UUIDs and reason counts. The query is in I. Do not add provider totals to resource revisions or canonical matches.

## C. Root cause analysis

“Confirmed” below means the observed condition and its present code path are evidenced. It does not prove an undocumented provider outage, the historical operator action that created a row, or an uncertain identity relationship. Proposed changes remain unexecuted. IDs identify issues in this report, not new production contracts.

### I01 — Missing registrations include already-retired synthetic lineage

**Confirmed, P1.** S3 finds 33 unavailable raw resources, 22 dataset versions without their manifests, and 26 unverifiable model artifacts. The raw resources are registered under generated `provider_*` names with sentinel-like all-`c` or all-`f` hashes; their source snapshots nevertheless claim `REAL_PROVIDER`. S5 shows all 22 affected datasets lack `dataset_inputs`; S6 traces 13 forecasts to missing model registrations and separately counts 13 forecasts over seven missing dataset versions. S7 verifies that **all 13 model-dependent forecasts already have** `TEST_ONLY_HARD_GATE_EXCLUSION` / `SYNTHETIC_TEST_LINEAGE` retirement events. Four evaluation retirement events also exist. These events do not retire every parent registration or permit erasing them.

`tests/integration/test_canonical_storage.py:85` creates the same generated provider names, `example/open-data/` identities, sentinel hashes, and manifest conventions. The existing synthetic quarantine identifies itself as such in its stored details. **Historical insertion/run provenance for every parent remains unproved**; do not infer that any missing real artifact is disposable merely from a similar name.

Why recovery did not clear this: integrity checks intentionally inspect registrations rather than manufacture missing bytes; the earlier three-dataset report considered a narrower file-row population. Model status `published` is historical registration, not current physical integrity. This is primarily an inventory/scope problem until authentic loss or test provenance is established. Upstream parent classification must precede restore/rebuild. Downstream test retirements already provide their exact approved exclusion; propagate no broader exemption. Reuse `football.integrity.PostgresIntegrityVerifier`, `football.retirement`, existing immutable dataset/model publishers and retirement consumers. Detailed IDs and expected hashes are in S3/S6, not guessed from names.

### I02 — Legacy manifest identity and physical-file identity differ

**Confirmed condition, P1; corruption hypothesis unconfirmed.** S3 directly hashes registered source-manifest paths: 48 checksum mismatches, all legacy Football-Data UK registrations, plus 34 missing manifests. Of the missing manifest registrations, 33 accompany the test-shaped resources; the other is the legacy OpenFootball snapshot. All 56 Football-Data UK resource byte checks and all 291 OpenFootball resource checks pass.

For example, legacy snapshot `14ceb568-9601-586b-a55a-325d0276aaad` points its manifest path at a ZIP whose physical hash is its source revision, whereas `manifest_sha256` is another registered value. The frozen acquisition bundle's registered digest also differs from its physical JSON bytes. This demonstrates mismatched registration meanings; it does not establish tampering. The current identity reader already labels these separately as `LEGACY_MANIFEST_UNVERIFIED` (`product/identity_admission.py:542`) while verifying resource bytes. Its policy must remain distinct from the newer `manifest-v1:` wrapper contract in `product/historical_manifest.py` and `product/historical_backfill.py:108`.

The two pending parser/validation resource rows are the frozen Phase 1B UK bundle for 2015/16 and 2025/26, not evidence that no subsequent parsing ever occurred. Downstream registrations, acceptance evidence, and source identity must be checked before assigning new parser lifecycle claims. Recovery cannot edit old hashes or relabel the frozen source as newly known. An explicit interpretation or new immutable wrapper/registration may be appropriate after tracing the original contract; which one remains a research task.

### I03 — Source identity proof does not establish a canonical relationship

**Confirmed, P0 integrity gate.** S4 reclassifies 20,805 active team/competition mappings: 15,749 currently admitted, 4,947 unresolved, 108 contradictory, one revoked, and 984 unsafe shared identity groups. Recorded S2 case labels have 4,942 `UNRESOLVED` and six `BLOCKED`; these differ because the fresh classifier recomputes retained proof instead of replaying the last recorded disposition. The latest-event table also contains 1,402 revoked historical mapping decisions, many outside the active mapping population. Do not call all 1,402 current blockers.

S2's active case counts localize unsupported-origin cases to 192 FotMob competitions, 2,168 FotMob teams, one PitchAPI competition, and 41 PitchAPI teams. Its 108 contradictory active cases comprise 103 API-Football teams, one Football-Data UK team, and four OpenFootball teams. An original source ID, a matching name, a Reep candidate bridge, and a deterministic method label do not prove the existing UUID belongs to the source entity. The R02-M report verifies 21 original StatsBomb owner identifiers but still has zero proof-ready canonical proposals; those UUID origins remain unresolved.

Existing recovery correctly refuses admission through `product/identity_trust.py`, `product/identity_admission.py:117`, `product/identity_correction.py`, and `product/resolution_identity.py`. Reep remains a candidate-discovery input; original provider namespace, country/competition context, accepted target anchor, and independent relationship evidence must pass the existing verifier. Deterministic evidence-complete batches can be prepared automatically. Ambiguous relations stay unresolved; no blanket manual approval or new identity store is justified. Historical corrections retain separate valid and knowledge times.

### I04 — Fixture records, native mapping cases, and duplicate members overlap

**Confirmed, P0 integrity gate.** S2 has 94,956 latest native fixture mapping keys: 47,293 `REVIEW_REQUIRED`, 531 `CONTRADICTORY`, 46,586 `AUTO_ACCEPTED`, 546 `MANUAL_ACCEPTED`. FotMob alone has 22,454 no-exact-candidate and 20,260 missing-season-label decisions; PitchAPI has 1,200 and 1,071 respectively. S1 stores 62,290 provisional product fixture rows. These are different populations and must not be added.

S6's active fixture-resolution member counts are 2,687 ambiguous, 11,806 impossible-team-schedule quarantines, 19,844 duplicate-resolved, and 318,425 unique. They map to 2,446 / 11,549 / 19,313 / 318,425 distinct canonical-real IDs respectively; IDs can still overlap across classes. The full historical table's 3,208 ambiguous and 19,883 duplicate-resolved rows include inactive records. Resolution Center's additional fixture-record cases include 43,035 `NEEDS_REVIEW` and 1,745 `BLOCKED`; a verified product identity can still have a separate schedule/result quarantine.

The upstream causes include absent canonical season/geography/team evidence and conflicting exact candidates. Existing conflict guards deliberately reject unsafe fixture publication; retrying downstream history cannot solve them. Reuse `history/fixture_identity.py`, `product/fixture_crosswalk_review.py`, `product/resolution_recovery.py`, and migrations `202610090200_fixture_identity_ingestion_guard.sql`, `202610210100_unknown_season_fixture_reconciliation.sql`, `202610310500_resolution_recovery_work.sql`. Current deployed reconciliation functions have both zero-argument and `uuid[]` signatures (S6). Batch only exact, source-backed cases; preserve member/orientation/season/time relationships and conflict trails.

### I05 — Quota deferral and deterministic integrity errors share a retry path

**Confirmed, P1.** S2 has 517 shared historical items waiting: 495 `ApiFootballError` quota/cooldown suppressions, 11 `RaiseException` identity guard failures, and 11 `PROVIDER_SCOPE_FAILED` live-priority deferrals. The legacy queue's 506 pending jobs are the **same 495 quota and 11 identity cohorts**; they are not 506 additional affected datasets. Legacy queue attempt counts reach 33 and 40; shared retry policies permit roughly the PostgreSQL integer maximum. S2's API-Football budget for 2026-11-02 records 99 requests, zero remaining, `exhausted=true`, and zero historical requests used. A past cooldown timestamp does not make a zero daily balance available.

The budget suppressor is intentional (`product/api_football.py:42`). The defect is that `product/sync.py:758` handles **all** `psycopg.Error`, `ApiFootballError`, and transport errors via `_retry_history_job`; `product/history_worker.py:301` maps them all to `RETRYABLE`. A deterministic identity guard cannot be repaired by backoff. Existing `RetryClassification.BLOCKED_EXTERNAL` and SQL `fail_work` cooldown/retry arguments are available; distinguish exhausted budget, transient connection/serialization failures, identity blockers, malformed data, and cancellation. Preserve fencing and original attempts. Do not increase quotas, purchase plans, or retry terminal old sync runs simply to improve statistics.

### I06 — History discovery exists while scheduled processing is disabled/deferred

**Confirmed configuration and backlog, P1; deployed flag uncertainty remains.** Of 1,224 provider history scopes, 873 are unattempted (`attempts=0`): 579 FotMob and 294 PitchAPI. Failed scopes comprise 239 FotMob `BLOCKED_IDENTITY`, 95 FotMob `COMPLETED_WITH_ERRORS`, two FotMob missing league lists, and two PitchAPI stored-snapshot replay failures. Eleven are `DEFERRED` for `LIVE_SYNC_HAS_PRIORITY` (four FotMob, seven PitchAPI). Two FotMob scopes succeeded. S2/S5 retain exact season groups and original labels.

The local configuration has `MATCHFORGE_HISTORY_SYNC_ENABLED=false`, one-hour cadence, per-provider history scope limits of two, discovery limit one, freshness 86,400 seconds, and API-Football history cap 2024. The code checks the history enable flag in `go/api/internal/app/app.go:166` and prioritizes live work through `product/provider_history_scopes.py`. The last recorded `HISTORY_BACKFILL` success began 2026-11-01 13:09 UTC; manual runs do not prove the scheduled process uses the current `.env`.

Seven FotMob refresh resources have `RECOVERY_FIXTURES_MISSING` and no successful refresh. Two PitchAPI resources have `DETAIL_REQUEST_FAILED`. No authentic league-fixture list should be manufactured. First confirm the deployed process's effective configuration and permissions; then use the existing replay/claim mechanism and fairness controls. Enabling a flag alone does not solve blocked identity, quota, or lawful access. Unavailable/empty provider scopes need separate, evidenced terminal or deferred treatment instead of an endless acquisition loop.

### I07 — Repository support is ahead of operating recovery schema

**Confirmed, P1.** Operating migrations stop at 202610310500. The file recovery, parity recovery, and stage-control tables/functions from 202610310600/700/800 are absent there but present in V4 research databases. Features depending on these migrations cannot be represented as deployed merely because tests or research databases have them. The architecture shadow ends at 202610200100 by design.

Historical logs additionally show 3,729 failed FotMob/PitchAPI sync runs with `reconcile_unknown_season_fixtures()` missing, last seen 2026-10-21. S6 proves that function now exists; this historical incident must not trigger another implementation of reconciliation. Recovery entrypoints need a read-only schema/build preflight and a useful unavailable-feature response. A separately authorized deployment of existing migrations must rehearse in isolation, verify compatibility, and keep all routes `LEGACY`. **Applying a migration is not permission to switch a stage or advance Architecture V2.**

### I08 — Historical failures, current defects, and nested errors are poorly separated

**Confirmed historical failures and diagnostic gap, P1.** S1 has 6,200 failed product sync runs versus 1,030 failed shared work items; runs and work IDs are different units. S2 groups failures by error and time. It includes DNS/transport errors, body deadlines, publication-fence loss, quota responses, deterministic admission failures, and operator cancellation. S5 finds **2,123** generic failed FotMob/PitchAPI runs with no `summary.errors` (`1,551 + 572`); detailed causes may still exist elsewhere in their summaries or logs.

Three reproducible saved failures are:

- `.local/sync-runs/54c83071-b8d5-44c9-a68e-e45592f55469.log:1`: missing reconciliation function. Current schema now contains it.
- `.local/sync-runs/63f93971-262b-43ab-81f6-c86bb9eb3faf.log:29`: `_fixture_observation_sha256` referenced undefined `fixture_id`. Current `operational_provider_sync.py:3059` accepts that argument; preserve the existing correction instead of adding a duplicate fix.
- `.local/sync-runs/f48511a7-5e48-4f92-96d5-371d97e2716a.log:1`: inverted source season bounds (2286-11-20 to 1970-01-01) were rejected by `seasons_check`. Current `product/sync.py:112` detects invalid source bounds, logs provenance, and returns unknown dates; existing tests cover valid, malformed, and inverted cases.

The current repository addresses those last two code defects; deployed build identity and successful processing of their exact retained inputs still need verification. Do not reopen every historical failed run. Use existing retry-as-new-operation semantics only when the underlying cause is removed, cancel decisions permit it, and repeated publication converges. `FAILED`, `CANCELLED`, expired leases, and superseded generations must retain their audit history. Zero expired current leases in S2 means this audit found no stale-running-job batch to reclaim.

### I09 — A healthy bounded report worker can still leave a large backlog

**Confirmed backlog, P1; sustained throughput bottleneck not yet measured.** S2 has 176,903 context generations pending out of 228,599; error fields are null. Only seven performance report generations are pending in that snapshot; comparison and forecast generation worklists are caught up. A separate old `DETAIL_BUSY` shared forecast item does not prove an uncompleted generation if a later generation already finished.

`product/public_reports.py:279` already processes at most 32 context entries, reserving half for the oldest backlog and half for relevant fixtures. `go/api/internal/app/app.go:214` schedules public reports on a one-minute ticker. **Do not add fairness that already exists.** Even at a full 32 completions per minute and zero new arrivals, 176,903 entries would need about 92.1 hours; actual runtime, retries, and arrivals can make it longer. This is a capacity calculation, not a promised recovery time or an approved SLA.

Investigate service and arrival rates, relevance, existing generation deduplication, busy scopes, and persisted report provenance. Prefer controlled replay through current workers before changing limits. Any tuning requires measured load and preserved oldest/live fairness, leases, generation fencing, immutable report hashes, and API parity. No worklist truncation or forced `completed_generation` update is a valid fix.

### I10 — Market readiness is correctly blocked by missing target qualification

**Confirmed, P1.** The operating pilot scope's 67 unbound family diagnostics are 53 `DATA_COLLECTION_REQUIRED` and 14 `INSUFFICIENT_PLAYER_DATA`. Operating canonical resource resolutions, provider authority decisions, provider coverage, and canonical coverage registries contain zero rows. Its 12,310 normalized observations and 26 sampled capabilities do not qualify an entire competition-season or an exact target.

`product/market_capabilities.py:197` first tests target-bound input coverage, common eligible fixtures, and parameter binding; it then tests semantics and model/evaluation readiness. `RESEARCH_REQUIRED` means those data checks are satisfied but model/evaluation requirements are not. It is **not a failed ingestion job**. `ENGINEERING_READY` requires separate scoped publication approval. `SUPPORTED` is not available through a status-edit endpoint.

The prior R02-M milestone retained five already accepted API-Football fixtures, ten research-qualified goal scalars, zero bookmaker-equivalent labels, and zero player admissions. S5 freshly confirms ten observation artifacts and **one selected COMPLETE canonical coverage row** in its research replay database. The saved milestone explicitly records one provider coverage report and one canonical coverage report, two in total (`v4-issue-02-unblocking-final.json:203`). S5 independently rechecked the canonical row; the experimental provider-coverage table was not separately queried. There is no two-versus-one canonical coverage discrepancy. One historical bound `RESULT_1X2/HOME` result is research-compatible; the normal unbound family report does not automatically consume that evidence. Neither mode proves scientific sufficiency, production coverage, or a new model authorization.

Reuse `coverage/resources.py`, `coverage/storage.py`, `canonical_resources/resolution.py`, `product/market_capability_cli.py`, and the existing qualification/evaluation owners. Preserve provider semantics, source/target period, settlement/void rules, explicit parameters, football and knowledge cutoffs, and publication policy. The 254,896 `ELIGIBLE` development-only legacy resource revisions must not silently become historical features.

### I11 — Native player observations and resource capability are not qualified exposure

**Confirmed, P1.** S5 finds 1,240 StatsBomb player mapping claims and 27,354 participation observations (27,353 StatsBomb plus one test-shaped observation), but no qualified continuous membership or transfer history is asserted. The existing historical-label pilot verified 644 native player IDs and reported zero admitted canonical player exposures/minutes. Operating lineups, lineup players, availability observations, and lineup accuracy tables are empty. Thus all 14 player-dependent market families remain explicitly insufficient.

For native normalized samples, API-Football, ESPN, Flashscore, FotMob, PitchAPI and Soccerway each show 40 native player IDs, and Understat 32, with zero corresponding recorded mapping claims in the audit's join. Those are provider-native samples, not 272 globally distinct players. Position stints, starting/substitute roles, bench membership, lineup prediction and played minutes have different meanings. The 2,927 `UNSUPPORTED_BY_COMPETITION` context capability rows are not automatically collection failures; 799 are `SUPPORTED` capability declarations, not 799 populated resources.

Reuse `scripts/inspect_v4_pilot.py:305` (`player_report`), `providers/normalization/participants.py`, `contracts/observations_v3.py`, existing identity owners, and the exact evidence in `v4-issue-02-player-exposure.json`. The audit supplies no authority to create a second membership ledger or admit player identities. No membership interval, transfer date, or minute duration may be inferred from adjacent lineups or a source string alone.

### I12 — Quality findings preserve real unknowns and one intentional synthetic conflict

**Confirmed, P1/P2 by rule.** S2's complete rule counts are:

| Rule | Severity | Finding occurrences | Scope/meaning |
| --- | --- | ---: | --- |
| SB_UNKNOWN_EVENT_TYPE | WARNING | 1,499 | 446 source resources; preserve unknown mapping |
| SB_IMPOSSIBLE_EVENT_TIMESTAMP | WARNING | 404 | 261 source resources; exclude unsafe temporal features |
| SB_NONMONOTONIC_POSITION_STINT | WARNING | 214 | 128 provider entity IDs; preserve and review |
| SB_EVENT_LOCATION_OUT_OF_BOUNDS | WARNING | 15 | seven source resources; exclude spatial features |
| SB_CONFLICTING_PLAYER_FACT | WARNING | 14 | seven provider entity IDs; preserve variants/null consensus |
| SB_SCORE_INCONSISTENCY | QUARANTINE | 38 | 38 source resources/match IDs; quarantine match |

Rules and actions are in `validation/statsbomb.py` and `schemas/quality/statsbomb-quality-policy-v1.json`. An unknown provider event ID may be a new version, an unsupported event, or malformed input; which explanation applies must be checked against the pinned provider specification and exact retained resource. Warnings with deliberate feature exclusion are legitimate outcomes, not a target for blanket acceptance.

The one `quarantine_records` row is `football-data-uk-p1-synthetic-score-conflict-v1`, with `(1,0)` versus `(1,1)` synthetic observations and `details.status=NEEDS_REVIEW`; its persistence status is `open`. One reconciliation conflict is `QUARANTINED`. These are the same synthetic case, not two additional football failures, and are separate from 38 StatsBomb finding occurrences. `QuarantineStatusV1` has uppercase operation labels while its table uses lowercase persistence labels. Existing reprocessing has no requests because no evidence-backed decision was supplied; preserve that distinction instead of bulk resolving it.

### I13 — External predictions mostly lack exact bindings, so settlement stays pending

**Confirmed, P1.** There are 1,250 unmatched and seven ambiguous prediction IDs, 47 matched, 1,304 date reviews, zero new binding rows, and 1,280 current pending settlements. Provider breakdown: unmatched Slybet 559, R2bet 316, Tips1960 220, Matchoutlook 155; all seven ambiguous predictions are R2bet. R2bet has 45 matched predictions (23 pending, 17 won, five lost); Matchoutlook has two matched wins. Current date-review status is `VERIFIED` for 588 and `NOT_APPLICABLE` for 716; no present mismatch is counted. The history's 1,409 `PENDING` settlement revisions are not the current pending population.

The 1,304 captures, reviews and predictions are not interchangeable row populations; captures total 1,381 and revisions total 1,477. Repeated ordinary page retrieval cannot create an exact canonical binding if the source lacks a provider fixture ID, valid date/time, unambiguous identity, or qualified target. `external_predictions.py:221`, `external_prediction_recovery.py`, the existing binding/date-review tables, and `go/api/internal/app/read_reports.go:26` fail closed. Preview existing exact candidates, append only approved/evidence-valid binding changes, and settle from authoritative finished regulation results. Leave ambiguous or unsupported markets pending/quarantined with reasons. A settlement is not a backdated forecast or evidence that a missing pre-match forecast existed.

### I14 — Stale lifecycle claims and repeated score disagreements need source-level review

**Confirmed symptoms, P1; provider/parser causes require case evidence.** S6/S7 finds 41 of 51 `LIVE` fixtures more than 48 hours past kickoff (33 provisional, eight verified), one verified `LIVE` fixture whose kickoff is still in the future, and 1,611 `SCHEDULED` fixtures more than 48 hours old (237 provisional, 1,374 verified). The 48-hour predicate is an audit age bucket, **not an approved automatic-finalization deadline**. Providers can legitimately report delayed, postponed, suspended, or incomplete events.

S7 also counts 1,845 source-result conflict events: 1,835 FotMob-to-FotMob events over ten fixture IDs, six OpenFootball-to-UK events over six IDs, two UK-to-UK events over one ID, and two API-Football-to-FotMob events over two IDs. These are events, not 1,845 distinct matches; distinct sets across provider-pair groups can overlap. Fresh official/provider evidence and the existing source update ordering must distinguish corrections from invalid transitions and identity errors.

Inspect exact retained fixture statuses, source update times, period/elapsed state, identities and score basis through `product/operational_provider_sync.py:2999` (`_valid_transition`), `_store_observation`, `_reconcile_observation`, fixture-resolution guards and source conflict records. Never infer final scores from elapsed wall time or choose a preferred provider merely to suppress a conflict. Keep original observations; publish only allowed newer conclusions after evidence passes.

### I15 — Technical access and permitted acquisition are different facts

**Confirmed published restriction, P0 for further acquisition; individual licence scope remains unverified.** FotMob's published terms dated **2026-10-22** prohibit systematic/bulk automated retrieval and require express written consent for data extraction/use. Its site footer also prohibits automatic services. The local provider is enabled and existing worker/budget rows show ongoing ordinary fetching. This audit found no account-specific consent document; lack of one in the inspected scope does not prove no agreement exists. Request and verify the applicable permission or use an already licensed alternative before recommending further FotMob acquisition.

The six external source registrations explicitly distinguish technical availability from rights. R2bet/Slybet say no explicit automation permission was found; Matchoutlook/Tips1960 carry restrictive reuse notes; Forebet is disabled after a normal HTTP 403 challenge. No bypass, alternate identity/account, or challenge circumvention is a remedy. PitchAPI technical docs were retrieved, but its attempted terms URL was unavailable; existing exact retention/owner decisions remain the relevant evidence until current rights are confirmed. Reep's public download is CC0, but that licence does not license upstream provider payloads or prove bridge accuracy. Local release `2026-10-31.1` and the public page's `2026-10-25.1` label differ; do not silently replace the pinned local artifact.

Provider-specific research and failed documentation fetches are in D. The report proposes permission-aware acquisition; **it did not disable workers, alter config, contact providers, or make any provider data request.**

### I16 — Some diagnostic states are placeholders rather than measurements

**Confirmed code limitation, P2.** `providers/observability_store.py:76` constructs `circuit_state="CLOSED"` and supplies zero for several unavailable metrics. That state does not prove a provider circuit is closed or that resolution/rate-limit/publication failures are zero. Its lifecycle query is also narrower than legacy `product_sync_runs`; a successful scope cannot establish health for every provider route.

S6 checks persisted public-report JSON: it has no `status`, `report_status`, or `comparison_status` keys. Go derives READY/PENDING/FAILED/EMPTY and comparison statuses at request time. Querying a missing JSON key and interpreting null as no error would hide real state. Preserve these APIs; derive diagnostics using their actual owner predicates, mark unavailable measurements explicitly, and add only measurements with current consumers. Use existing metrics/work status and avoid a parallel health/state database.

### I17 — Scientific failure and phase blockers are expected controls, not data tickets to clear

**Confirmed governance state, P0 for unauthorized transitions.** The 19 `FAIL` and four `PASS` Sprint 2 run registrations include historical/retired evidence; they are not 19 retryable data jobs. Phase 35's frozen 4,253 mapping-proof population, 59 generic Elo conflicts and 327 insufficient-history targets are historical gate populations, **not refreshed current counts**. Their exact required proof remains separate from this audit's active mapping denominator.

The architecture shadow has 3,153,511 observation artifacts and 10,192 canonical resolutions, yet zero canonical coverage rows; operating/research databases have different routes, counts and purposes. Large normalized populations do not imply complete canonical, coverage, serving or API parity. Existing project-status owner decisions keep Architecture V2 cutover/retirement blocked, V4 Issue 2 incomplete, and subsequent scientific work separately authorized. Do not reopen terminal routes, move thresholds after results, use outcomes as pre-match inputs, or modify `docs/project-status.json` to claim remediation/phase completion. The remediation workstreams below do not authorize architecture cutover.

## D. Research findings and solution comparison

Research retrieved **2026-11-02**. Recommendations combine current code/SQL evidence with primary sources. Website crawl timestamps or current documentation are not proof of the contract version under which old bytes were acquired. No commercial quote, additional request budget, provider inquiry, or library installation was made.

| Ref | Primary source and relevant finding | Limits and application |
| --- | --- | --- |
| R1 | [PostgreSQL 18 transaction modes](https://www.postgresql.org/docs/18/sql-set-transaction.html): read-only repeatable-read can hold a consistent query snapshot. | Database snapshots do not freeze files or an independently queried API. This audit records separate collection timestamps. |
| R2 | [PostgreSQL 18 SELECT](https://www.postgresql.org/docs/18/sql-select.html): `SKIP LOCKED` can support competing queue consumers but yields an incomplete locked-row view. | Use the existing claim/fence SQL; use ordinary consistent reads for inventories. It does not itself provide exactly-once publication. |
| R3 | [PostgreSQL 18 INSERT](https://www.postgresql.org/docs/18/sql-insert.html): conflict handling uses explicit unique constraints. | Reuse existing semantic identities and transactions; a retry must verify identical input/output identity, not merely suppress a duplicate insert. |
| R4 | [PostgreSQL 18 backup guidance](https://www.postgresql.org/docs/18/backup-dump.html): database dumps provide a consistent restorable database snapshot. | Raw/object files and a restore test are separate evidence. Do not restore over operations. |
| R5 | [StatsBomb official open-data repository](https://github.com/statsbomb/open-data): selected competition-season JSON, match events/lineups, selected 360 coverage, and attribution terms. | A complete file in a selected scope does not imply broad coverage or a historical availability timestamp. Reuse exact pinned specs/resources; inspect the licence for the intended use. Protected targets remain excluded. |
| R6 | [Official StatsBomb match format](https://raw.githubusercontent.com/statsbomb/open-data/master/doc/StatsBomb%20Open%20Data%20Specification%20v1.1.pdf). | Useful for source-specific field interpretation; a current document cannot silently upgrade an old parser or resolve every unfamiliar event ID. Match the pinned event specification separately. |
| R7 | [Football-Data UK field notes](https://www.football-data.co.uk/notes.txt): full/half-time goals, shots, corners and cards are separate fields; some statistics and card-count conventions differ by league. | These notes were readable today. `data.php` returned 429; attempted `terms.php`/privacy URLs were unavailable. Field definitions establish no blanket automation or redistribution right. |
| R8 | [OpenFootball football.json](https://github.com/openfootball/football.json): public-domain/CC0 fixture/result data with documented upstream update dependence. | A legitimate alternative for covered fixtures/results, not a source of missing minute exposure, rich events, historical knowledge times or bookmaker semantics. Pin commits and admit identities separately. |
| R9 | [API-Football v3 specification](https://www.api-football.com/documentation_v3) and [official quota guidance](https://www.api-football.com/news/post/how-to-optimize-api-sports-calls-and-quota-usage). | Native status and score periods matter; some final results can be delayed. Rate limits require bounded, quota-aware scheduling. Official docs do not prove the account's current plan or authorize a larger budget. |
| R10 | [API-Football terms](https://www.api-football.com/terms). | Terms permit building applications while restricting direct resale and quota evasion through multiple accounts. Confirm actual account rights; no purchase or scope expansion is proposed automatically. |
| R11 | [football-data.org v4 API policies](https://docs.football-data.org/general/v4/policies.html): nulls/empty lists are valid; rate limits and current-season/default-date behavior are explicit. | Existing fallback adapters must request explicit historical scopes; do not replace unknown values with zero or assume a current team squad proves historical membership. |
| R12 | [PitchAPI reference](https://pitchapi.dev/): documents endpoint shapes, request/error metadata, retry behavior, UTC fields, coverage/plan variation and predicted lineups. | Verify exact retained/API contract before changing adapters. Attempted `https://pitchapi.dev/terms` was unavailable; current rights were not independently established. Do not replace the existing transport with a new SDK without a demonstrated gap. |
| R13 | [Reep official distribution](https://www.reep.football/data/): CC0 dated downloads with manifests/checksums, provider bridges and redirects; hosted API has a separate access model. | Candidate discovery and source provenance, not permission for upstream payloads or automatic MatchForge admission. Public page advertises 2026-10-25.1 while local evidence pins 2026-10-31.1; reconcile provenance before any update. |
| R14 | [FotMob terms dated 2026-10-22](https://www.fotmob.com/tos.txt) and [site footer](https://www.fotmob.com/). | Explicit consent and automation restrictions materially affect acquisition planning. Account-specific written permission was not inspected. Obtain evidence or select an already permitted source. |
| R15 | [Sports Reference bot policy](https://www.sports-reference.com/bot-traffic.html) was attempted and returned 403. | No new FBref acquisition permission was verified. Preserve the already isolated retained research and its recorded restrictions; do not bypass access controls. |

Failed research URLs are recorded as failures, not supporting authorities. Exact provider rights, inaccessible terms, and missing authentic bytes remain evidence gaps. For sources absent from the operating database (for example FBref/ClubElo/Sofascore), current research registry counts are reported separately in A; capabilities in code do not imply usable production datasets.

| Issue | Candidate solutions | Recommendation, reliability and correctness | Complexity, cost and maintainability | Sources / confidence |
| --- | --- | --- | --- | --- |
| I01 | Re-download/rebuild every missing registration; classify provenance and reuse approved retirements first | Classify by exact IDs and lineage. Restore only authentic matching bytes; already-retired synthetic forecasts remain historical evidence. | Local inventory work first; bulk acquisition may be pointless or impossible. Reuse integrity/retirement owners. | S3/S6/S7, R3/R4; high on observed gaps, uncertain on missing originals |
| I02 | Overwrite old digests; interpret old contract and add independently verified new wrappers/versions | Preserve old registration; explain legacy logical/physical identities and publish new evidence only under the correct contract. | Moderate migration/compatibility analysis; no extra provider cost if retained bytes suffice. | S3/S4, historical_manifest.py, R3/R4; high on mismatch, medium on contract-specific repair |
| I03 | Name/fuzzy batch matching; exact ID/namespace/context/independent relationship verification | Existing trust/crosswalk verifier plus exact proposals. Leave ambiguous identities unresolved. | Candidate batches reduce review effort; Reep local download reuse avoids new service/dependency cost. | S4, R5/R8/R13; high on blocker, case-dependent recovery |
| I04 | Merge by date/score/name; reuse reviewed fixture correspondence and active resolution groups | Match exact accepted members, season, orientation and kickoff; preserve conflicts. | Bounded batch recovery through existing code; no new matching engine. | S2/S6, R8/R9; high |
| I05 | Raise retries/quotas; classify retryable, blocked-external, deterministic and cancelled causes | Reuse current classification, cooldown and shared-work contracts. Retry only changed/transient conditions. | Small Python/SQL-adapter changes; lower wasted work. Paid-plan costs need a quote and owner decision. | S2, R2/R9/R10; high |
| I06 | Enable all history/network fetching; confirm runtime config and replay eligible retained scopes first | Address rights, identity and quotas before enabling exact permitted cohorts; retain live priority without unbounded starvation. | Existing workers/config; a measured cadence avoids blanket spend and large new infrastructure. | S2/S5, R9/R11/R12/R14; high on backlog, medium on deployed configuration |
| I07 | Duplicate recovery logic; guarded deployment of existing migrations | Version/build preflight, isolated migration rehearsal and ordinary deployment approval; keep legacy routing. | Existing SQL migrations; deployment risk requires restore evidence. No cutover implementation. | S2/S5/S6, R4; high |
| I08 | Retry all old failures; verify current fixes and expose original cause per run | Preserve old failures; validate exact retained cases against current build before scoped replays. | Existing log/summary structures; no replacement orchestrator. Network/DNS state may be external. | S2/S5, saved logs, R2/R12; high on incidents, medium on current deployment |
| I09 | Mass-complete generations/increase limits immediately; drain and measure existing bounded worker | Measure arrival/completion rates and fairness; replay within current bounds, tune only if measurements justify it. | Reuses existing 32-entry batch. Wall time/CPU/DB load are real costs; no promised completion time. | S2, public_reports.py, R2/R3; high on backlog, medium on sustained capacity |
| I10 | Translate all blocked states to supported; qualify exact targets through existing registries | Recover shared upstream inputs, bind exact semantics and parameters; retain research/evaluation/publication gates. | Batch by shared inputs and competition-season; no model or API expansion merely to clear statuses. | S5, R5/R7/R9/R11/R12; high |
| I11 | Infer minutes/membership from lineup presence; qualify explicit player/fixture/period/exposure evidence | Reuse current observations and identity owners; accept only proved canonical exposure. | Higher evidence cost; permitted richer sources may require acquisition approval. New independent membership logic is unnecessary without a contract gap. | S5, R5/R9/R11/R12/R13; high on absence, uncertain on recoverable coverage |
| I12 | Relax warnings/quarantine; compare exact source/version and preserve existing quality action | Add only supported mappings/parser corrections and new immutable outputs; explain unchanged legitimate findings. | Rule-specific tests; existing validators minimize maintenance. Some source errors have no recoverable replacement. | S2, R5/R6/R7; high on rules, case-dependent cause |
| I13 | Aggressive name joins/recollect pages; exact binding/date/settlement recovery | Reuse bindings and reviews; process only exact lawful retained candidates, leave ambiguity explicit. | No new scraper or settlement engine; uncertain source rights may block fresh collection. | S2, R9/R14; high on status counts, conditional on evidence |
| I14 | Finalize by age/preferred provider; compare exact source revisions and official final state | Reconcile identity, status transitions and score periods with the existing guards. | Ten heavily repeated FotMob cases are a useful batch investigation; future acquisition still permission-dependent. | S6/S7, R9/R12; high on symptoms, medium/low on upstream cause |
| I15 | Treat public reachability/private R&D as permission; verify written/published rights or switch sources | Preserve evidence, enforce existing permission contracts, and use only scoped permitted acquisition. | No new technical stack. Written consent, account changes or costs require owner action. | R7/R8/R10/R12/R13/R14/R15; high on FotMob text, unknown on account-specific exceptions |
| I16 | Add another status service; complete existing diagnostic measurements and represent unknowns | Reuse existing work/provider/read-report owners; never report invented zeros or circuits. | Small consumer-led changes and contract tests; no extra datastore. | S5/S6, R1/R2; high on code limitation |
| I17 | Re-run failed scientific routes or bypass parity; preserve gates and report exact remaining work | Separate data recovery from scientific authorization and architecture cutover. | No model spend or phase work until explicitly authorized. | project-status.json and gate evidence; high |

## E. Status transition and recovery matrix

Expected recoverable counts below are **conditional bounds or unknown**, never forecasts of success. A count is not recovered until the target's full verification passes. `SUCCEEDED` belongs to a completed operation; historical failed runs and findings remain recorded.

| Issue | Current status | Target status | Required action | Preconditions | Verification | Expected recoverable count |
| --- | --- | --- | --- | --- | --- | --- |
| I01 | Missing/BLOCKED source, dataset or model checks; historical `published` | Verified physical/logical integrity, or explicitly classified retained test evidence | Prove provenance; restore exact bytes or publish a new immutable version where justified | Authentic backup/source and lineage; existing retirement scope respected | Existing integrity verifier, checksum/size/lineage comparison; exact retirement joins | Unknown; 33 raw, 22 dataset, 26 model registrations are candidates for classification, not a guaranteed restore batch |
| I02 | LEGACY_MANIFEST_UNVERIFIED; direct checksum mismatch; two pending resource lifecycle rows | Correctly interpreted legacy status or independently verified new registration | Trace original digest meaning and downstream processing; append new evidence only if required | Exact raw bytes and original contract known | All 56 UK and 291 OpenFootball raw checks stay valid; new wrapper verifies; old hashes unchanged | 48 mismatches + one additional missing legacy manifest investigated; new parser claims for two resources only if evidenced |
| I03 | UNRESOLVED / CONTRADICTORY / REVOKED / BLOCKED | ORIGIN_ANCHOR/CROSSWALK and current trusted result, or preserved explicit quarantine | Existing exact identity proof/correction | Native namespace, accepted target, independent relationship, valid/knowledge time | Existing trust predicate, fresh identity audit, no new unsafe shared group | Unknown subset of 5,056 active unadmitted mappings; no bulk promise |
| I04 | REVIEW_REQUIRED, provisional, active schedule/ambiguity quarantine | Existing accepted/UNIQUE/DUPLICATE_RESOLVED conclusions | Exact season/member/orientation/time evidence; existing fixture recovery | I03 where entity identity is needed; no competing candidate | Re-run current fixture resolution and conflict guards; count both members and unique fixtures | Unknown subset of 47,293 native reviews and active quarantines; populations overlap |
| I05 | 495 quota waits; 11 identity retry loops; 11 provider-scope deferrals | Deferred until real capacity, BLOCKED_EXTERNAL where contract applies, then new verified SUCCEEDED attempt | Correct classification and scheduling; do not change source truth | Budget/entitlement restored or identity evidence supplied | No new deterministic retry without changed blocker; successful attempts retain original lineage | Classify all 517 waits; recover unknown subset, never assume 495 new historical datasets |
| I06 | 873 PENDING, 338 FAILED, 11 DEFERRED scopes; failed refresh resources | Valid SUCCEEDED scope or evidenced legitimate unavailable/deferred state | Confirm deployed flag; existing lawful retained replay/acquisition | I03/I05/I15; approved exact scope and budget | Full scope's resources stored/normalized, original errors resolved, downstream history/coverage reconciled | Unknown; up to 1,222 non-success scope keys investigated, not necessarily recoverable |
| I07 | Recovery/parity/stage functionality absent from operating schema | Compatible deployed capability; route remains LEGACY | Rehearse then separately approve existing migration deployment | Backup/restore and compatibility evidence; no cutover | Applied versions, required tables/functions, unchanged route and identity/artifact checks | Three existing migrations; zero status records healed merely by deployment |
| I08 | Historical FAILED/CANCELLED/LEASE_EXPIRED; generic summaries | Clear cause and new verified successful operation when warranted | Verify current build/fixes, original cause, retained input, operator intent | Rights and original failure removed; current lease ownership | Current fixed input succeeds idempotently; old run unchanged | Unknown subset of failures; zero expired running leases found in S2 |
| I09 | generation > completed_generation | Current generation completed by normal publication | Existing bounded/fenced worker, measured throughput | Correct source fingerprint, acceptable DB load | Remaining eligible backlog and age, exact output hashes, no skipped generation | 176,903 candidate context generations at S2; net backlog depends on arrivals and eligibility |
| I10 | DATA_COLLECTION_REQUIRED / RESEARCH_REQUIRED / ENGINEERING_READY | Next genuine readiness diagnosis, then only separately authorized SHADOW/SUPPORTED | Bind qualified input, semantics, sufficient history, evaluated model and publication | Frozen scientific rules and target-specific evidence | Existing `assess_market`, coverage intersections, model lineage/evaluation and publication proof | No supported-market estimate; 67 operating families assessed |
| I11 | INSUFFICIENT_PLAYER_DATA / unsupported context | Qualified exact player input, or unchanged unsupported state | Prove identity, fixture participation, period exposure and membership as required | Legitimate source and exact semantic definitions | No invented minutes or continuous intervals; tests for bench/substitute/transfer/unknown | Unknown; 14 families affected; existing canonical pilot exposure remains zero |
| I12 | WARNING / QUARANTINE / open / NEEDS_REVIEW | Policy-valid new output or preserved justified finding | Exact rule and source/version investigation; no threshold relaxation | Source confirms correction or supported interpretation | Rule-specific tests and immutable output comparison; unresolved score conflicts stay sealed | Unknown subset of 2,184 findings; synthetic case need not become resolved |
| I13 | UNMATCHED / AMBIGUOUS / PENDING settlement/comparison | MATCHED + evidence-valid date, then appropriate settlement/READY where supported | Exact source binding and finished result; original pre-match forecast if comparing | I03/I04/I14/I15; no ambiguous source date | Unique binding, append-only review, correct period/void rules, repeat convergence | Unknown subset of 1,257 unbound/ambiguous and 1,280 pending; overlap prevents summing |
| I14 | Stale/future LIVE/SCHEDULED; score conflict events | Source-backed allowed lifecycle/result conclusion | Retained revision comparison, identity and time/period check | Newer authoritative evidence or deterministic parser correction | Existing transition guard, no fabricated score/final state, conflict trail preserved | 41 old LIVE + one future LIVE + 1,611 old SCHEDULED investigated; count is not a recovery guarantee |
| I15 | TECHNICALLY_AVAILABLE/ENABLED without demonstrated acquisition right; 403/unavailable source | Existing permitted capability or explicit access blocker | Verify exact permission/entitlement; select approved alternative | Written/published permission and approved request scope/budget | Source terms/consent reference, no bypass, current capability accurately describes access | No guaranteed source expansion; Forebet remains disabled absent lawful access |
| I16 | CLOSED/zero placeholders; computed API states not persisted | Measured value or explicitly unavailable diagnostic | Wire actual existing telemetry; evaluate correct serving predicates | Existing current consumer and compatible response contract | Unknown never silently becomes healthy; diagnostics agree with scoped work/results | Code/diagnostic improvement; no record recovery estimate |
| I17 | FAIL, BLOCKED, NOT_RUN, NOT_READY phase/evaluation records | Preserve history; new gate result only after independent authorized proof | Maintain frozen exclusions/thresholds and owner handoff | New explicit authorization for subsequent science/cutover | Exact gate acceptance, parity and unchanged protected artifacts | Zero historical failed results to rewrite; future gate result unknown |

Unproved identities, absent authentic bytes, unsupported provider semantics, missing historical knowledge times, legitimate provider gaps, unavailable player exposure, and unapproved scientific/publication states **must remain unresolved or explicitly unavailable**. “Research completed” is not equivalent to “data recovered.”

## F. Prioritized remediation roadmap

These six phases are **workstreams**, not new architecture phases or authorization to perform fixes during this audit. Dependencies govern execution: for example DS14's retry fix precedes DS06's recovery, even though reliability is displayed under Phase 4. Prefer one bounded implementation concern per task branch and the existing checkout. Do not create a second pipeline, identity workflow, provider transport or status store.

Each task below identifies its issue, exact current cohort or denominator, dependencies, change location, evidence/research, schema/API/config impact, tests, verification, recovery limits and rollback. Query labels refer to the actual SQL in S1–S7 and I. `AUTONOMOUS` means technically safe **when a later instruction authorizes execution**, with existing contracts and phase limits still binding. `RESEARCH_DEPENDENT` permits evidence gathering and preparation before the missing evidence exists; it does not authorize speculative data mutation.

### Phase 1 — Immediate recovery preparation

#### DS01 — P0 — Freeze task scope and build a deduplicated recovery manifest — AUTONOMOUS

- **Issue/cohort:** all I01–I17; start from the 131-table census, 20,805 active entity mappings, 94,956 latest native fixture keys, and explicitly separate historical events and research databases. Counts above are baseline evidence, not constants to encode.
- **Change/approach:** reuse existing read-only inventories (`providers/data_audit.py`, `product/identity_audit.py`, `product/resolution_cases.py`, `integrity.py`). Save exact IDs, provider/competition/season, status owner, source hash, current blocker, dependencies and snapshot in a task-local manifest. No new production schema/API/config or status enum is needed. Sources S1–S7/R1.
- **Dependencies/impact:** none. Enables all other tasks; expected recovered records: zero from inventory alone. Keep component records and case occurrences separate; derive cross-issue affected fixture unions by exact UUID only.
- **Tests/acceptance:** compare each grouped total with its own base population; test/review historical-vs-active and native-vs-canonical denominator handling if production reporting changes. Run `work_age`, `mapping_current`, `mapping_cases`, `fixture_resolution_active`, `current_history_scopes`, and file checks against one fresh declared snapshot per collection. Every recovery candidate must have an ID and an independently verifiable prerequisite.
- **Recovery/rollback:** inventory failure leaves operations untouched; retain partial evidence as incomplete, then retry the read-only collection. Never substitute old counts as current.

#### DS02 — P1 — Classify missing parent artifacts and approved test lineage — AUTONOMOUS

- **Issue/cohort:** I01; all 33 raw resources, 22 dataset versions and 26 model artifacts from S3, plus their 13 already-retired forecasts and four recorded evaluation retirements. Source origins for all parent rows are not yet fully established.
- **Change/approach:** trace exact IDs through dataset/model/forecast dependencies and `artifact_retirement_events`; reuse `football.retirement` and current integrity report consumers. Present all registrations plus the existing precise retirement scope. Do not omit missing parents or expand a forecast-only exclusion. Sources S3/S6/S7/R3/R4.
- **Dependencies/impact:** DS01. Exact known classification can proceed; authentic restores depend on DS20/DS21. Recovery estimate: unknown; all 13 dependent forecast exclusions must remain intact.
- **Schema/API/config:** prefer an additive distinction in existing diagnostics if a consumer needs it. No deletion, relabeling to REAL_PROVIDER, new retirement event, or changed immutable row merely to fix counts.
- **Tests/acceptance:** `tests/integration/test_artifact_retirement.py`, `test_integrity_verification.py`, and Python integrity/retirement tests. Verify the exact retirement overlap is 13/13 at baseline; all other missing registrations remain explicitly listed. Compare missing-parent sets before and after classification.
- **Recovery/rollback:** revert diagnostic code if classification is wrong; immutable registrations and existing retirements remain unchanged. New exclusions outside already approved scope go to DS19, with exact proof.

#### DS03 — P1 — Verify deployed build and schema before recovery features run — AUTONOMOUS preparation; deployment scope conditional

- **Issue/cohort:** I07/I08; operating migrations through 202610310500, three later migrations absent, 3,729 historical missing-function incidents, and current corrected code paths.
- **Change/approach:** extend the existing Go/Python recovery preflight (`go/api/internal/app/resolution_recovery.go`, `product/resolution_center.py`, existing migration tooling) to identify missing required capability and build metadata before work is queued. Reuse `GET /version` for build identity, and read-only `to_regclass`/`pg_proc` checks. Prepare/rehearse **existing** migrations 600/700/800 in an isolated, verified target if deployment is requested. Sources S2/S5/S6/R4.
- **Dependencies/impact:** DS01. No records recover solely from installing a schema. Preserve all 13 `LEGACY` routes. Existing compatibility/phase policy, and the later execution instruction, must authorize any operating deployment; do all concrete rehearsal work first if final approval is necessary.
- **Schema/API/config:** no competing migration system and no new stage switches. Return a precise unavailable-capability result through the existing error contract. Existing migrations remain unedited.
- **Tests/acceptance:** `test_resolution_files.py`, `test_resolution_parity.py`, `test_resolution_stages.py`, and `test_resolution_recovery.py` in disposable integration databases; Go resolution recovery tests. Prove clean upgrade, repeated migration application, pre-migration behavior, restored schema compatibility, and unchanged legacy routes. `current_functions` must show the already deployed reconciliation signatures; do not reimplement them.
- **Recovery/rollback:** no operating changes until prepared. Prefer restore/revert of an isolated rehearsal; an operating rollback must follow tested compatibility and backup procedures, preserve new evidence, and never force a stage switch.

### Phase 2 — Data acquisition and retained-source recovery

#### DS04 — P0 — Verify source-specific acquisition and retention permissions — RESEARCH_DEPENDENT

- **Issue/cohort:** I15; FotMob, PitchAPI, external prediction sources, and any proposed FBref/Sofascore/other alternative. Technical availability and zero missing files do not prove permission.
- **Change/approach:** inspect existing exact owner/retention decisions and current provider terms/account rights; reconcile FotMob's 2026-10-22 text with any applicable written permission. Record source, version/date, permitted activity, retention, request budget and restrictions using existing provider capability/acceptance mechanisms. Use pinned Reep/OpenFootball downloads only within their actual licence and evidence role. Sources R7–R15.
- **Dependencies/impact:** DS01; DS18 only where rights/spend cannot be established. Expected new datasets: unknown. Research may proceed without calling provider data endpoints or contacting anyone.
- **Schema/API/config:** use existing source/capability/access fields; avoid a new licensing subsystem. Do not silently enable disabled sources, broaden budgets, switch accounts, bypass a challenge, or treat a technical flag as consent.
- **Tests/acceptance:** provider capability/acceptance and credential/runtime-policy tests; prove blocked/disallowed sources make zero outbound data requests. Each acquisition candidate needs a current source permission reference and exact permitted scope. Missing permission remains a blocker.
- **Recovery/rollback:** no acquired bytes during permission research. If a later access configuration is changed, retain its original value and stop only the affected new route on failed preflight; do not delete retained source evidence.

#### DS05 — P1 — Plan quota and history scheduling from actual deployment evidence — AUTONOMOUS diagnostics; acquisition conditional

- **Issue/cohort:** I05/I06; 495 quota-wait jobs, local disabled history scheduler, 873 untouched provider scopes, 11 live-priority deferrals. Sources S2/S5/R9/R11/R12.
- **Change/approach:** verify effective running configuration through existing Admin diagnostics/build metadata without exposing credentials; compare it with the listed local nonsecret settings. Reuse `PostgresApiFootballBudget`, `product/history_requests.py`, `product/provider_history_scopes.py`, `product/history_work.py`, and existing provider request budgets. Reserve live vs history capacity using current policy; record why zero historical requests were used rather than guessing.
- **Dependencies/impact:** DS01, DS04 for any outbound request, DS14 before retry execution. Recovery estimate unknown; classify all 495 quota waits and 11 provider-scope deferrals with a real next condition.
- **Schema/API/config:** existing flags/cadence/quotas only; no paid upgrade or increased ceiling without DS18. No new environment variables are presently justified. If later justified, update `.env.example` and the local `.env` together while preserving every existing value and never committing `.env`.
- **Tests/acceptance:** API budget/history scope/work integration tests; daily reset, cooldown, minute cap, live reservation, starvation, cancellation, restart and fencing coverage. `budgets`, `work_age`, `history_last_runs` and scope cohorts must explain due-but-unclaimable items. Budget exhaustion must not cause repeated provider calls or false success.
- **Recovery/rollback:** revert an authorized scheduling change to its saved values if load or live freshness regresses. Preserve reservations/attempts already legitimately used; do not refund or reset counters by hand.

#### DS06 — P1 — Recover permitted provider-history scopes in evidence-backed batches — RESEARCH_DEPENDENT

- **Issue/cohort:** I06; 239 FotMob identity-blocked, 95 partial/error, four parser/replay/list failures, 873 unattempted and 11 deferred provider scopes; seven missing-fixture refresh resources and two PitchAPI detail failures. Cohorts overlap shared work.
- **Change/approach:** inspect each failed scope's retained `source_snapshot_id`, summary and resource hashes. Reuse `OperationalProviderSync.backfill_league_response`, `provider_history_scopes.py:478`, existing snapshot replay and the scope/shared-work binding. Collect new data only for genuinely missing resources after permission/plan checks; preserve original season labels, including non-calendar labels. Sources S2/S5/R7–R12.
- **Dependencies/impact:** DS03, DS04, DS05, DS14; DS07/DS08 for identity-blocked scopes; DS13 for lifecycle conflicts. Expected recovered scope count unknown; record recoverable, unavailable, ambiguous and externally blocked subsets before execution.
- **Schema/API/config:** existing storage and normalizers. New parser mappings only if exact source proof demonstrates a current gap; no silent empty-list success for a malformed response.
- **Tests/acceptance:** `python/football/tests/test_provider_history_replay.py`, `test_operational_provider_sync_seasons.py`, `test_provider_seasons.py`, plus integration history/provider-work/operational-sync tests. Twice-run selected scope must retain identical source/normalized identities, produce no duplicate canonical facts, and report complete vs partial recovery honestly. Verify `scope_errors`, `history_scope_discovery` and fresh coverage per competition-season.
- **Recovery/rollback:** abort a failed batch, retain its authentic bytes and failed receipt, and resume by exact scope/version through normal claims. Never reset all scopes to PENDING or overwrite immutable snapshots.

### Phase 3 — Data integrity

#### DS07 — P0 — Prepare exact entity-identity proposals and apply only already authorized deterministic admissions — RESEARCH_DEPENDENT

- **Issue/cohort:** I03; 5,056 active unadmitted mappings, including 108 contradictory and one revoked. R02-M has zero valid review-ready proposals for its 21 StatsBomb owner mappings.
- **Change/approach:** use `product/identity_admission.py`, `identity_trust.py`, `identity_correction.py`, `crosswalk_resolution.py`, `resolution_identity.py`, and the existing Reep adapter for candidate discovery. Group by exact provider/native ID, country/competition/season and accepted target anchor; retain original resource hashes. Produce valid existing Resolution Center previews before asking for adjudication. Sources S4/R5/R8/R13.
- **Dependencies/impact:** DS01/DS04; DS09 for a case depending on uncertain manifest meaning; DS19 only for a real qualified ambiguous/policy decision. Do not ask the owner to bless unsupported candidates. Unknown recoverable subset; fresh audit must still expose all unresolved cases.
- **Schema/API/config:** no new crosswalk table or trust algorithm. Existing automatic, source-complete rules can run when authorized; operator-approved actions must use the actual existing authenticated workflow and recorded approval, never a fabricated `owner:` actor or `approved=true` claim.
- **Tests/acceptance:** Python identity/trust/retained-source/crosswalk tests and integration identity history/correction/Resolution Center suites. Include same names/different entities, provider namespace, UUID origin mismatch, changed sources, revoked mapping, historical knowledge and contradictory groups. Every newly trusted mapping must have exact source-to-target proof; no new unsafe group or old cutoff change.
- **Recovery/rollback:** retract through existing append-only correction/revocation workflows with prospective knowledge time if a new decision is invalid. Preserve old evidence and UUID identities; never mutate historical admissions.

#### DS08 — P0 — Recover exact fixture mappings and season/schedule conflicts — RESEARCH_DEPENDENT

- **Issue/cohort:** I04; 47,293 latest native reviews, 531 contradictory native mappings, 62,290 provisional product fixtures and active ambiguity/schedule quarantines. These are overlapping sets, not a combined backlog.
- **Change/approach:** reuse `product/fixture_crosswalk_review.py`, `product/resolution_recovery.py`, `history/fixture_identity.py` and existing scoped `reconcile_unknown_season_fixtures(uuid[])`. Bind accepted teams/competition, original provider match ID, season, orientation and kickoff. Apply only existing exact authorized rules; prepare qualified cases for DS19 where required. Sources S2/S6/R8/R9.
- **Dependencies/impact:** DS07 and DS03 as needed. Unresolved result/time disagreement stays quarantined; safe identity-only work must not depend on forcing a lifecycle result. DS13 reconciles status after identity proof. Recoverable count unknown. Batch by shared verified entity/season evidence and active member IDs, never name similarity or score coincidence.
- **Schema/API/config:** reuse current recovery work/targets/results and ingestion guards; no new fixture identity mechanism or conflict-table truncation.
- **Tests/acceptance:** fixture identity/crosswalk and integration resolution recovery/batches/identity guard suites, with reversal, duplicate members, missing/ambiguous seasons, geography, same-team/same-kickoff conflict, and idempotent replay. Compare active member and unique canonical counts, verify native-key uniqueness and unchanged real-fixture IDs. A retired duplicate is not an extra recovered match.
- **Recovery/rollback:** prospective append-only correction and supported scoped invalidation/rebuild; leave contested members quarantined. Never remove the history ingestion guard.

#### DS09 — P1 — Reconcile legacy manifest meaning and frozen parser lifecycle claims — RESEARCH_DEPENDENT

- **Issue/cohort:** I02; 48 legacy manifest checksum mismatches, one additional missing OpenFootball manifest, and two UK pending resource rows. Resource bytes already verify.
- **Change/approach:** inspect the original acquisition/publication contract and Git history for each registration shape. Reuse `product/historical_manifest.py`, `historical_backfill.py`, `identity_admission.py:561`, and existing source-registration publishers. Determine whether a direct physical hash comparison is applicable; any new wrapper must independently preserve exact source bytes and old identity. Sources S3/S4/R3/R4/R7/R8.
- **Dependencies/impact:** DS02; DS04 only if new acquisition is actually needed. Possible recovery is improved lineage/interpretation, not 48 newly restored football datasets. No new source known-time claims without proof.
- **Schema/API/config:** prefer existing versioned wrapper registrations; a migration is justified only if the proven contract cannot represent a required compatible correction. Do not edit registered hashes, pending rows or acceptance evidence simply to match current bytes.
- **Tests/acceptance:** historical manifest, retained identity, canonical ingestion, immutable source/registration and integrity integration tests. Include logical-vs-physical hash, legacy ZIP path, frozen bundle, missing manifest, mismatched resource, symlink/path escape, duplicate source entry and repeated publication. All raw verified sets remain intact; new entries explain their contract and knowledge times.
- **Recovery/rollback:** discard only unregistered invalid candidate outputs according to existing storage policy; keep old registrations and source bytes. If interpretation stays uncertain, report it explicitly and perform no replacement.

#### DS10 — P1 — Qualify player identity and exposure only where exact evidence exists — RESEARCH_DEPENDENT

- **Issue/cohort:** I11; 14 insufficient-player market families, 1,240 mapping claims, source-native/participation populations and zero qualified pilot minute exposures.
- **Change/approach:** reuse `scripts/inspect_v4_pilot.py:305`, `providers/normalization/participants.py`, `contracts/observations_v3.py`, identity owners and R02-L evidence. Inspect native player IDs, exact fixture/team identity, lineup confirmation, starting/substitute/bench roles, reported period minutes, and independently supported membership/time evidence. Source candidates are R5/R9/R11/R12/R13; their rights and field coverage must first pass.
- **Dependencies/impact:** DS07/DS08/DS04 and the existing exact market/observation target contracts. No scientific model or broad player-membership architecture is authorized by this task. Recoverable players/minutes unknown; keep source-native and canonical populations distinct.
- **Schema/API/config:** current observation/coverage/qualification contracts first. Add no continuous-membership abstraction merely to turn nulls into values.
- **Tests/acceptance:** `tests/test_qualification_audit.py`, `test_v4_accepted_history_audit.py`, normalization/native identity tests, and applicable isolated market coverage tests. Prove unknown role/minutes stay unknown, bench is not appearance, interrupted/extra-time periods are distinct, two-team conflicts remain explicit, and knowledge is not backdated. Every qualified player input has complete identity/fixture/period/exposure evidence.
- **Recovery/rollback:** withdraw new derived qualification through existing immutable correction/supersession, leaving source observations intact. Unavailable minutes do not become 0 or 90.

#### DS11 — P1 — Investigate each quality rule with exact source/version evidence — RESEARCH_DEPENDENT

- **Issue/cohort:** I12; six rule groups, 2,184 findings, 38 quarantined match/resource IDs, plus the independently named synthetic score conflict.
- **Change/approach:** use `validation/statsbomb.py`, the checked-in quality policy, existing event/lineup normalizers and quarantine/conflict reprocessing. Group by rule/source spec/provider event type; compare exact retained examples against the applicable pinned official specification. Correct only proved parser/mapping defects; source inconsistencies remain findings. Sources S2/R5/R6/R7.
- **Dependencies/impact:** DS02 for synthetic-vs-real classification and DS04 for replacement acquisition. Unknown recoverable subset; do not promise all warnings can be removed.
- **Schema/API/config:** no weakened severity, skipped validation, widened bounds or changed frozen thresholds. A supported schema/mapping extension uses the repository's existing versioning rules.
- **Tests/acceptance:** `test_statsbomb_validation.py`, `test_statsbomb_event_normalization.py`, quarantine/conflict storage and canonical ingestion integration suites. Each changed rule needs a failing retained-case regression plus malformed/boundary/control cases. Recheck per-rule distinct resource/entity denominators and downstream temporal/spatial exclusions; synthetic conflict remains identifiable.
- **Recovery/rollback:** revert an incorrect parser/version, retain new attempted artifacts as failed evidence, and continue using prior eligible outputs. Never overwrite raw events or invent a corrected score.

#### DS12 — P1 — Recover exact external prediction bindings and supported settlements — RESEARCH_DEPENDENT

- **Issue/cohort:** I13; 1,250 unmatched, seven ambiguous, 1,280 current pending settlements, and computed comparison states. Original dates currently have no measured mismatch cohort.
- **Change/approach:** reuse `product/external_predictions.py`, `external_prediction_recovery.py`, existing captures/bindings/date reviews and effective/current result views. Batch by exact native fixture evidence and reviewed dates; only compare an original prior forecast when it actually exists. Sources S2/R9/R14 plus exact source terms from DS04.
- **Dependencies/impact:** DS04/DS07/DS08/DS13. Send genuinely ambiguous qualified proposals to DS19; DS21 applies any later approved binding. Recovery count unknown; a verified unique binding can still have a legitimately pending result or no supported forecast.
- **Schema/API/config:** existing append-only stores and Go projection contract. No fuzzy match, new scraper, retrospective prediction or new settlement market.
- **Tests/acceptance:** `test_external_prediction_recovery.py`, resolution/identity/date-review integration suites and Go external prediction/read-report tests. Cover duplicate revisions, stale preview, ambiguous dates, reversed teams, postponed/awarded/AET/shootout results, unsupported selections and missing pre-match forecast. Repeated settlement produces no duplicate semantic revision; current WON/LOST/PENDING totals match exact evidence.
- **Recovery/rollback:** append a correction/revocation through the existing binding/review contract. Preserve old predictions/captures and results; ambiguous cases remain unresolved.

#### DS13 — P1 — Investigate stale lifecycle and recurrent result conflicts — RESEARCH_DEPENDENT

- **Issue/cohort:** I14; 41 old LIVE, one future LIVE and 1,611 old SCHEDULED fixtures at S6/S7; 1,845 conflict events, including 1,835 over ten FotMob fixture IDs.
- **Change/approach:** compare exact retained provider revisions, timestamps, period/elapsed and score basis, accepted identity and transition guards in `product/operational_provider_sync.py`, `history/fixture_identity.py` and existing source-result conflict handling. Trace any wrong classification upstream before changing transitions. Sources S6/S7/R9/R12.
- **Dependencies/impact:** DS07/DS08 where identity is unresolved, DS04 before new fetches. Recoverable count unknown; the age bucket identifies investigation candidates, not final outcomes.
- **Schema/API/config:** existing status enum and guard first; add a supported provider mapping only with evidence. No blanket finalization, invented result, clock-based score, provider precedence change or silent conflict exclusion.
- **Tests/acceptance:** operational provider sync/normalization and fixture identity integration tests. Include delayed results, reschedule, interrupted/awarded/cancelled states, AET vs regulation, older correction arrival, future kickoff, conflicting providers and idempotent reconciliation. Each changed conclusion is traceable to the exact authentic revision, and no conflict recurs without new evidence.
- **Recovery/rollback:** append corrected conclusions through existing time/identity mechanisms; retain original source observation and conflict event. Revert a bad transition rule, never erase contradictory history.

### Phase 4 — Pipeline reliability

#### DS14 — P1 — Stop deterministic failures from consuming endless retry attempts — AUTONOMOUS

- **Issue/cohort:** I05; blanket catch at `product/sync.py:758`, 11 identity-error retries and 495 exhausted-quota waits, plus provider-scope priority deferrals. Sources S2/R2/R9.
- **Change/approach:** classify at the existing shared history failure adapter, not in a duplicate scheduler. Use current `RetryClassification`, `WorkRegistry.fail`, history work projection and SQL error contracts. Distinguish known identity guard, transient database/network failures, quota cooldown, unsupported/malformed input and lease loss. Pass proven cooldown/availability evidence through existing arguments; do not label unknown integrity errors transient by default.
- **Dependencies/impact:** DS01/DS05; implement before DS06/DS21 replay. All waiting items gain accurate reasons and next conditions; recovered records remain unknown until their blockers clear.
- **Schema/API/config:** existing states/classification fields suffice unless inspection proves otherwise. Prefer no migration or environment change. Preserve original terminal operation rows, attempt histories, leases and cancellation intent.
- **Tests/acceptance:** focused failing test for repeated identity `RaiseException`; unit and integration history/work orchestration tests for serialization/deadlock/connection retry, deterministic guard blocking, provider quota/cooldown and cancellation/lease revocation. Repeated scheduling without changed identity must create no new identical retry attempt; valid changed evidence must permit a correctly owned normal attempt. `work_errors` and queue/domain projections must agree.
- **Recovery/rollback:** revert classifier code if a supported transient path regresses; keep truthful recorded attempts and restore scheduling through current owner APIs. No direct SQL state reset or increased attempt ceiling.

#### DS15 — P1 — Expose original failure causes and verify existing lifecycle fixes — AUTONOMOUS

- **Issue/cohort:** I08; 2,123 generic failures lacking `summary.errors`, saved NameError/inverted-season/missing-function cases, lease/fence/transport failures. Current source already fixes the named code/schema defects.
- **Change/approach:** extend existing `go/api/internal/app/admin_sync.go`, `product/cli.py`, operational sync summaries and structured logs only where the real cause is lost. Preserve structured source, operation, phase, exception/code, request/run correlation and original log path; redact keys/URLs containing credentials. Verify build/schema first, then test retained failure inputs in isolation. Sources S2/S5/log samples/R12.
- **Dependencies/impact:** DS03; DS14 for meaningful retry labels. Expected recovery unknown; this task should not duplicate the existing season/fixture fixes or rewrite historical failed summaries.
- **Schema/API/config:** reuse summary/log fields; compatible additional fields only with current consumers. No new logging service or unbounded payload capture.
- **Tests/acceptance:** Python product sync/operational provider tests and Go admin sync tests; malformed/inverted seasons remain flagged, hashing receives fixture ID, current reconciliation signature is callable, partial errors remain visible, secret strings never appear. A test must prove a new generic failure retains its original specific cause even when the process wrapper reports nonzero exit.
- **Recovery/rollback:** revert added diagnostics if contract consumers break; existing logs/failed runs remain readable. Replay only selected authorized cases after their causes are removed, via DS21.

#### DS16 — P1 — Drain and measure the existing public-report backlog — AUTONOMOUS within current worker bounds

- **Issue/cohort:** I09; 176,903 pending context generations, seven performance generations at S2, no pending forecast/comparison generation cohort in that snapshot.
- **Change/approach:** reuse `product/public_reports.py:279` and Go's existing public report runner; first measure per-tick service, new generations, oldest age, errors and busy scopes. Inspect deduplication/source-fingerprint reuse before changing batch limits. Preserve the current half-oldest/half-relevant selection; the code already implements it. Sources S2/R2/R3.
- **Dependencies/impact:** DS01/DS03; source-dependent bad records wait for DS08/DS13. Recovery target is all **eligible selected** generations; baseline backlog is not a guaranteed final number. Existing bounds are a safe initial replay; broader capacity/SLO changes require measured justification and scope review.
- **Schema/API/config:** existing worklists, work metrics and immutable reports; no forced completed generations or new queue. A limit change is unnecessary unless measurements demonstrate a current need.
- **Tests/acceptance:** `test_public_reports.py` in Python/integration plus Go read-report scheduling tests. Cover starvation, live relevance, failures rotating, stale generation, worker loss, identical retry and concurrent updates. Require no eligible oldest item starvation, no false completion, stable hashes on repeated input and a documented net completion/arrival rate. Query both generation gap and serving freshness.
- **Recovery/rollback:** stop the controlled run through normal cancellation/shutdown if load or live freshness regresses. Roll back only tuning/config if introduced; retain valid reports and unfinished generation metadata.

#### DS17 — P2 — Replace fabricated health measurements with actual scoped evidence — AUTONOMOUS

- **Issue/cohort:** I16; hardcoded circuit CLOSED, unsupported zero metrics, and serving statuses computed outside report JSON. Sources S5/S6/R1/R2.
- **Change/approach:** inspect `providers/observability_store.py`, `observability.py`, existing work metrics, `go/api/internal/app/performance_store.go`, `read_reports.go` and external prediction projection. Distinguish measured zero, unmeasured, stale and scope-unavailable. Derive existing statuses using their actual owner predicates; only add a metric with a current consumer and stable contract semantics.
- **Dependencies/impact:** DS01/DS15, DS14 for accurate failure reasons. No direct data recovery estimate; acceptance is truthful diagnostics and effective monitoring.
- **Schema/API/config:** preserve published response contracts or add a versioned compatible optional measurement state when a real consumer requires it. No competing status service/datastore; do not silently break `CircuitStateV1` by assigning an invented label.
- **Tests/acceptance:** provider observability unit/integration tests and Go report decoders. A failed/unmeasured scope cannot display a measured healthy circuit/zero failure merely because data is absent. Current vs historical and empty vs pending reports remain distinguishable; malformed JSON/digest still fails validation.
- **Recovery/rollback:** revert the diagnostic change on compatibility failure; preserve existing operational state and metrics. Keep the limitation explicitly documented until a supported measurement exists.

### Phase 5 — Human decisions and unavailable dependencies

#### DS18 — P0 — Resolve exact source permission or budget choices — HUMAN_DECISION

- **Issue/cohort:** I15/I05; specific provider routes for which DS04/DS05 cannot establish rights or approved capacity. This is not permission to ask the owner about routine retries or parser choices.
- **Action/location:** present the concrete permission evidence and affected cohorts through the existing owner/capability process. Options: supply an applicable licence/consent, retain a blocked acquisition route, choose an already permitted source, or approve a quoted plan/request budget. Sources R7/R10/R12/R14/R15. Do not contact providers without explicit messaging authorization.
- **Dependencies/impact:** DS04/DS05 must first complete all independent research and prepare exact options; unknown recovery count. No schema/API/code change is inherently required by the decision.
- **Acceptance/tests:** a recorded exact activity/scope/budget decision and verified source rights; provider no-request gates pass before any acquisition resumes. Owner approval alone cannot override third-party restrictions.
- **Recovery/rollback:** keep affected acquisition blocked if evidence or approval is absent. Preserve all existing retained data and prior decisions; spend is not automatically authorized.

#### DS19 — P0 — Adjudicate only genuinely qualified ambiguous or policy-dependent cases — HUMAN_DECISION

- **Issue/cohort:** I01/I03/I04/I12/I13; exact cases DS02/DS07/DS08/DS11/DS12 prove cannot be resolved under approved deterministic rules. No current number of valid proposals is asserted; the bounded R02-M set currently has zero.
- **Action/location:** prepare an evidence-complete existing Resolution Center proposal/batch with exact IDs, source/target evidence, preview hash, consequences and rollback. A case without proof remains a research/evidence gap, not an owner choice to invent a relationship. Any proposal to broaden a test-only exclusion requires its precise affected parent/dependent IDs and preserved raw inventory.
- **Dependencies/impact:** completed technical proposal work; unknown recoverable subset. Use existing authenticated review events, approvals, corrections and immutable decisions; no parallel approval log or fabricated owner actor.
- **Acceptance/tests:** operator approves/rejects a concrete valid preview through the existing workflow; revalidate freshness, uniqueness and all integrity guards at apply time. Existing batch/identity/retirement tests and exact downstream verification apply. Do not ask to reopen a failed scientific route under a data-cleanup task.
- **Recovery/rollback:** preserve rejection/defer reasons; append supported correction/revocation if a newly approved decision later proves wrong. Retain old lineage and frozen cutoffs.

#### DS20 — P1 — Obtain authentic missing originals or retain an honest unavailable disposition — EXTERNAL_BLOCKER where originals cannot be found

- **Issue/cohort:** I01/I02; only registrations DS02/DS09 establish need authentic restoration outside current retained files. Do not assume all 33 sentinel-hash resources are real recoverable provider data.
- **Action/location:** search already authorized backup/source locations by expected byte count and SHA-256, using existing integrity/file-recovery machinery. Reuse the prior no-match evidence, then inspect genuinely new locations rather than repeat broad scans. Ask for a correct locator or exact original only after that work is exhausted; any destructive retention choice goes to DS19. Sources S3/R4.
- **Dependencies/impact:** DS02/DS09; DS04 before any new provider acquisition. Expected authentic matches currently unknown; zero guaranteed. A changed current provider response cannot stand in for missing original bytes.
- **Schema/API/config:** no new fallback source or published artifact identity. Existing file-recovery plan compares exact hash/size/path and fails closed.
- **Tests/acceptance:** exact-byte restore/symlink/path/mismatch/idempotency tests in integrity/resolution-file suites. A missing file is recovered only when the original registration verifies; otherwise the report records unavailable/ambiguous/irrecoverable-with-reason without a healthy transition.
- **Recovery/rollback:** reject mismatched candidates and retain failed verification evidence. Do not overwrite an existing path or substitute a regenerated manifest with a different digest.

### Phase 6 — Reprocessing and verification

#### DS21 — P1 — Reprocess only cohorts whose upstream evidence and execution prerequisites pass — AUTONOMOUS for approved, evidence-complete cohorts

- **Issue/cohort:** successful prerequisites across I01–I14, not every unresolved record. Start with a small exact eligible cohort from the DS01 manifest; batch by shared cause/provider/competition-season, then expand only after demonstrated convergence.
- **Action/location:** use existing source/dataset/model-file restoration where exact originals exist, normalizers, identity/fixture reconciliation, canonical resolution/coverage owners, history work adapters, external settlement and public-report workers. Changes create new immutable artifacts/versions as required. Register through normal transactions with fencing, scoped locks and dependency invalidation; never update statuses independently of verified publication. Sources R2/R3/R4 and the task-specific source references above.
- **Dependencies:** DS02–DS17 only as applicable to the cohort; DS18–DS20 for that cohort's real unresolved prerequisite. Their unresolved cases do not prevent independent eligible cohorts from completing. DS07/DS08/DS12 prepare any required manual proposals; DS19 adjudicates them; DS21 applies the subsequently authorized action. Proposal preparation does not depend on prior adjudication. Do not begin model fitting, new science, protected evaluations, promotion or cutover.
- **Schema/API/config/impact:** no extra schema/API/config assumed. All actual changes must have a current consumer and existing contract reason. Recovered count is the measured exact output set; record unrecoverable/ambiguous/unavailable subsets separately, along with unchanged legitimate no-data states.
- **Tests/acceptance:** domain unit/integration/regression checks from predecessor tasks; crash/retry/resume, cancellation, source correction, duplicate semantic work, historical cutoffs and concurrent generation tests. Replay every selected immutable input twice; prove stable logical output/hash, no duplicate canonical facts, no backdating, correct status/coverage transitions and preserved raw source/published artifacts. Count affected UUID unions separately from attempts and status occurrences.
- **Recovery/rollback:** normal transaction rollback before publication; after publication retain immutable bytes and append a supported correction/supersession or restore routing/config through existing controls. Never delete valid earlier forecasts or overwrite raw bytes. A failed batch remains resumable at its exact cursor/input hash.

#### DS22 — P0 — Verify downstream integrity, report actual outcomes, and stop at the owner handoff — AUTONOMOUS

- **Issue/cohort:** I16/I17 and every executed task; untouched blocked cases remain part of the final accounting. Scope includes canonical records, history eligibility, coverage, work/domain projections, public reports, APIs and existing published forecast behavior.
- **Action/location:** rerun DS01 queries with named before/after cohorts, current file/identity audits, domain acceptance and existing parity checks only where authorized. Update this report and `CURRENT_TASK_STATUS.md` with actual receipts, completed IDs, changed denominators, verified recoveries, remaining unavailable/ambiguous/external cases and monitoring instructions. Update project status only if an independently authorized status transition actually occurred; preserve old evidence and gates. Sources S1–S7/R1/R4.
- **Dependencies/impact:** DS21 for executed cohorts; no requirement to invent evidence to close DS18–DS20. Recovery count is observed, never a completion quota. A report may finish with legitimate blockers; it may not call the whole programme or a phase complete when its acceptance is unmet.
- **Schema/API/config:** none beyond approved predecessor changes. Keep the champion hash, protected targets, historical registrations and production route unchanged unless separately authorized by their owning process.
- **Tests/acceptance:** inspect Makefile once and run focused checks during development. After final code changes run comprehensive verification **once** as `make check integration` using the documented disposable integration setup; do not separately repeat its covered targets. Add required leakage/identity/immutability and per-domain checks not covered by the aggregate. A prose-only report update needs prose review and `git diff --check`, not code checks. Record real exit codes, logs, limitations and final diff/status; required PR delivery follows `docs/git-delivery.md` for implementation.
- **Recovery/rollback:** failed verification leaves affected task incomplete; restore only through its documented safe path, retain every failure receipt and continue independent work. Do not mark success merely because error counts fell. Return control to the owner without starting another map, route, phase, science task or cutover.

## G. Human decision register

These are conditional decisions after technical preparation, not questions that block this audit. Work on independent autonomous tasks should continue. Paths such as `product/...`, `providers/...`, `contracts/...`, `coverage/...` and `history/...` in C–K are relative to `python/football/src/football/`; Go paths are repository-relative. No unimplemented filename is prescribed.

| Issue / task | Decision required | Evidence | Available options | Recommended choice | Consequences |
| --- | --- | --- | --- | --- | --- |
| I15 / DS18 | Applicable source permission where published restrictions conflict with proposed acquisition | FotMob terms dated 2026-10-22; enabled local config; no account-specific permission inspected; other exact source gaps in D | Supply existing applicable written permission; obtain permission separately; use an already permitted alternative; retain the route's acquisition blocker | Verify an actual applicable right before any additional acquisition; prepare exact permitted alternatives first | May reduce new coverage; no automatic deletion or rewriting of retained bytes. Owner approval does not replace provider permission. |
| I05 / DS18 | Additional paid capacity or expanded authorized request budget, **only if needed after scheduling/replay work** | 495 quota-wait jobs; budget exhausted with zero historical allocation in S2; no plan quote collected | Retain budget and deferred state; reallocate within an already approved policy; approve a concrete quoted plan/scope | Use retained recovery and existing permitted capacity first; escalate only a documented capacity shortfall | No automatic purchase, account multiplication, quota bypass or promised recovery date. |
| I03/I04/I13 / DS19 | A specific identity/fixture/prediction relation that remains genuinely ambiguous or requires an explicit operator decision | Exact independent candidate evidence and a valid fresh existing Resolution Center preview must be prepared first; the R02-M 21-mapping pilot currently has zero such proposals | Approve the evidenced relation; reject a contradicted relation; defer unresolved candidates | Submit only evidence-complete proposals; keep uncertain cases quarantined | Trust/canonical changes require the established authenticated workflow and downstream checks. No request to guess a source relationship. |
| I01/I02 / DS19/DS20 | Accepting a newly justified exclusion/disposition beyond an already approved scope, or any irreversible retention change | Missing originals plus exact parent/dependent IDs; existing events exclude 13 synthetic forecasts and four evaluations, not all parents | Preserve explicit unavailable state; recover authentic originals; approve a narrowly justified prospective disposition | Preserve evidence and apply only existing exact exclusions unless a concrete new decision is necessary | A disposition cannot make missing bytes verify or establish full parity. No broad gate exemption, deletion or new “resolved” label by default. |

No owner decision is required to read evidence, fix an authorized reversible parser/retry/diagnostic bug, prepare valid proposals, run disposable tests, or verify idempotency. New model research, protected evaluation, promotion, architecture cutover and scheduler retirement remain outside this roadmap's autonomous scope; their existing authorization requirements are unchanged.

## H. Prevention and architectural improvements

Use the existing owners; implement only measured gaps that a roadmap task requires.

| Pattern | Owner/layer | Concrete prevention | Guard against recurrence |
| --- | --- | --- | --- |
| Synthetic registrations counted as real lost data | Existing integrity/retirement reporting and test setup | Trace exact provenance and approved retirement scope; keep raw and effective diagnostic populations separately visible | Test generated provider/sentinel fixture rows remain attributable; isolated integration targets cannot silently select operations |
| Logical manifest ID confused with file SHA | Source registration / historical manifest reader | Validate the exact registration version; preserve legacy interpretation and immutable wrapper lineage | Legacy ZIP/bundle and manifest-v1 regression cases; physical mismatch never silently repaired |
| Native identifier mistaken for a canonical relationship | Existing identity/crosswalk admission owners | Require native scope, accepted target anchor and independent relation evidence; revalidate changes prospectively | Wrong UUID, same-name/different-team, source change, revoked/contradictory and historical cutoff tests |
| Provisional/duplicate fixture drives downstream work | Fixture resolution / history ingestion guard | Keep exact member/season/orientation/time proof, active resolution membership and unique real-fixture denominators | Duplicate, uncertain season, impossible schedule and concurrent recovery tests |
| Deterministic failures retry indefinitely | History worker / shared-work adapter | Classify known integrity blockers separately from transient transport/transaction failures; retry on real condition change | Attempt count stays stable under repeated unchanged blocker; quota deferral respects reset/cooldown |
| Live requests starve historical coverage | Existing provider budget/scope scheduler | Measure approved capacity and claim eligibility; reuse bounded live/history fairness | Restart and backlog tests; no unauthorized extra request, no silently unprocessed scope |
| Code feature assumed deployed | Existing migration/build preflight | Read-only capability checks before queuing recovery; clear unsupported-feature response | Old/new schema compatibility tests and exact version receipts |
| Generic failure hides upstream cause | Existing run summary and logs | Retain specific sanitized exception/provider/resource/run and original log reference | Partial-failure and redaction tests; cancellation/fence loss remain distinct from provider outage |
| Report backlog ages despite successful ticks | Existing public-report worker / work metrics | Measure generation arrivals, completions, age and selection fairness; source-fingerprint reuse | Oldest/live fairness and generation race tests; no forged completion markers |
| Rich resource mistaken for qualified market history | Coverage/semantic/model governance owners | Exact field/period/target parameters and common canonical history; separate access, coverage, research and publication | Missing fields, mismatched score basis, late knowledge, insufficient history and research-only data fail closed |
| Lineup presence becomes invented minutes/membership | Observation normalizers and existing qualification owners | Preserve role, reported period, missingness, exact player/team/fixture identity and source timing | Bench, substitute, unknown time, transfer and two-team cases cannot yield unproved exposure |
| Quality warnings disappear through relaxed rules | Existing validation policy / source parsers | Correct supported source mappings only; retain source errors and feature exclusions | Retained regressions and boundary cases with unchanged quality gates |
| Age or source preference invents a final result | Operational provider sync / fixture conflict guard | Reconcile authentic revisions and status/period/time evidence; no clock-only finalization | Delayed and corrected results, AET/shootout/awarded states and stale revision tests |
| Repeated unmatched prediction collection | Existing binding/date/settlement workflow | Reuse retained exact evidence; identify missing binding prerequisites before recollection | Ambiguous dates/identities and absent original pre-match forecast remain explicit |
| Technical success hides unverified rights | Existing provider acceptance/capability gate | Source/activity-specific permission reference and budget preflight | Disallowed/unknown acquisition produces no outbound data call; existing data is preserved |
| Health metrics use fixed CLOSED/zero | Existing provider/work/serving diagnostics | Report measured state or explicit unavailable scope using compatible contracts | Unmeasured cannot look healthy; persisted and request-time statuses are tested separately |

Alerts should use the existing configured freshness/lease/cooldown/phase contracts and exact blockers, not thresholds invented after seeing this audit. Track changes in cohorts and oldest eligible age, rather than notifying on every repeated unchanged blocked record. Any new business SLO or spending requirement needs its own explicit decision; it is unnecessary for the initial safe fixes.

## I. Verification and exit criteria

### Evidence hashes and exact reproduction

The local evidence ledger below identifies collected bytes. It is not a backup of the operating database. Detailed raw query files may contain public football identities and operational metadata and should remain under the repository's existing local-data access policy.

| Evidence file | SHA-256 |
| --- | --- |
| [`snapshot.json`](../../.local/data-status-audit/snapshot.json) | `eecf4c0cf1d68971e461ea6686884e14b68fc7933692a76ead2bae8621ea53c7` |
| [`detail.json`](../../.local/data-status-audit/detail.json) | `26a739ebb20c8679a419226d1d388803b9ae900281b16ac752d8a97b6d6345f5` |
| [`files.json`](../../.local/data-status-audit/files.json) | `1f99a1727c85e9d51132322d32d492b22c2dbd4b454f88a8d1ed5ab543bf2bb2` |
| [`identity-audit.json`](../../.local/data-status-audit/identity-audit.json) | `3ef23dc5a70243d3537576711ef692bda8138e8e5b84ef04c360037a7838ef4a` |
| [`extra.json`](../../.local/data-status-audit/extra.json) | `5e80f8a6883bb6c28eb08b645692690bfa0d0eb6c66b9ff9ad725fe01e4d5f6c` |
| [`final-queries.json`](../../.local/data-status-audit/final-queries.json) | `96c0cbd253f9f1179b96e310ce4b3cf75006b765dcb67d058cd50f7d93b700da` |
| [`safety-tail.json`](../../.local/data-status-audit/safety-tail.json) | `b94b51f15c4e3f8aabc9f66d8679d9e5054e3ca3709908fd30001e3a1e5d55fc` |
| [`status-definitions.json`](../../.local/data-status-audit/status-definitions.json) | `eda5873e69fd112376d4a7410ab64aff0c87b4f90241b233eaa0c8274b7e180c` |
| [`inventory.json`](../../.local/data-status-audit/inventory.json) | `890d5ba458eaa1602fb20fc4d6325cbe9f09ddbf194b1beed2d97b0c9adcd6c5` |

Collection commands actually executed from the repository root were `.venv/bin/python /private/tmp/matchforge_audit_{snapshot,detail,files,identity,extra,final_queries,safety_tail}.py`, individually, with read-only database access. Exact copies are retained locally as `collect-*.py`; helpers used the prefix of `matchforge_audit_detail.py` solely to load credentials safely. To reuse them after `/private/tmp` is cleared, restore those helper files first from the local collector copies. Review any collector before use, keep the explicit read-only connection/transaction settings, and write fresh evidence under a new directory if preserving the audit snapshot. An initial final-query collection failed on an incorrect `created_at` column in `artifact_retirement_events`; it rolled back, the query was corrected, and S6 is the successful completed collection. A query of the pre-control architecture shadow's absent stage-settings table was recorded as an expected version difference. No failed query was treated as a successful count.

Read-only helper invocations used existing code:

- `football.product.identity_audit.audit_report(connection, data_root)`; never `--admit-verified`.
- `football.product.resolution_data.resource_check(root, registration)` for all raw resources; `PostgresIntegrityVerifier.dataset_file_checks`, `verify_model_artifact`, and registered observation/capability file hashes.
- `football.providers.data_audit.audit_provider_data(connection, data_root=...)` for actual field/provider/player statistics.
- `football.product.market_capability_cli.market_capability_report` followed by its summary for the exact scope in B; no forecast fit, publish or promotion.

The following exact collected SQL statements support the nontrivial cohorts and can be rerun inside a declared read-only repeatable-read session. JSON evidence retains their result rows and any parameters. Identifier lists for missing models/datasets come from exact S3 failures, not hand-entered guessed IDs.

<details>
<summary>Collected issue, latest-state, and verification queries</summary>

**detail.json / work_errors**

```sql
SELECT work_type,state,last_error_code,left(last_error_message,500),count(*),min(requested_at),max(requested_at) FROM football.work_items WHERE state<>'SUCCEEDED' GROUP BY 1,2,3,4 ORDER BY count(*) DESC;
```

**detail.json / work_age**

```sql
SELECT work_type,state,count(*),count(*) FILTER(WHERE lease_until<transaction_timestamp()),count(*) FILTER(WHERE available_at<transaction_timestamp()),min(available_at),max(available_at),max(attempt_count),min(max_attempts) FROM football.work_items GROUP BY 1,2 ORDER BY 1,2;
```

**detail.json / scope_errors**

```sql
SELECT provider_code,status,left(last_error,500),count(*),min(next_attempt_at),max(next_attempt_at),max(attempts) FROM football.product_provider_history_scopes GROUP BY 1,2,3 ORDER BY count(*) DESC;
```

**detail.json / history_queue**

```sql
SELECT job_status,left(last_error,500),count(*),min(next_attempt_at),max(next_attempt_at),max(attempt_count) FROM football.product_history_sync_queue GROUP BY 1,2 ORDER BY count(*) DESC;
```

**detail.json / budgets**

```sql
SELECT provider_code,window_date,requests_used,historical_requests_used,remaining_requests,exhausted,deferred_until,minute_remaining,last_error FROM football.provider_request_budgets ORDER BY window_date DESC,provider_code;
```

**detail.json / current_history_eligibility**

```sql
WITH latest AS (SELECT DISTINCT ON(fixture_id) * FROM football.product_match_history_decisions ORDER BY fixture_id,decided_at DESC,decision_id DESC) SELECT source_provider_code,eligible,reason,count(*),min(kickoff_at),max(kickoff_at) FROM latest GROUP BY 1,2,3 ORDER BY 1,2,3;
```

**detail.json / mapping_current**

```sql
WITH latest AS (SELECT DISTINCT ON(provider_code,provider_match_id) * FROM football.product_provider_mapping_decisions ORDER BY provider_code,provider_match_id,observed_at DESC,decision_id DESC) SELECT provider_code,disposition,reason,count(*),count(DISTINCT candidate_fixture_id) FROM latest GROUP BY 1,2,3 ORDER BY 1,2,3;
```

**detail.json / identity_current**

```sql
WITH latest AS (SELECT DISTINCT ON(entity_type,mapping_id) * FROM football.product_identity_admissions ORDER BY entity_type,mapping_id,decided_at DESC,decision_id DESC) SELECT entity_type,provider_code,disposition,reason,football.product_mapping_trusted(entity_type,mapping_id,canonical_id),count(*) FROM latest GROUP BY 1,2,3,4,5 ORDER BY 1,2,3,4,5;
```

**detail.json / fixture_resolution_active**

```sql
SELECT active,resolution_status,resolution_reason,count(*),count(DISTINCT member_fixture_id) FROM football.fixture_identity_resolutions GROUP BY 1,2,3 ORDER BY 1,2,3;
```

**detail.json / forecast_work**

```sql
SELECT count(*),count(*) FILTER(WHERE generation>completed_generation),min(requested_at) FILTER(WHERE generation>completed_generation),max(requested_at) FROM football.product_forecast_refresh_work;
```

**detail.json / report_work**

```sql
SELECT report_kind,count(*),count(*) FILTER(WHERE generation>completed_generation),left(last_error,500),min(requested_at) FILTER(WHERE generation>completed_generation),max(last_attempt_at) FROM football.product_report_refresh_work GROUP BY report_kind,last_error ORDER BY 1,2 DESC;
```

**detail.json / context_work**

```sql
SELECT count(*),count(*) FILTER(WHERE generation>completed_generation),left(last_error,500),min(requested_at) FILTER(WHERE generation>completed_generation),max(last_attempt_at) FROM football.product_context_report_refresh_work GROUP BY last_error ORDER BY count(*) DESC;
```

**detail.json / external_current**

```sql
SELECT ep.source_code,ep.effective_match_status,ep.date_status,coalesce(r.settlement_state,'NO_RESULT'),count(*) FROM football.external_prediction_effective ep LEFT JOIN football.external_prediction_current_results r ON r.prediction_id=ep.prediction_id GROUP BY 1,2,3,4 ORDER BY 1,2,3,4;
```

**detail.json / validation_rules**

```sql
SELECT rule_code,severity,action,scope_type,count(*),count(DISTINCT source_resource_id),count(DISTINCT provider_entity_id) FROM football.validation_findings GROUP BY 1,2,3,4 ORDER BY 1,2,3,4;
```

**detail.json / source_pending**

```sql
SELECT p.code,s.id,r.id,r.provider_path,r.sha256,r.size_bytes,r.parse_status,r.validation_status,s.manifest_path,s.source_identity,s.source_revision FROM football.source_resources r JOIN football.source_snapshots s ON s.id=r.source_snapshot_id JOIN football.providers p ON p.id=s.provider_id WHERE r.parse_status='pending' OR r.validation_status='pending';
```

**detail.json / dataset_lineage**

```sql
SELECT d.id,d.dataset_name,d.layer,d.status,d.manifest_path,d.published_at,count(DISTINCT i.source_resource_id),count(DISTINCT f.id) FROM football.dataset_versions d LEFT JOIN football.dataset_inputs i ON i.dataset_version_id=d.id LEFT JOIN football.dataset_files f ON f.dataset_version_id=d.id GROUP BY d.id ORDER BY d.published_at,d.id;
```

**extra.json / capability_fields**

```sql
SELECT p.code,r.resource_type,r.availability,r.identity_quality,r.entitlement,count(*) FROM football.provider_resource_capabilities r JOIN football.providers p ON p.id=r.provider_id GROUP BY 1,2,3,4,5 ORDER BY 1,2,3,4,5;
```

**extra.json / missing_model_inputs**

```sql
SELECT a.id,a.model_family,a.published_at,i.dataset_version_id FROM football.model_artifacts a LEFT JOIN football.model_artifact_inputs i ON i.model_artifact_id=a.id WHERE a.id=ANY(%s::uuid[]) ORDER BY a.id;
```

**extra.json / context_backlog_by_scope**

```sql
SELECT c.competition_id,c.name,m.season_id,f.status,count(*),min(w.requested_at),max(w.last_attempt_at) FROM football.product_context_report_refresh_work w JOIN football.product_fixtures f USING(fixture_id) JOIN football.product_competitions c USING(competition_id) LEFT JOIN football.matches m ON m.id=f.fixture_id WHERE w.generation>w.completed_generation GROUP BY 1,2,3,4 ORDER BY count(*) DESC;
```

**extra.json / history_scope_discovery**

```sql
SELECT provider_code,status,split_part(season_label,' - ',1),count(*),min(next_attempt_at),max(attempts) FROM football.product_provider_history_scopes GROUP BY 1,2,3 ORDER BY 1,2,3;
```

**extra.json / current_history_scopes**

```sql
WITH latest AS(SELECT DISTINCT ON(fixture_id) * FROM football.product_match_history_decisions ORDER BY fixture_id,decided_at DESC,decision_id DESC) SELECT l.source_provider_code,l.competition_id,m.season_id,l.eligible,l.reason,count(*) FROM latest l LEFT JOIN football.matches m ON m.id=l.fixture_id GROUP BY 1,2,3,4,5 ORDER BY 1,2,3,4,5;
```

**extra.json / history_last_runs**

```sql
SELECT sync_type,status,count(*),max(requested_at),max(finished_at) FROM football.product_sync_runs WHERE sync_type LIKE '%%HISTORY%%' GROUP BY 1,2 ORDER BY 1,2;
```

**final-queries.json / missing_model_forecasts**

```sql
SELECT count(DISTINCT forecast_id),count(DISTINCT model_artifact_id) FROM football.forecast_artifacts WHERE model_artifact_id=ANY(%s::uuid[]);
```

**final-queries.json / missing_dataset_forecasts**

```sql
SELECT count(*),count(DISTINCT dataset_version_id) FROM football.baseline_forecasts WHERE dataset_version_id=ANY(%s::uuid[]);
```

**final-queries.json / current_functions**

```sql
SELECT p.proname,pg_get_function_arguments(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='football' AND p.proname IN('reconcile_unknown_season_fixtures','claim_work','fail_work') ORDER BY 1,2;
```

**final-queries.json / active_resolution_unique**

```sql
SELECT resolution_status,count(*),count(DISTINCT member_fixture_id),count(DISTINCT canonical_real_fixture_id) FROM football.fixture_identity_resolutions WHERE active GROUP BY 1 ORDER BY 1;
```

**final-queries.json / live_staleness**

```sql
SELECT status,count(*),count(*) FILTER(WHERE kickoff_at<transaction_timestamp()-interval '48 hours'),min(kickoff_at),max(kickoff_at) FROM football.product_fixtures WHERE status IN('LIVE','SCHEDULED','HALF_TIME','INTERRUPTED','SUSPENDED') GROUP BY 1 ORDER BY 1;
```

**safety-tail.json / retired_dependency_overlap**

```sql
SELECT count(DISTINCT f.forecast_id),count(DISTINCT f.forecast_id) FILTER(WHERE r.id IS NOT NULL) FROM football.forecast_artifacts f LEFT JOIN football.artifact_retirement_events r ON r.object_kind='FORECAST' AND r.object_id=f.forecast_id AND r.retirement_scope='TEST_ONLY_HARD_GATE_EXCLUSION' WHERE f.model_artifact_id=ANY(%s::uuid[]);
```

**safety-tail.json / source_result_conflicts**

```sql
SELECT existing_provider_code,incoming_provider_code,count(*),count(DISTINCT canonical_match_id),min(detected_at),max(detected_at) FROM football.product_source_result_conflicts GROUP BY 1,2 ORDER BY 1,2;
```

**safety-tail.json / live_identity_scope**

```sql
SELECT f.status,f.identity_status,CASE WHEN f.kickoff_at>transaction_timestamp() THEN 'FUTURE' WHEN f.kickoff_at<transaction_timestamp()-interval '48 hours' THEN 'OLDER_THAN_48H' ELSE 'OTHER' END,count(*) FROM football.product_fixtures f WHERE f.status IN('LIVE','SCHEDULED') GROUP BY 1,2,3 ORDER BY 1,2,3;
```

</details>

### Required exit evidence for later remediation

1. **Status correctness:** every changed status resolves to a completed, validated operation or a fresh evidence-backed diagnostic. Old failures, warnings, attempts, decisions and retirements remain intact. Zero unresolved rows is not an acceptance condition.
2. **Complete accounting:** each DS01 candidate ends as verified recovered, legitimately unavailable/unsupported, ambiguous/quarantined, irrecoverable with evidence, or externally blocked. Report exact unique UUIDs separately from attempts, revisions, finding rows and scope keys; unexplained exclusions are zero. Preserve baseline counts and record concurrent additions.
3. **Integrity and provenance:** every restored original matches registered SHA-256 and byte count. New derived versions bind authentic source/input/processing versions and both physical/logical checks as applicable. Old manifests, published artifacts and source hashes are unchanged. Existing 13 forecast/four evaluation retirements keep precisely their approved scope.
4. **Identity and duplicates:** every newly admitted mapping passes the existing verifier and current trust predicate; every corrected fixture has accepted member/orientation/season/time proof. No fuzzy-only admission, fabricated source relationship, duplicate canonical fact or new unsafe shared identity group is allowed. An admitted subset cannot hide unresolved siblings.
5. **Coverage and semantics:** expected, observed and qualified units are explicit by provider/dataset/competition-season/period/target. Unknown denominators do not become 100% coverage; zero observations do not become zero-valued football statistics. Model/market readiness is recomputed with exact target inputs, compatible semantics and frozen sufficiency rules.
6. **Historical eligibility:** `football_cutoff`, `knowledge_cutoff`, `knowledge_mode`, valid/knowledge history and same-kickoff batching remain correct. Target outcomes stay absent from pre-match inputs. A current read-only inventory or retrospective label qualification is not a historical forecast dataset. Protected Sprint 2 targets and terminal routes remain untouched.
7. **Reliability:** deterministic blocked identity errors stop consuming identical retry attempts. Quota waits become claimable only after real allowed capacity exists; lease/cancellation fencing rejects stale publication. Crash/restart/retry and partial batch recovery converge on the same semantic result. No dead-letter/terminal failure is erased to reduce a counter.
8. **Serving and downstream effects:** canonical history, resource/target coverage, work/domain generations, external binding/settlement, read reports and existing APIs agree for the exact executed scopes. Reprocessing identical inputs reproduces logical outputs; expected append-only corrections retain predecessor links. Existing healthy forecast behavior and champion hash `e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4` are preserved.
9. **Reports and monitoring:** eligible backlog age/completion/arrival measurements and specific failure reasons are recorded. Unmeasured circuits and fields do not appear as measured healthy zeros. Persisted public report bytes and computed API readiness use their actual owners. Sustained load/fairness limits are evaluated against existing requirements; new business thresholds are not invented during execution.
10. **Phase discipline:** exact authorized parity/quality checks pass for claimed scopes. Partial/shadow parity is not complete production parity. No migration, route change, scientific evaluation, model promotion, protected evaluation, cutover or scheduler retirement is claimed without its separately applicable authority and evidence. Architecture V2/V4 whole-programme completion is not an exit condition this roadmap can manufacture.
11. **Engineering verification and delivery:** run the checks appropriate to the actual final diff and domain, with exact commands/exit codes/logs. Do not weaken tests, validation, typing, lint, complexity or frozen gates. Follow the repository review/delivery policy and stop at its required owner handoff.

### Verification of this audit deliverable

This audit changed prose documentation and an ignored local status tracker only. Production code, SQL, schemas, `.env`, project-status JSON and existing evidence were not edited. Therefore the repository's prose-only policy applies: review the report and references and run `git diff --check`; no `make check`, integration tests, builds, migrations or remediation are appropriate to validate prose. Read-only queries and file-verifier results above are the actual audit evidence. Historical test pass claims in referenced reports are historical evidence, not test commands run by this audit.

## J. Execution checklist

All engineering/remediation boxes are intentionally unchecked. F contains the complete implementation/rollback/test contract for each ID; C provides the corresponding root cause and I the common verification rules. Dependencies apply across workstreams. Blocked cases do not halt independent safe tasks.

- [ ] **DS01 — AUTONOMOUS:** I01–I17; F/DS01; no dependency. Freeze current ID-scoped inventory; accept only reconciled scoped totals and a complete recovery manifest.
- [ ] **DS02 — AUTONOMOUS:** I01; F/DS02; after DS01. Classify every missing parent and exact retirement relationship; accept no expanded exclusion or hidden missing registration.
- [ ] **DS03 — AUTONOMOUS preparation:** I07/I08; F/DS03; after DS01. Verify deployed build/schema and rehearse any requested existing migrations; accept compatibility evidence and unchanged legacy routes before any separately scoped deployment.
- [ ] **DS04 — RESEARCH_DEPENDENT:** I15; F/DS04; after DS01. Establish actual source/activity permission; accept a verifiable rights/scope reference or an explicit blocker.
- [ ] **DS05 — AUTONOMOUS diagnostics:** I05/I06; F/DS05; after DS01 and DS04 before acquisition. Explain capacity and effective scheduler state; accept quota-safe claim eligibility and preserved live priority.
- [ ] **DS06 — RESEARCH_DEPENDENT:** I06; F/DS06; after DS03/04/05/14 and DS07/08/13 as applicable. Recover exact permitted history cohorts; accept complete-vs-partial accounting and duplicate-free twice-run replay.
- [ ] **DS07 — RESEARCH_DEPENDENT:** I03; F/DS07; after DS01/04 and DS09 as applicable. Prepare exact relation proof and authorized admissions; accept current trust verification with no fabricated/ambiguous match.
- [ ] **DS08 — RESEARCH_DEPENDENT:** I04; F/DS08; after DS07/03 as applicable; unresolved lifecycle conclusions stay quarantined. Recover exact fixture cases; accept identity/season/orientation/time proof and preserved ingestion guards.
- [ ] **DS09 — RESEARCH_DEPENDENT:** I02; F/DS09; after DS02. Explain each legacy manifest/lifecycle case; accept immutable compatible evidence, unchanged original hashes and verified raw resources.
- [ ] **DS10 — RESEARCH_DEPENDENT:** I11; F/DS10; after DS04/07/08 and exact target prerequisites. Qualify only proved player inputs; accept explicit exposure/membership/missingness and no inferred minutes.
- [ ] **DS11 — RESEARCH_DEPENDENT:** I12; F/DS11; after DS02/04 as applicable. Resolve supported source/parser issues; accept retained-case regressions with unchanged quality gates and explicit legitimate findings.
- [ ] **DS12 — RESEARCH_DEPENDENT:** I13; F/DS12; after DS04/07/08/13; qualified manual proposals go to DS19 and later application to DS21. Recover exact bindings/settlements; accept unique valid bindings, honest pending/unsupported cases and idempotent result revisions.
- [ ] **DS13 — RESEARCH_DEPENDENT:** I14; F/DS13; after source permission and applicable identity proof. Explain stale/future lifecycle/result conflicts; accept authentic allowed transitions without clock-based final scores.
- [ ] **DS14 — AUTONOMOUS:** I05; F/DS14; after DS01/05, before replay. Correct retry classification; accept stable attempts under unchanged deterministic blockers and safe transient/cooldown recovery.
- [ ] **DS15 — AUTONOMOUS:** I08; F/DS15; after DS03/14. Preserve original sanitized failure causes and validate current fixes; accept specific new error evidence without rewriting historical failures.
- [ ] **DS16 — AUTONOMOUS within bounds:** I09; F/DS16; after DS01/03 and data repair only for affected cohorts. Drain/measure existing report worker; accept correct generation completion, fairness, output hashes and load evidence.
- [ ] **DS17 — AUTONOMOUS:** I16; F/DS17; after DS01/15/14. Make diagnostics truthful; accept measured or explicitly unavailable health without breaking existing contracts.
- [ ] **DS18 — HUMAN_DECISION:** I15/I05; F/DS18; only after DS04/05 exhaust technical research. Decide concrete permission/spend options; accept recorded exact scope and independently valid provider rights.
- [ ] **DS19 — HUMAN_DECISION:** I01/I03/I04/I12/I13; F/DS19; only after evidence-complete predecessor proposals. Adjudicate a real case or narrow new disposition; accept existing authenticated fresh-preview workflow and supported correction path.
- [ ] **DS20 — EXTERNAL_BLOCKER:** I01/I02; F/DS20; after DS02/09. Obtain authentic missing originals/locator or retain unavailable state; accept exact hash/size matches or evidence-backed explicit exceptions without false success.
- [ ] **DS21 — AUTONOMOUS for eligible approved cohorts:** I01–I14; F/DS21; all cohort-specific prerequisites first. Restore/reprocess normally; accept twice-run convergence, stable IDs, immutable lineage and measured recoveries.
- [ ] **DS22 — AUTONOMOUS:** I16/I17 and all executed tasks; F/DS22; after completed cohort work. Verify downstream behavior, update actual outcomes and deliver; accept required checks, complete accounting and preserved gates, then stop at owner handoff.

Recommended initial order: **DS01 → DS02/DS03/DS04/DS05 → DS14 → DS15**, then evidence preparation for DS07/DS09/DS11/DS13, followed by DS08/DS10/DS06/DS12 only where their own prerequisites pass. DS16 and DS17 can proceed independently when their listed prerequisites are satisfied. Resolve DS18–DS20 only for affected cohorts. End each executable cohort with DS21 and DS22 evidence. This is an ordering guide, not permission for simultaneous implementations or unrequested subagents.

## K. Ready-to-execute Codex remediation prompt

The following prompt is standalone: it refers to checked-in/local repository evidence, not this conversation. **It is for a future owner invocation. This audit does not execute it or approve unresolved actions.**

```text
You are working in /Users/radar/Desktop/football-simutation on MatchForge.

Execute the approved, evidence-complete autonomous data remediation tasks in
 docs/evidence/data-status-remediation-report.md.
Treat that report as an evidence-backed plan whose counts require refresh, not
as permission to change business requirements, historical truth, provider rights,
scientific gates, or architecture cutover. Read AGENTS.md and applicable scoped
instructions first, followed by the relevant backend/frontend, testing, model
routing, Git delivery and review guides. Use CURRENT_TASK_STATUS.md to track
actual progress. Preserve unrelated work. Use the existing checkout and an
appropriate dedicated ft/ task branch; do not spawn subagents unless separately
authorized by the owner or applicable instructions.

Start with DS01. Verify current branch, deployed build/schema, database endpoint
and role, source roots, existing owner decisions and project status. Refresh
exact read-only inventories and archive named, credential-free before evidence.
The prior audit's operating database was football, PostgreSQL 18.6, schema through
202610310500; four V4 research databases had 202610310800. Do not assume that is
still true. Keep operating, shadow, experimental, current, historical, native and
canonical populations distinct. If local receipts are unavailable, regenerate
the report's exact SQL/helper audits before making data claims.

The verified baseline showed 33 test-shaped unavailable raw resources, 22 missing
dataset manifests, 26 unverifiable model manifests, and 13 dependent forecasts
already covered by exact approved synthetic-test retirements. It also showed
4,947 actively reclassified unresolved identity mappings, 108 contradictory and
one revoked; 495 history jobs waiting on exhausted API capacity and 11 retrying a
deterministic identity guard; 873 unattempted and 338 failed provider-history
scopes; and 176,903 context generations waiting for bounded report projection.
These cohorts overlap and must not be summed. Do not reconstruct test fixtures
or rewrite old failures merely to achieve healthy counters.

Execution order and authority:
1. Complete DS01, DS02 and safe DS03 preparation. Verify current runtime fixes
   before adding code: the saved undefined-fixture_id, inverted-season and missing
   reconciliation-function incidents already had current repository corrections.
2. Complete DS04 rights research and DS05 quota/deployment diagnostics. FotMob's
   published 2026-10-22 terms restricted automated/systematic retrieval; verify any
   applicable actual permission before proposing new acquisition. Technical HTTP
   access or private use is not permission. Do not contact providers, purchase a
   plan, bypass a challenge, change accounts, or expand request budgets without
   the necessary explicit instruction and independently valid source rights.
3. Implement DS14 retry classification, then DS15 cause preservation and existing
   fix verification. Reuse current RetryClassification, work/domain adapters,
   leases, cooldowns and publication fencing. No new orchestrator or status store.
4. Progress DS07/DS09/DS11/DS13 research and evidence preparation using exact
   retained source bytes and existing identity/quality/lifecycle owners. Then
   DS08/DS10/DS06/DS12 may execute only when their cohort-specific proof and
   permissions pass. Apply existing authorized deterministic rules; prepare
   concrete valid existing Resolution Center previews for real operator decisions.
   Do not fabricate an owner actor, approval, identity or exact correspondence.
5. Progress DS16 with the existing bounded/fair report worker, and DS17 with
   existing telemetry/read-report contracts. Measure load, arrival/completion and
   oldest eligible age before tuning; the worker already reserves oldest/live
   capacity. Never set completion generations or health values by hand.
6. Execute DS21 only for exact evidence-complete, authorized cohorts. Unresolved
   DS18/DS19/DS20 cases block only their dependencies; continue independent safe
   tasks. Preserve recoverable, legitimately unavailable, ambiguous and
   irrecoverable-with-evidence categories. A changed provider response cannot
   replace missing original bytes with a different registered checksum.
7. Finish DS22 for every executed cohort, update the remediation report with real
   before/after IDs, counts, sources, hashes, actual outcomes, tests and unresolved
   exceptions, and complete applicable Git delivery. Then stop at owner handoff.

For every task:
- Inspect current consumers/code/contracts before changing anything. Use the
  smallest complete fix and existing recovery/parser/admission/publisher paths.
- Follow F's dependencies, implementation locations, record cohorts, research,
  tests, acceptance queries and rollback requirements. Additional research is
  autonomous; invented proof or policy is prohibited.
- Use focused failing tests where practical, including failure branches and
  idempotency/concurrency/historical cases. Reprocess exact inputs twice and
  verify convergence, stable semantic identities and no duplicate canonical facts.
- Preserve source bytes, hashes, mapping/fixture IDs, old decisions and correction
  history, dataset/artifact versions, forecast lineage, football_cutoff,
  knowledge_cutoff, knowledge_mode, same-kickoff rules and target-outcome sealing.
- Do not invent records, scores, player minutes, membership intervals, source
  relationships, coverage denominators, recovery estimates or provider behavior.
- Never bypass integrity checks, relax quality/identity/parity constraints, move
  frozen thresholds, hide exclusions, silently coerce unknowns, or edit a status
  to SUCCEEDED/RESOLVED/SUPPORTED without verified recovery and validation.
- Test-only retirement scope is exact. Preserve raw inventories; do not expand
  exclusions, delete historical registrations or regenerate placeholder bytes.
- Do not introduce new configuration/schema/dependencies without a demonstrated
  current consumer/contract need. If new variables are justified and added to
  .env.example, add them to local .env while preserving all existing values;
  never print credentials or commit .env.
- For operating deployment or any irreversible/destructive step, first complete
  all concrete reversible preparation and verification. Establish authorization
  from the current instruction and existing phase policy; if absent, present the
  exact final action and reason approval is required. Do not repeatedly ask for
  actions already authorized.

Validation and stopping rules:
Inspect the Makefile graph. Run focused checks during development and one
make check integration after final code changes; do not independently repeat
covered targets. Use disposable/verified isolated databases for mutating tests.
Run required domain gates and git diff --check. Prose-only changes follow the
repository's prose-only exception. Record commands actually run, exit codes and
full failure evidence. Never claim tests, recovery, reproduction, coverage,
parity, migration or completion without final-state evidence.

Keep the existing champion and valid published forecast behavior. No new model
research, fitting, protected evaluation, promotion, architecture route switch,
production cutover, scheduler retirement, terminal-route reopening or threshold
change is authorized by this prompt. Preserve current Architecture V2/V4 gates.
Report actual partial success and exact remaining prerequisites; do not claim
whole-map/phase completion from fewer error or blocked rows.

Stop dependent work only for genuinely unresolved evidence, an actual required
owner decision, provider restriction, unavailable external dependency or safety
blocker. Complete all independent authorized work first. A final handoff must
state completed IDs, verification, remaining cohorts and exact next actions,
without starting another map or phase.
```

Audit delivery verification is recorded below. Remediation remains **NOT EXECUTED**. Existing architecture and V4 implementation gates remain unchanged.

Final audit-deliverable review: **PASS**. Sections A–K, 17 issue IDs, 22 unique task definitions and 22 checklist entries reconcile. Nine collected-evidence hashes, 81 full repository paths, 32 scoped Python paths, 16 referenced test filenames and 34 Markdown links passed local reference checks. The review also checked census/integrity denominators and explicit read-only evidence for every collection. The senior-review checklist in `docs/review-checklist.md` was applied to scope, source authority, preservation, evidence, phase limits and delivery; implementation-specific checks are deferred to actual implementation.

`git diff --check` exited 0. The untracked report was also explicitly checked with `git diff --no-index --check /dev/null docs/evidence/data-status-remediation-report.md`: exit 1 denotes the new-file difference, with no whitespace diagnostics. The report-specific review command exited 0. Receipt: [local report review](../../.local/data-status-audit/report-review.json). No code tests were run or claimed.

Delivery state: local research/planning output on `ft/data-status-audit`, based on `e5b9b88`; report remains uncommitted for review. Commit/push/PR were not performed, consistent with the analysis/research exception in `docs/git-delivery.md`. The only visible task change is this new Markdown report; `CURRENT_TASK_STATUS.md` and raw audit receipts remain ignored local tracking/evidence. No unrelated work was present or altered.


## L. Autonomous execution checkpoints — 2026-11-02

### L1. Scope and refreshed evidence

Execution started at `8b82dd6` on `main`, as initially requested. The owner subsequently requested a new branch and commits before moving to each later task/phase. Work continues on `ft/data-status-remediation`. The existing audit text and original `.local/data-status-audit` receipts remain intact. `CURRENT_TASK_STATUS.md` is the ignored local tracker. No Wayfinder map was claimed or reopened.

The fresh read-only census ran at 11:05:33–11:05:50 UTC (12:05:33–12:05:50 Africa/Lagos). Each follow-up collection declares its own repeatable-read snapshot; moving worker totals are not combined as one snapshot. The exact candidate IDs, source hashes, provider/competition/season keys, current/native case owners and SQL are retained in `.local/data-status-remediation/candidates.json`. Current source/artifact verification inspected 67,070 raw registrations: 67,037 verify and 33 remain unavailable. Missing sets remain 22 dataset manifests and 26 model manifests. All 13 dependent forecasts retain their exact existing synthetic-test exclusions. No registration or retirement was changed.

Current mapping trust is unchanged: 20,805 active mappings, 15,749 admitted, 4,947 unresolved, 108 contradictory, one revoked, and 984 unsafe shared groups. Counts alone do not prove which additional mapping IDs, if any, are eligible for admission; DS07 must compare each qualified mapping with its current trust before applying a change. Native cases, historical decisions, current mappings and canonical fixture IDs remain separate denominators.

The operating database is still at migration `202610310500`. Its `/version` response reports `dev` with unknown code SHA, dependency lock hash and worktree state. The settings file has history scheduling disabled and live FotMob/PitchAPI enabled, but those file values do not prove the running process environment. Existing scoped reconciliation signatures are deployed; they were not reimplemented. Later-schema recovery and new failure-deadline code require verified ordinary deployment. No operating migration, runtime restart, stage switch, scheduler retirement, model fit, evaluation or promotion was performed.

Several audit helpers (`football.providers.data_audit`, `football.product.market_capability_cli`, and related V4 research helpers) belong to the audit's different source checkout and are absent from this branch. Their historical audit results are retained as such. Current execution does not import later-route implementation merely to refresh a diagnostic. The refreshed extra collection records these helper results as unavailable, rather than treating old values as fresh. Its database queries completed without errors; an obsolete console-summary expression failed after the JSON receipt had been written. That reporting-only collector expression was corrected without rerunning the successful queries.

### L2. Research decisions and recovery limits

- [PostgreSQL 18 error codes](https://www.postgresql.org/docs/18/errcodes-appendix.html) support classification by SQLSTATE. The existing identity guard still has generic `P0001`, so only its exact first-line message is recognized as the known external identity blocker. Other integrity/undefined-function/protocol failures are not treated as transient.
- [FotMob terms, dated 2026-10-22](https://www.fotmob.com/tos.txt) retain explicit restrictions on systematic retrieval. No applicable account-specific written exception was found in the inspected evidence. New automated acquisition remains permission-dependent. No existing worker/configuration was silently changed.
- [PitchAPI reference](https://pitchapi.dev/) establishes technical fields, response metadata and predicted-lineup distinctions. It does not establish unrestricted current acquisition rights. Exact pre-existing owner-accepted retained research scopes remain governed by their own decisions; they are not generalized into new acquisition permission.
- [API-Football terms](https://www.api-football.com/terms) and [football-data.org policies](https://docs.football-data.org/general/v4/policies.html) support existing account/quota limits and explicit historical scopes. No account entitlement, paid expansion or new budget was inferred. The 495 quota-wait jobs and 11 identity-conflict jobs remain operationally unresolved until the applicable capacity/evidence and deployed fix exist.
- [OpenFootball](https://github.com/openfootball/football.json) and [Reep downloads](https://www.reep.football/data/) remain source-specific public/CC0 alternatives within their actual roles. They do not establish upstream rights, provider bridge correctness, historical membership or player minutes. The public Reep release label differs from the pinned local release, so no silent update was made.
- Exact retained StatsBomb bytes identify all 1,499 unmapped-type findings as Own Goal Against (20): 105, Own Goal For (25): 105, Error (37): 527, and Referee Ball-Drop (41): 762, across 446 verified resources. These are provider-defined event types; new mappings use normalizer v2 and new build identities. Existing v1 bytes/findings remain immutable. The [official specification location](https://github.com/statsbomb/open-data/blob/master/doc/StatsBomb%20Open%20Data%20Specification%20v1.1.pdf) was found; the browser could not parse its octet-stream PDF, so the retained provider event dictionaries are the exact field evidence.
- All 38 historical score-inconsistency cases pass the current score check on their registered, checksum-verified Parquet files. This confirms the existing own-goal correction; it does not erase old findings or constitute a new persisted validation run. Other legitimate clock, stint, coordinate and conflicting-fact warnings remain subject to the unchanged quality policy.
- All 1,304 external predictions lack native provider binding keys in the inspected current rows. Existing 47 legacy matches remain valid under their prior evidence. Names alone cannot produce a new exact binding, settlement or missing pre-match forecast.
- Source-result conflicts remain 1,845 events over 19 distinct fixture IDs. Of those events, 1,835 involve ten FotMob fixture IDs. Age or a different retained score is insufficient to choose a final result or relax transition guards.

The 33 raw registrations have internally impossible constraints: 30 require an all-`c` SHA-256 with exactly two bytes; three require an all-`f` SHA-256 with exactly three bytes. Exhaustive enumeration checked all 65,536 two-byte payloads and all 16,777,216 three-byte payloads and found no match. This proves that authentic byte restoration cannot satisfy those exact registrations. It does not prove each row's historical insertion provenance or authorize deleting/reclassifying it. These rows remain explicit inconsistent registrations. Available backup listings contain SQL/database dumps, which do not supply the absent external raw/model/dataset files. No matching original for the other missing manifests was established; an authentic file backup/locator is still required.

### L3. Execution and task accounting

The two retained failed PitchAPI scopes `l_0275VP/2026/2027` and `l_0ALvwF/2026/2027` were replayed twice in one disposable database with no network requests. Their 61 and 58 provider observations converge to stable row hashes, but both remain `BLOCKED_IDENTITY`, with zero qualified results, canonical fixtures or history rows. The operating scopes were not relabelled as succeeded. The disposable database was removed after recording the receipt.

Four normal context-worker batches selected 32 items each and published 128 context reports, with zero failures or lost leases. Four selected immutable reports were repeated through the normal worker and retained identical input/output hashes. During the declared 11:29:44–11:30:05 UTC sample, pending entries fell from 172,620 to 172,492; the total worklist stayed 228,606 and the oldest pending age remained substantial. Cumulative completed-generation increments include coalesced generations and concurrent work and are not counted as recovered football facts. This is a bounded accepted cohort, not completion of the whole backlog.

Implementation changes and focused tests are prepared for the next verified commit checkpoints. Final aggregate verification, final task dispositions and delivery remain pending. No whole-programme, scientific or architecture phase completion is claimed.

| Task | Original status | Action taken | Final status | Records recovered | Tests | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| DS01 | AUTONOMOUS | Fresh read-only census, exact-ID candidate manifest and active/native denominators | PASS | 0 | 199 census queries; identity/file audits | snapshot.json; candidates.json; identity-audit.json |
| DS02 | AUTONOMOUS | Trace missing parents and exact existing retirement overlap; prove invalid raw hash/size pairs | PASS_WITH_WARNINGS | 0 | Exact-byte checks; 13/13 retirement overlap; exhaustive hash checks | files.json; safety-tail.json; sentinel-hash-proof.json |
| DS03 | AUTONOMOUS_PREPARATION | Preflight missing recovery tables/history deadline signature; rehearse upgrade twice in disposable database | VERIFIED_CODE_PENDING_ROLLOUT | 0 | Focused upgrade and pre-migration regressions pass | focused-deadlines.log; runtime.json |
| DS04 | RESEARCH_DEPENDENT | Refresh official source terms and preserve exact existing retention decisions | RESEARCH_COMPLETE_WITH_RIGHTS_GAPS | 0 | No provider data requests made | Report L sources; runtime.json |
| DS05 | AUTONOMOUS_DIAGNOSTICS | Inspect local settings, unknown runtime build, quotas and suppressed history cohorts | DIAGNOSTICS_COMPLETE | 0 | 495 quota waits; 11 identity waits remain; no budget/config changes | detail.json; runtime.json |
| DS06 | RESEARCH_DEPENDENT | Verify retained failures in empty and populated isolated copies; repair unusable optional aliases | POPULATED_REPLAY_IN_PROGRESS | 0 canonical; 119 native observations in disposable database only | Both runs converge without network requests | scope-replay.json |
| DS07 | RESEARCH_DEPENDENT | Recompute all active mapping trust with existing verifier | NO_NEW_AUTOMATIC_ADMISSION_PROVED | 0 | Exact-ID comparison: all 15,749 qualified mappings already trusted; zero eligible unadmitted IDs | identity-audit.json; candidates.json |
| DS08 | RESEARCH_DEPENDENT | Preserve exact native/current cohorts; shadow replay cannot pass missing identity proof | IDENTITY_PROOF_REQUIRED | 0 | Two failed scopes remain blocked and duplicate-free | candidates.json; scope-replay.json |
| DS09 | RESEARCH_DEPENDENT | Inspect legacy registration/read contracts and immutable raw bytes | LEGACY_MANIFEST_PROOF_GAP_RETAINED | 0 | 48 UK mismatches and one missing OpenFootball manifest remain separately classified | files.json; extra.json; historical_manifest.py |
| DS10 | RESEARCH_DEPENDENT | Separate native player data from qualified canonical period/minute exposure | TARGET_QUALIFICATION_REQUIRED | 0 | No inferred player identity, membership or minutes | Original audit S5; current-branch limitations in L |
| DS11 | RESEARCH_DEPENDENT | Identify all four retained unmapped types; add versioned mappings; replay exact old score cases | VERIFIED_CODE; NO_PUBLISHED_REBUILD | 0 published; 1,499 mapping candidates | Normalization regressions pass; current score checks pass 38/38 | quality-research.json; quality-score-replay.json; event-types.log |
| DS12 | RESEARCH_DEPENDENT | Inspect exact binding prerequisites for every prediction | NO_NEW_EXACT_BINDING_PROVED | 0 | All 1,304 lack native provider binding keys; existing 47 legacy matches preserved | runtime.json |
| DS13 | RESEARCH_DEPENDENT | Inspect current observation score bases and retained conflict cohorts | CONFLICTS_PRESERVED_PENDING_PROOF | 0 | 1,845 events cover 19 fixture IDs; 1,835 FotMob events cover ten IDs | candidates.json; safety-tail.json |
| DS14 | AUTONOMOUS | Classify deterministic/transient failures; atomically project proven quota deadlines | VERIFIED_CODE_PENDING_ROLLOUT | 0 | No-repeat blocking, release/projection, quota deadline and fencing regressions pass | focused-deadlines.log; history-unit.log |
| DS15 | AUTONOMOUS | Preserve specific cause before generic JSON; redact nested summaries and streamed logs | VERIFIED_CODE_PENDING_ROLLOUT | 0 | Go process/cancellation/redaction tests pass | go-sync-final.log; go-lint.log |
| DS16 | AUTONOMOUS_WITHIN_BOUNDS | Run four existing 32-item context batches; repeat four immutable reports | BOUNDED_COHORT_PASS_BACKLOG_REMAINS | 128 context reports; 0 football facts | 128 published; zero failures/lease losses; four stable repeated hashes | report-drain.json |
| DS17 | AUTONOMOUS | Mark unavailable measurements and current-state counters explicitly; retain circuit enum compatibility | VERIFIED_CODE_PENDING_ROLLOUT | 0 | Unit/integration measurement-state assertions pass | unit.log; focused-integration.log |
| DS18 | HUMAN_DECISION | Consolidate source-specific permission and capacity gaps after research | DEPENDENT_ACQUISITION_BLOCKED | 0 | No source enablement, account changes, purchases or provider contact | Report L sources and decision register |
| DS19 | HUMAN_DECISION | Preserve authenticated review; no unsupported relationship submitted as approval-ready | NO_NEW_EVIDENCE_COMPLETE_PROPOSAL | 0 | No fabricated actor/approval or broadened retirement | identity-audit.json; scope-replay.json |
| DS20 | EXTERNAL_BLOCKER | Exhaustively prove 33 raw hash/size pairs impossible; inspect available backup kinds | RAW_REGISTRATION_INCONSISTENT; OTHER_ORIGINALS_UNAVAILABLE | 0 | 65,536 two-byte and 16,777,216 three-byte payloads checked; no matches | sentinel-hash-proof.json; files.json |
| DS21 | AUTONOMOUS_FOR_ELIGIBLE_COHORTS | Replay exact retained scopes twice in isolation and publish bounded existing reports | SHADOW_CONVERGENCE_PASS; CANONICAL_RECOVERY_BLOCKED | 128 derived reports; 0 canonical facts | Stable shadow row hashes; zero network; four report hash replays stable | scope-replay.json; report-drain.json |
| DS22 | AUTONOMOUS | Finish final diff review, aggregate verification, commit checkpoints and delivery | IN_PROGRESS | Not a recovery quota | Final aggregate pending | CURRENT_TASK_STATUS.md |

### L4. Local receipt hashes

| Receipt | SHA-256 |
| --- | --- |
| [local snapshot.json](../../.local/data-status-remediation/snapshot.json) | `430029aed43e9061c4803655889e1caf7c9c15cea75143709e7ee77c89e7d08f` |
| [local detail.json](../../.local/data-status-remediation/detail.json) | `baf030342566e0739fa8b56804b9a499455adf53a93aa2bf06d95523645597a3` |
| [local files.json](../../.local/data-status-remediation/files.json) | `71e0c9d3fb4655bdbe764379739634b63e5f19e8852769b48e88df05ea5d62fa` |
| [local candidates.json](../../.local/data-status-remediation/candidates.json) | `aa9e756f93830d7303e17903b8e1c7510724ad21f1a92864fff59c7149e485f3` |
| [local identity-audit.json](../../.local/data-status-remediation/identity-audit.json) | `d402b2e0bb53d00beb6b04ef8a5d8a22b56d17386acb9915ae41b93233730496` |
| [local final-queries.json](../../.local/data-status-remediation/final-queries.json) | `2e4c5b268415789db084215c36382403f0828efe254e2f32cb49f84d239a1591` |
| [local safety-tail.json](../../.local/data-status-remediation/safety-tail.json) | `799cda119cd8eeaa8fdc30266069ca9d27d61187da501e63f480579e12b972a9` |
| [local extra.json](../../.local/data-status-remediation/extra.json) | `c1c983650dc6a2b6d2e075db84085ebf0fb121b6580d99e0f05ddcb44c7da721` |
| [local runtime.json](../../.local/data-status-remediation/runtime.json) | `e4f872eb43a505023d54bd5384fd080bffdcf64ac697a7d380cb05ab7405554d` |
| [local sentinel-hash-proof.json](../../.local/data-status-remediation/sentinel-hash-proof.json) | `6d53086c52db1c98dae1b3571a6402169ee42de0ca4456c1c70a31c91520ecee` |
| [local quality-research.json](../../.local/data-status-remediation/quality-research.json) | `91ddc077c2a2ea32d40c371d8d64aab61ef0c2eb24d1e4a9bd19c8a738ec7e7c` |
| [local quality-score-replay.json](../../.local/data-status-remediation/quality-score-replay.json) | `8a425c757d2646df8caa8af264895856c8a5d6771ac8bd7e4f5a307ee2b391e8` |
| [local scope-replay.json](../../.local/data-status-remediation/scope-replay.json) | `da5a2097189d8b4e00727279447602ed7324afe9c7b6c1341e1a554ab7e222f2` |
| [local report-drain.json](../../.local/data-status-remediation/report-drain.json) | `565bb1168f87c8cc9068da9341c9858e2dfcc253a4fdca356b3496aba266bfa8` |

### L5. Commit checkpoints

- `f015973`: inventory/research report committed before continuing the preserved implementation batch.
- DS03/DS14 code checkpoint: 83 focused unit tests and 62 disposable-database cases pass. Scoped Ruff lint/format, Mypy (eight files), SQL migration validation and whitespace checks pass. The schema upgrade was applied twice in a disposable database; pre-migration work is blocked and all 13 stage routes remain `LEGACY`. This checkpoint does not deploy the operating runtime or rewrite its old attempts.

DS14 adds one migration because the deployed history failure adapter discarded the shared retry/cooldown arguments. Both the original seven-argument API and the new deadline-aware API use the same fenced implementation. Rate-limit body errors and HTTP `Retry-After` remain retryable; unknown integrity/protocol failures remain non-retryable. The release regression uses the existing release and projection functions in one transaction, preserving queue/shared deadline agreement.

- `ba63a0d`: DS03/DS14 preflight, failure classification and atomic provider deadlines committed.
- DS15 checkpoint: focused Go process, generic-summary, stream-redaction and cancellation tests, `go vet ./...`, and `golangci-lint run ./...` pass. Private stdout/stderr logs are redacted before persistence; structured summaries retain their original error and run/log correlation. Empty generic error containers no longer hide a specific preceding exception. The focused race-detector check also passes.

- `b68cf79`: DS15 original-cause and redacted-process-output checkpoint committed.
- DS17 checkpoint: six unit tests and five disposable-database tests pass, as do scoped Ruff formatting/lint and Mypy. `unmeasured_fields` distinguishes unsupported placeholders from measured zero; `current_state_fields` identifies job counters that cannot reconstruct an earlier state. Empty scopes retain `NEVER_SUCCEEDED` and explicit measurement-unavailable diagnostics. The existing circuit enum and serialization/digest for fully measured snapshots are preserved.

- `df976ad`: DS17 unavailable/current-state metric checkpoint committed.
- DS11 checkpoint: 15 normalization/quality unit tests and three disposable publication/validation scenarios pass. The database scenarios verify v2 publication plus idempotent validation of both v1 and v2 datasets. Scoped Ruff/Mypy and whitespace checks pass. The read-only replay of all 38 historical score findings passes the current score rule, and all 1,499 unmapped-type cases have exact retained-source type evidence. No operating dataset was rebuilt, no old finding was erased, and no model feature/evaluation gate was changed.

- `35fd47d`: DS11 versioned StatsBomb mapping and v1 compatibility checkpoint committed.
- DS07 exact-ID checkpoint: the read-only 11:55:41–11:56:08 UTC audit compared all 20,805 active mapping decisions against current trust. Exactly 14,193 origin anchors and 1,556 crosswalks are already trusted; all 108 contradictory, one revoked and 4,947 unresolved mappings are untrusted. The exact eligible-unadmitted set is empty. No automatic admission was skipped and no mapping/approval actor was fabricated. New relationship evidence is required for the unresolved cohort; names and aggregate count equality are insufficient. Receipt: [identity eligibility](../../.local/data-status-remediation/identity-eligibility.json), SHA-256 `5c5adb799fcde0a35f3feb16fb1f4531f6ffb00cd273dc8058222b21de75a954`.

### L6. Populated retained-source rehearsal and optional search aliases

The earlier empty-database PitchAPI replay establishes source parsing and idempotency only; it cannot establish eligibility against operating admissions. A new consistent operating snapshot, exported at 12:01:02 UTC, was dumped read-only and restored into `football_ds_populated_7bd6703eae2842fcb98c299445d116da`. The 1,410,654,762-byte dump was restored successfully, existing/new migrations applied twice, and immutable source files copied using APFS copy-on-write. Operations were not restored over, migrated or restarted. This populated copy is the qualification environment for further retained replay.

A concrete upstream failure is now reproduced: seven `fotmob/9195` seasons contain 238 fixture-row failures from the empty `product_team_aliases.normalized_name` constraint. In snapshot `74cfa9dd-53ee-58b2-a1c6-73e47fe64159`, provider team `4724` is named `AFC`, and all 34 of its 2020/2021 appearances normalize to an empty search alias. The exact source SHA-256 is `f05759ed67372c55327e2afa5aee66aa260520f8f1e6323b80137235f3534bdf`. These are row occurrences across seasons, not a new unique-match recovery total.

The narrow fix keeps original names and stable native/canonical IDs, omits only an unusable optional search alias, and logs the provider/team/snapshot context. It changes neither global name normalization nor identity admission rules. The exact `AFC` regression and non-Latin/designator-only cases retain provisional identity and empty eligible history; a second run keeps the same fixture/native mapping IDs. Twenty disposable operational-sync tests, scoped Ruff formatting/lint/complexity, Mypy and whitespace checks pass. No empty alias, invented name, transliteration or new trust claim is written.

The populated rehearsal is processing the retained alias-error cohorts, thirteen deadlock-only scopes, and two PitchAPI scopes twice, with zero provider requests. It compares core fact IDs/hashes and preserves explicit blockers. Its final results and any operating recovery authorization remain pending; this code checkpoint does not claim that those scopes or the remediation programme are complete.

Receipt: [source alias cases](../../.local/data-status-remediation/retained-alias-cases.json), SHA-256 `251f4fca2b99ab8482089ff9df3237b51299fb006e5dbf5d5373b5f4d569a311`.

Receipt: [populated provision](../../.local/data-status-remediation/populated/provision.json), SHA-256 `a421baaba0e966462783b0e58a5c4fadadeda29b20a548d4c9b4557a21e6a649`.
