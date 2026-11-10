# Foundation, compatibility and deferred-feature acceptance

Checkpoint I2. **Design definitions and future acceptance, not implemented gate
passes.** Read [current evidence](current-state.md), [target design](design.md),
[learning](learning.md), [recovery](storage-recovery.md),
[ADR 0005](../../adr/0005-unified-architecture-evolution.md) and the single
[roadmap](roadmap.md). Source paths below are repository-relative; Python modules
are beneath `python/football/src/football/` unless a full path is given.

## Fifteen foundation requirements

The disposition describes the required change, not automatic authorization.
Existing tests are reusable harnesses, not claims that this investigation ran
all of them. The acceptance column defines the additional deterministic contract.
All rows use proposed ADR 0005 and preserve the original scientific/phase gates.

| ID | Current owner / contract and maturity | Disposition | Exact negative/positive acceptance and harness | Ticket / subsequent handoff |
| --- | --- | --- | --- | --- |
| A02 | `forecasting/market_catalogue.py::MarketDefinition`, `products.py`, `model_runner.py`; target catalogue and score projections implemented; publication/settlement compatibility partial | EXTEND | 1X2 partitions, draw/double-chance unions, strict/quarter lines, censored tails, period/basis and unsupported model preserved across Go→TS; extend market/product tests and `web/lib/contracts.test.ts`; incompatible ET never settles regulation | P06-02, P05-01; BASE-RULES → F7; A01 excluded |
| B01 | `identity/repository.py`, `player_source_facts`, match participation, `context/live.py`; source/team associations exist, full temporal registration query not established | EXTEND | 2024 query excludes 2026 transfer/loan/call-up; opposite-team ambiguity rejected; extend identity-history/participation integration tests | P08-02; BASE-IDENTITY → POST-F2-01 |
| B02 | `LineupObservationV1`, `player_position_stints`, V3 resource observations; shape/grid fields implemented, tactical segment meaning partial | EXTEND | Starting formation remains unchanged after source-proven substitution/shape revision; unknown coordinates are not zero; extend live-context and rich-observation fixtures | P08-02; BASE-SOURCE/API → F3 |
| B03 | `context/live.py::LineupObservation`, `PredictedLineupV1`, current lineup-mode enum; PARTIAL not a distinct current mode | EXTEND | Partial/predicted never labelled confirmed; late confirmation excluded at old cutoff; duplicate starter/opposite-side invalid; new version does not alter old bytes | P08-02; BASE-IDENTITY/SOURCE → POST-F3-01/03 |
| B04 | `AvailabilityObservation`, `context_sync.py` default-disabled gates; qualified operating rows 0, effective activation unverified | EXTEND | Empty/unsupported/restricted/stale/unknown/no-reported-issue remain distinct; injury/suspension/doubt/rest/tactical cause preserved; extend `test_context_sync.py`, `test_live_context.py` | P08-02 policy only; actual intake/UI → F4 |
| B05 | `docs/source-acquisition.md`, raw/context/export owners; general access policy exists, specific new health/minor policy not established | BLOCKED_EVIDENCE | No new availability source before source-rights/minimization/correction/expiry/minors policy; restricted export and diagnostic log tests; no clinical inference | P01-02, P08-02, P12-01; BASE-PRIVACY → POST-F4-01 |
| C01 | `forecasting/features.py`, `dataset.py`, feature snapshot contract, current model runner; centralized history implemented; future-feature parity unverified | EXTEND | Same source/cutoff/null/category vectors produce identical fit/shadow/serve features; post-kickoff correction and same-batch targets excluded; extend feature/backtesting and model-runner tests | P16-02; BASE-SCIENCE → F5/F6 |
| C02 | `forecasting/evaluation.py`, `uncertainty.py`, post-match monitoring; paired scoring implemented, monitoring denominator counts issued forecasts | EXTEND | Easier subset cannot win on raw accuracy; paired eligible IDs/horizons and full eligible-denominator/abstention/segment shift report required | P16-01/03; BASE-SCIENCE → F6 |
| C03 | `runtime_models.py`, `model_runner.py::ModelRegistry`, artifact loader and `model-registration.schema.json`; exact artifact/retired checks implemented; operating registry empty | ALREADY_SATISFIED at loader/registry code scope only | Extend `tests/integration/test_runtime_model_registry.py` and runner/API tests for missing/corrupt/incompatible/RETIRED approved role: unavailable, no implicit fallback; retain history | P06-02, P16-01 verification; BASE-SCIENCE/API → F7 |
| C04 | `evaluation_protocol.py`, `experiments.py`, `replacement_holdout.py`, artifact/governance contracts; frozen protection implemented; automated lifecycle not operating | EXTEND | Inspected/spent/protected targets cannot become unspent; identical run retry converges, immutable fit/artifact/policy hashes; missing policy stops before outcome load | P16-02/03; BASE-SCIENCE → F5/F6 |
| D01 | `product_standings`, standing observations and Go standings API; source tables implemented, competition-rule completeness unverified | EXTEND | Deduction, ordered tie break, split/playoff, award/abandonment and aggregate golden cases; unknown rule yields partial source table; extend serving/context tests | P06-02, P08-02; BASE-RULES → POST-F1-02 |
| D02 | `providers/capability_registry.py`, `resource_authority.py`, scoped capability schema; SHADOW_ONLY, 26 retained rows | EXTEND | Entitlement/methodology/season change blocks only affected scope; UNKNOWN/UNSUPPORTED/RESTRICTED/PARTIAL not empty confirmed; preserve original source values and version history | P08-01; BASE-SOURCE → F0/F2/F3/F4/F10 |
| E01 | `work/contracts.py`, `work/storage.py`, Go operations and sync APIs; operating work and expired RUNNING rows observed | EXTEND | Task IN_PROGRESS with zero valid leases does not imply running workers; SUCCEEDED+BLOCKED report stays blocked acceptance; DB/API/SSR/event views agree on lease/generation | P03-01, P05-02, P06-01; BASE-OPS → F8 |
| E02 | `app.go::version`, build ldflags in Makefile, Goose and registry/stage settings; code provenance supported, operating values unknown and migration absent | EXTEND | Running commit/lock/schema hashes/model/route mismatch prevents adoption claim; `/readyz` 200 alone insufficient; extend version/readiness/serving tests | P00-01, P14-01, P18-01; BASE-OPS → F0/F8 |
| E03 | `admin_access.go`, source-path/immutable stores, experimental DB guard; current local controls implemented, future streams/backups need integration | EXTEND | Host/Origin/peer/token/JSON, SSE scope/resume, SSR secret/cache, SSRF/traversal/bomb, wrong-key/operating-restore target and stale fence failures; use existing Go, raw, restore and Playwright harnesses | P01-02, P04-02, P06-01, P12-01/P17-01; BASE-PRIVACY/OPS |

B05 blocks its sensitive source scope; it does not block a read-only team page
using already qualified public results. C03 code support does not confer an
operating gate PASS. New enum meanings or member/formation contracts require
actual source fixtures and compatible later versions, not edits to old schema
fingerprints. Core completion does not require deferred F-pages or new science.

## Remaining audit-ID handoff

The companion's phase table supplies references for the other 24 non-P0 IDs;
A01 is the twenty-fifth non-P0 item and remains explicitly excluded. Together
with the 15 foundation IDs, these account for all 40 IDs without inventing the
missing original audit definitions. `registers.json` retains the exact ID→F-phase
references; use the companion's actual ticket scope, not an inferred gap title.

| ID group | Deferred IDs | Companion phases containing those references |
| --- | --- | --- |
| A | A03–A08 | F0/F1/F2/F7/F9/F11, as individually mapped in the register |
| B | B06–B10 | F0/F2/F3/F5/F6/F10 |
| C | C05–C07 | F0/F5/F6/F7/F8 |
| D | D03–D05 | F0/F3/F7/F10 |
| E | E04–E10 | F0/F6/F8/F9/F10/F11 |

## EXT-01–EXT-09 dispositions

| ID | Verified owner/version and current maturity | Target seam and remaining gap | Ticket / acceptance |
| --- | --- | --- | --- |
| EXT-01 | Actual dependency map in current-state; `scripts/check_architecture_boundaries.py`; IMPLEMENTED direct-boundary guard, SHADOW canonical path | Keep one writer per domain; extend checks only for demonstrated new SQL/worker/UI bypasses; no generic platform | P00-01/P14-01; unauthorized import/writer and duplicate scheduler fixture fails |
| EXT-02 | `ProviderPayload`, native models, resource-observations V1–V3, capability registry; IMPLEMENTED/SHADOW by path | Typed resource/field semantics, independent identity/known time/capability; fill only approved gaps | P08-01/02; new field/resource/null tests, cases X1–X3 |
| EXT-03 | `WorkType`, `WorkRequest`, leases/fences, dependency state events; OPERATING for observed work | Reuse work registration and versioned committed event publication; event seam DOCUMENTED_ONLY | P03-01/P04-01; crash/retry/correction/no-starvation and X1/X6 |
| EXT-04 | SQL migrations, OpenAPI, TS parser, model schemas; existing versions IMPLEMENTED, mixed future releases UNVERIFIED | Explicit N/N−1 contract window, scoped event versions and reversible expand/migrate/contract | P06-01/P14-01/P17-01; old/new producer-consumer rehearsal |
| EXT-05 | Next SSR shells, expanded fixture, HTML designs, shared components; IMPLEMENTED partial composition | Typed server-query-owned optional sections, request-rendered Admin data and shared event cache; no runtime plugins | P06-01/P07-01; X4/X7, keyboard/mobile/SSR/capability-off parity |
| EXT-06 | `MarketDefinition`, model/feature/experiment/artifact contracts; IMPLEMENTED scientific owners, future models blocked separately | New market/model must declare supported distribution/period/inputs/evaluation and authority | P06-02/P16-02/03; X5/X6, C01–C04 |
| EXT-07 | Immutable raw/artifact stores, SQL lock/fence and experimental guards; IMPLEMENTED; new archive/release path UNVERIFIED | Per-slice resource/rights/backup/migration and serving rollback record | P01/P10/P11/P12/P18; interruption/disk/corrupt source/rollback |
| EXT-08 | Architecture, schema, feature, Go/TS contract and migration test harnesses exist | Extend current `make check`/integration/CI; no new framework; release fitness tests remain unimplemented | P14-01/P17-01; run deterministic positive/negative X1–X7 |
| EXT-09 | Path-level owner inspection and tests below; compression/RNG experiments are separate technical proofs | Seven future release demonstrations all UNVERIFIED until authorized scoped fixtures/rehearsals run | P17-02; measured actual diff radius/resources, no speculative pluggability PASS |

## Seven path-level extension demonstrations

The file counts are **proposed minimum edit radius** from current owner inspection,
not measured production extension diffs or a guarantee that no central registry
will change. Named existing paths are verified; `<new>` names denote future files,
not created code. All seven future-feature operating proofs are **UNVERIFIED**.
The static route and exact test design are delivered now; execution/acceptance is
attached to P17-02 or the relevant independently authorized F-ticket.

| Case / localized edits | Source/authority and contract fixtures | Tests, resource effect and switch/rollback |
| --- | --- | --- |
| X1 another provider: `providers/sources/<new>.py`, `providers/native/<new>.py`, `providers/normalization/<new>.py`, current capability/adapter registration and provider fixture tests (about 5–7 files) | Exact native resource sample, source terms/entitlement/quota, schema and processing version; old native fields + additive unknown enum, new native ID reuse and unsupported resource | Extend `test_provider_resource_capabilities.py`, normalizer/native tests, work/fence integration; zero calls until approved capability; source-scoped disabled rollout, stop adapter and retain raw observations. No new identity/queue |
| X2 player metric: existing typed observation/measurement declaration, versioned resource schema only if needed, coverage/consumer parser and tests (about 4–6 files) | Unit/population/period/method version and real known-at; absent historical value=null, observed zero=0; preserve original player ID and snapshot | Rich-observation/identity/feature differential fixtures; display-only field adds payload/storage, not champion inputs. Capability-gated display, revert reader while retaining new source bytes; old snapshot/hash unchanged |
| X3 injury source: provider-owned adapter, capability/authority, `context_sync.py`, `context/live.py` only if a new sourced meaning, tests (about 4–7 files) | BASE-PRIVACY and exact provider/league entitlement first; missing/stale/revoked/empty versus no reported issue; minor and correction expiry fixtures | Context sync/live and security/export tests; bounded context calls below live reserve, canonical player verification. Existing context flags stay disabled until approved; stop that scope, retain policy-compliant lineage, no probability effect |
| X4 formation section: `web/components/expanded-fixture.tsx`, one `<new>` section, `web/lib/contracts.ts`, existing Go context DTO/query if missing, component/E2E tests (about 4–6 files) | Qualified `LineupObservation`/grid/shape/confirmation version; list alternative, partial formation and unknown coordinates; no inferred XI | HTML comparison, SSR/hydration, keyboard/mobile/axe, no duplicate requests/new timer/connection. Section switch is proposed, not existing; disable presentation without model/fixture edits or deleting observations |
| X5 market: `forecasting/market_catalogue.py`, `products.py` or approved product owner, Go/OpenAPI/TS consumers and tests (about 5–8 files) | Exact event/line/period/basis/distribution and model support; old 1X2 fixture, incompatible ET fixture, unresolved-tail fixture; separate scientific authority where model changes | Product coherence/complement and settlement tests; no renamed unrelated probability. Market capability disabled until accepted; revert selection/publication route, preserve old probability and settlement revisions. No A01 filter |
| X6 challenger: approved Python adapter, immutable registration/config, existing fit/feature/evaluation owners and tests (about 4–7 files plus authorized numerical implementation) | One hypothesis, exact artifact/feature versions, qualified snapshot, unspent holdout and resource/scientific decisions; retired/missing/corrupt variant fixtures | Runtime registry, firewall, fit/reload/reproduce, paired denominator and no-fallback tests. Candidate disabled/shadow by default; zero fit calls until authorized; cancel candidate work and retain exact approved champion |
| X7 match-detail section: one `<new>` React section, `expanded-fixture.tsx`, shared API/parser only for genuinely new data, tests (about 3–5 files) | Existing qualified source/identity/section contract; initial/partial/unavailable/additive-field fixtures; resource query and invalidation owner | Shared snapshot/subscription, no duplicate fetches, a11y/mobile/reflow/SSR and disabled-section probability parity. Proposed presentation switch; revert section only, retain data and subscriptions for existing consumers |

Unavoidable shared edits are explicit: X1 may require static provider registration;
X2/X3 may require a typed observation version; X4/X7 may need a missing context DTO;
X5 crosses scientific and settlement contracts; X6 may need substantial authorized
model code. These are targeted owner changes, not proof that arbitrary new data
or models are plug-and-play. Measure touched production paths, query count,
payload/bundle/DOM/CPU/RAM/disk/provider calls against the frozen same-workload
baseline; reject unexplained unrelated changes instead of enforcing an invented
universal file-count ceiling.

## Compatibility and staged-release fixtures

Support the current approved producer/consumer release N and its preceding
release N−1 during a staged extension rollout. Old versions are retired only after
all required clients/workers are accounted for, the measured stream replay window
and rollback period expire, stored representations remain readable, usage proves
no required consumer, backup/restore passes and owner cutover is authorized.
Immutable historical artifact/schema readers remain available for their retention
lifetime; N−1 deprecation cannot rewrite their bytes.

| Producer / consumer | Positive fixture | Negative / rollback fixture |
| --- | --- | --- |
| Old SQL/API → new Go/TS/SSR | Missing additive field becomes unknown with preserved zero/null/omitted meaning | Required incompatible field or semantic version fails only the affected resource; no silent default |
| New API → old TS/SSR | Additive optional fields ignored; known fields and IDs unchanged | New enum/market/period is explicit unavailable; never relabel as an old meaning |
| Old/new long-lived SSE | Versioned event + entity predecessor and scoped resume checkpoint; old/new clients coexist | Unsupported event/gap causes bounded authorized snapshot; no permanent HTTP timer fallback or leaked Admin event |
| Expanded SQL → old/new worker | Additive migration, existing IDs and constraints retained; bounded backfill checkpoint retry | Transactional failure/restart leaves old data/Goose versions exact; no half-applied destructive contract |
| New model/observation representation → historical reader | Explicit supported loader/codec/schema version, original checksum preserved | Missing/corrupt/RETIRED/incompatible artifact fails closed; never load a latest alternative |
| Optional UI enabled → disabled | SSR layout/cache/API/subscription stays coherent; probability bytes identical | Disable only new section/reader/job; preserve source, forecasts, history and completed unrelated work |

Freeze at least these concrete fixture relationships in implementation tests:
`score=null` versus `score=0`; a source `confirmed=false` versus `true`; unknown
availability versus a successful empty response; regulation 1–1 with ET 2–1;
5+ censored bucket versus exact five; old event entity version 4 arriving after
version 5; snapshot scope offset 10 while concurrent publication 11 commits;
transaction allocated offset 11 rolls back while 12 is attempted; changed source
semantics with unchanged wire field name; absent/corrupt/retired approved role.
Use synthetic fixture UUIDs and controlled clocks, not protected real outcomes.

Expand → migrate → contract: introduce compatible fields/readers off the active
route; shadow compare exact scope outputs; perform bounded authorized backfill
without fabricated historical known times; record mixed-version and restore
proof; enable selected routing; observe; retire only under separate approved
contract step. Rollback disables routing/worker/display, retaining additive schema
and immutable publications. A compensating forward migration is distinct from
restoring a prior service route; do not assume destructive SQL down migrations.

## Live-score regression assignment

These are proposed deterministic extensions to existing harnesses, not new passing
results. P02/P03 own backend publication, P04 transport/cache, P17 integrated proof.
Every case retains original forecast and compatible settlement behavior.

| # | Controlled scenario | Owning harness and required assertion |
| --- | --- | --- |
| 1 | SCHEDULED→LIVE | Operational sync + Go fixture/live DB tests; qualified lifecycle published together |
| 2 | Verified live 0–0 | Native/normalizer/Go/TS fixture; zero remains present, not unavailable |
| 3 | 0–0→1–0 | Live-order + event/cache tests; next version reaches collapsed and expanded view |
| 4 | HT and FT | Lifecycle/period fixtures; compatible final only, no elapsed-time inference |
| 5 | Delayed final | Provider refresh/work tests; bounded retry, last verified state and reason retained |
| 6 | Source correction | Resolution/settlement/post-match tests; new revisions, old bytes unchanged |
| 7 | Missing score | API/React contract tests; null with exact evidence cause, no event-count guess |
| 8 | Unknown freshness | Go/TS fixture; unknown clock cannot become FRESH |
| 9 | Stale resource | Controlled DB clock/deadline + browser state; separate score/event/stat freshness |
| 10 | Provider outage/recovery | Worker/source fixtures; retry/cooldown and unrelated-provider independence |
| 11 | Quota exhaustion | Provider policy/work fixtures; real cooldown, live reserve and no unbounded catch-up |
| 12 | Worker interruption/lost lease | Work/publication-fence integration; successor only publishes |
| 13 | Conflicting provider identity | Existing MC Oran synthetic binding fixture; withhold resource and retain conflict |
| 14 | Status/incident contradiction | Go live DB + UI partial-state fixture; incident feed cannot choose lifecycle |
| 15 | Out-of-order update | Source/football-clock ordering + entity versions; old fact does not overwrite |
| 16 | Repeated response | Raw/observation/work tests; same logical update does not duplicate output |
| 17 | Reload/tab resume | Playwright controlled events; resume/checkpoint or one exceptional snapshot |
| 18 | Browser closed | Go schedule + worker integration; acquisition/publication independent of UI |
| 19 | Expired cache | Use-resource generation + event fixtures; old HTTP response cannot regress state |
| 20 | Concurrent sync | Work/lock/fixture DB fixtures; one qualified publication, independent jobs usable |
| 21 | Midnight/timezone | Schedule/date-filter fixtures; Africa/Lagos boundary and earlier-day final catch-up |
| 22 | Newly verified identity | Existing correction/replay integration; affected unbound score becomes reconsidered only after proof, old cutoff unchanged |

## BASE-EXTENSION handoff manifest

Companion:
[MatchForge_Post_Redesign_Extensible_Football_Product_Implementation_Plan_v2_2026-11-09.md](../../../MatchForge_Post_Redesign_Extensible_Football_Product_Implementation_Plan_v2_2026-11-09.md),
SHA-256 `1af14d28180d97b8ab60f228c5dae539f841c3a4b98d5f1a175b35c79fb8c95a`.
This is a **scope-specific design handoff**, not a blanket runtime PASS.
POST-F0-00 must verify it for each selected feature/cohort. A01 is excluded from
all tickets and is not a prerequisite for this handoff.

| Manifest item | Delivered definition / current proof | Required independent implementation proof |
| --- | --- | --- |
| Module/writer map | Current-state owner/dependency map and EXT table | Selected scope's actual running writer/API/version; no duplicate owner |
| Extension/version | `ProviderPayload`, observation V1–V3, work contracts, `MarketDefinition`, `ModelRegistration`, source-backed UI composition | X-case scoped contract fixtures and any targeted missing seam accepted |
| SQL/API/event/model compatibility | N/N−1 and historical-reader policy above | Mixed-release Go→OpenAPI→TS→SSR→SSE tests; additive upgrade/retry and restore |
| Safe switches | Existing context enablement defaults off; explicit registry enabled set; stage routes LEGACY | Effective runtime flags must be observed; new per-section/source/candidate switches are proposals until implemented |
| Identity/source qualification | Stable/native IDs, bitemporal decisions and field-scoped capability owners | Exact selected provider/team/player/competition/season proof, known time and entitlement; no name-only merge |
| Rights/privacy/resources | Minimal availability policy, scoped export, Mac headroom/fairness | Approved source/health/media policy and measured provider/CPU/RAM/WAL/disk budgets |
| Migration/rollback/recovery | Existing immutable publication/experimental guard; recovery design | Verified complete referenced backup, disposable migrate/retry/rollback/restore, reversible route |
| Scientific boundary | Existing frozen governance/firewalls/artifact identity; no model change | New authority only for F5/F6, parity and untouched comparison; no promotion inference |
| UI acceptance | Authoritative HTML, no permanent sidebar, inline sections, SSR and accessibility | Actual typed initial HTML, no duplicate fetch/poll loop, states/keyboard/mobile/performance evidence |

| Companion gate | Scope and current readiness | Consumers |
| --- | --- | --- |
| BASE-IDENTITY | Existing contracts/code; selected feature cohort must independently prove identity/membership/corrections | F1–F4 |
| BASE-SOURCE | Capability/authority code exists; complete selected field/entitlement proof not universal | F0/F2/F3/F4/F10 |
| BASE-API | Existing Go/OpenAPI/TS owners; proposed new team/player/SSR contracts not implemented | All new pages |
| BASE-EVENT | Event design delivered; runtime **NOT IMPLEMENTED** | Live views/F8/F11; an independently justified static team view need not wait |
| BASE-PRIVACY | General restrictions known; new availability/media processing policy **NOT VERIFIED** | F4 and image/sensitive-data portions |
| BASE-SCIENCE | Prior governance exists; future feature/candidate dataset and run authority **NOT GRANTED** | F5/F6; does not block confirmed-lineup display |
| BASE-OPS | Active shared provider work observed; release provenance/full DR/new job budgets not accepted | New background work/F8 |
| BASE-RULES | Goal catalogue/projections exist; selected competition and settlement completeness must be proven | F1/F7 |
| BASE-EXTENSION | Design package delivered, X1–X7 future release acceptance **UNVERIFIED** | F1–F11, independently by slice |

Future-feature playbook: inspect actual code/deployment; select a qualified scope;
identify X-case and sole owner; freeze contract/rights/time/budget; repair one
missing seam only if necessary; expand and test old/new; rehearse failure/retry/
restore; authorize bounded rollout; verify running provenance; retain rollback;
contract later. Commit each independently authorized slice before its dependent
slice. No architecture-wide cutover or optional science dependency is imposed
merely to display an already qualified team field.

## FR-001–FR-016 compatibility and independence

[The original FR report](../../evidence/forecast-readiness-remediation-plan.md)
is dated 3 November, preceding merged PR #179/#182. Its counts are historical,
not a fresh backlog. Current cohorts in current-state supersede aggregate-count
assumptions only; earlier exact IDs/evidence remain preserved.

| FR | Redesign impact / classification | Current disposition and next bounded acceptance | Roadmap |
| --- | --- | --- | --- |
| FR-001 Ghana stranded identities | PARTIAL; independent defect/source relationship | Reuse merged replaced-native correction work; reverify selected old/new mapping and old-cutoff hashes before any new case. No recovery count promised | P02/P08/P09 |
| FR-002 missing native relationships | PARTIAL; AUTHENTIC EVIDENCE | Exact independent source/canonical relationship still required; no fuzzy matching or new identity database substitutes | P08/P09 |
| FR-003 retained ineligible results | DIRECT mechanism, PARTIAL data | Failed eligibility predicate and source/identity/known-time proof per cohort; bounded replay and future-history recomputation; old snapshot unchanged | P02/P09 |
| FR-004 genuine missing history | PARTIAL; EXTERNAL/SOURCE | New architecture cannot manufacture history; later separately scoped source work under standing access policy, exact retained bytes/qualification and current team coverage | P09 |
| FR-005 Scottish namespaces | PARTIAL; independent/source fix | Preserve merged parser/alias work; dated competition/season/identity census, no historical namespace rewrite or blanket admission | P02/P08/P09 |
| FR-006 admission refresh fanout | DIRECT scoped work/invalidations; independent optimization only after profiling | Merged bounded work reused; reproduce current populated deadline failure before another optimization; exact descendant/generation parity | P03/P14 |
| FR-007 rolling CSV identity | Independent defect fix already merged; preservation required | New-code hash/row semantics and old identity compatibility are regression cases; retained 1,491 conflicts are not proof of current recurrence | P02/P14 |
| FR-008 canonical fixture collision | PARTIAL; AUTHENTIC FIXTURE EVIDENCE | Explicit source/season/orientation/reschedule/ID-reuse proof; one accepted representative without false merge; distinguish already resolved cluster | P02/P08 |
| FR-009 unmatched observations | DIRECT bounded reprocessing, PARTIAL source proof | 10,873 FotMob + 2,097 PitchAPI latest finished unbound candidates; exact mapping/season/basis qualification, no fabricated success from execution | P03/P09 |
| FR-010 quota/retry/history scopes | DIRECT technical scheduling; PARTIAL access | Separate deterministic block, quota cooldown, live deferral and retry; expired worker fence cannot publish; actual source permission retained | P03 |
| FR-011 missing registered originals/manifests | PARTIAL prevention; AUTHENTIC EVIDENCE/EXTERNAL/OWNER | Complete checksum-exact restoration or retain explicit unresolved lifecycle; new websites cannot replace missing original hash; no last-copy deletion | P01/P11/P12 |
| FR-012 full V2 parity | PARTIAL; independent existing PHASE GATE/OWNER | Five execution-success/BLOCKED reports do not pass full canonical/serving/report comparisons; original Phase 35 then 36 gates remain | P17/P18 |
| FR-013 report backlog | DIRECT scoped work; independent throughput evidence | Reuse bounded workers and generation fencing; old 148,095 count is not current; measure pending/oldest current generation and completeness | P03/P14 |
| FR-014 StatsBomb legacy origins | PARTIAL; AUTHENTIC RELATIONSHIP/OWNER | Forward native-method compatibility is merged but not applied at B0; old independent proof blocks remain; no legacy rewrite/admission from method name | P08/P09 |
| FR-015 broader markets/player data | PARTIAL contracts; EXTERNAL/SOURCE/SCIENTIFIC AUTHORITY | Source/player/exposure/settlement proof plus independent model/evaluation/promotion; 53/14 prior diagnostic families not new markets enabled | P06/P08/P16 |
| FR-016 quarantines/conflicting results | PARTIAL; AUTHENTIC EVIDENCE | Source-specific correction/identity/basis proof; retain exclusions and immutable disputed claims until qualified | P02/P08/P09 |

No FR issue is automatically solved by a broker, SSE or a new schema. Ready
source-independent code investigation, existing bounded technical recovery and
checksum search can continue under their own prior authorization. This task does
not start those actions. Proposed universal reingestion, a second scheduler,
duplicate matching library or new settlement engine is redundant; qualified
source acquisition, exact identity proof, artifact recovery, full parity and
scientific gates are not made redundant by the redesign.

## Discrepancy register and recurring audit

Machine-readable details are in [registers.json](registers.json). These source-bound
summaries classify evidence instead of rewriting historical reports to agree.

| ID | Class / severity | Evidence and resolution |
| --- | --- | --- |
| UD-001 | HISTORICAL_DIFFERENCE / low | Companion/older task references pending PRs; GitHub confirms #178/#179/#182 merged. Preserve dated source; use combined baseline |
| UD-002 | MISSING_EVIDENCE / high | Running `/version` unknown while tested Git SHA is known. Existing ldflags path exists; separately deploy/verify exact build before adoption |
| UD-003 | IMPLEMENTATION_MISMATCH / high, release-specific | Merged `202611100200` absent in operating DB. No rollout claim; require approved pre-writer migration/restore plan |
| UD-004 | MISSING_EVIDENCE / high | Four stored historical RUNNING rows have no valid lease. Effective worker status differs from a durable state label; show expiry/recovery instead of active execution claim |
| UD-005 | IMPLEMENTATION_MISMATCH / medium, target-only | Post-match CLI/work exists but operating rows/schedule absent. Plan monitored scheduler; no current continuous-learning claim |
| UD-006 | FALSE_POSITIVE / low | Retained provider LINEUPS resources versus zero qualified context rows are different populations; no fabricated source contradiction |
| UD-007 | FALSE_POSITIVE / medium | `event_observations.n_live_tup=0` versus 2,609,128 exact rows is stale estimation; never delete based on estimates |
| UD-008 | MISSING_EVIDENCE / critical | Prior exact source/model/manifest gaps still constrain full recovery; search authentic backup, preserve blocker/disposition |
| UD-009 | FALSE_POSITIVE / medium | 281 same-key groups are candidates; example has accepted common representative. Do not submit another merge or claim 281 duplicate public fixtures |
| UD-010 | HISTORICAL_DIFFERENCE / low | MC Oran old SCHEDULED claim versus fresh verified canonical FINISHED 0–0. Preserve dated report and add current observation |
| UD-011 | UNRESOLVED_SOURCE_CONFLICT / high | MC Oran FotMob mapping/native kickoff/resource binding remains inconsistent and API marks conflict/partial; exact new proof required, no guard removal |
| UD-012 | HISTORICAL_DIFFERENCE / low | Integration aggregate exit 2 and later passing corrected focused tests are both true; never relabel earlier aggregate PASS |
| UD-013 | IMPLEMENTATION_MISMATCH / medium, target-only | Current External Predictions API/UI paginated; proposed requirement is unpaginated selected scope. P06 delivers compatibility, not a data repair |
| UD-014 | MISSING_EVIDENCE / high | Full required V2 parity not accepted; SUCCEEDED/BLOCKED and absent operating cutover are distinct truth |
| UD-015 | SUPERSEDED_INFORMATION / low | Older ordinary acquisition approval restrictions superseded by standing source policy, while this task's explicit no-acquisition limit applies |

Each future resolution binds conflicting references/cutoffs, authority, root
cause, confidence, exact affected IDs and dependencies, required authorization,
regression test and status. Incremental audits follow changed source/decision/
work/artifact IDs, migration checksums, OpenAPI/TS DTO fixtures and runtime version;
use existing project-status/architecture/schema/CI checks. Full historical scans
are occasional bounded reconciliation, not each UI read or timer tick. Generate
registry/schema reference excerpts where useful; never auto-rewrite owner ADRs or
immutable reports. Safe docs corrections are dated supplements; canonical changes
use existing prospective decision/replay owners in a separately authorized task.
