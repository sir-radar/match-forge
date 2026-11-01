# MatchForge Architecture

## Purpose

This document records durable system boundaries, language ownership, storage ownership, and dependency direction across MatchForge.

It does not replace `PLAN.md`, schemas, migrations, model contracts, current project-status records, or resolved owner/Wayfinder decisions.

## Implementation Status

This document defines architectural ownership and allowed dependency direction. It does not imply that every component described here is currently authorized, implemented, production-ready, or exposed through an API.

Current implementation, gate, and authorization state must be read from the repository's tracked project-status authority and the applicable resolved owner/Wayfinder decisions and evidence.

Where these sources disagree, the newer explicit owner/Wayfinder decision takes precedence over a stale architectural or planning checkpoint.

### Automated dependency boundaries

`make architecture-check` runs as part of `make check`, which is the check command used by CI. It checks that identity, canonical-resource and observation modules do not import provider adapters; features do not import raw stores or provider normalizers; forecasting does not import provider adapters or access raw provider payload fields; and provider adapters do not import forecasting. The general experiment runner cannot directly import protected evaluation readers or database clients. Frontend source cannot import provider-native parser schemas. Go and Rust source cannot add named model-fitting functions or known model-fitting library dependencies. Python worker classes and Go ticker schedules must have registered shared-work contracts; registered production worker paths must retain their Work Orchestrator calls and SQL adapters.

These source checks guard direct dependencies and known entrypoints. They do not verify deployed production routing, Phase 35 cutover, or Phase 36 scheduler retirement.

### Architecture V2 baseline

Architecture V2 starts from the final R3 head, `c46fa44f4fdae16f0dbff7c4dd7cd8a19f3dc365`, merged through PR #167. Phase 0 preserves the existing runtime before any schema or worker cutover. The remaining phases require implementation and acceptance evidence.

Run the capture from the repository root with the existing `.env` exported and `scripts/toolchain.sh` loaded:

```sh
uv run --locked python -m scripts.capture_architecture_v2_baseline \
  --output .local/remediation/matchforge-architecture-v2/new-baseline \
  --fixture-date 2026-10-14 --fixture-date 2026-10-15 --fixture-date 2026-10-16 \
  --cutoff 2026-10-15T23:29:06.806401Z
```

The output directory must not exist. The tool shares an exported PostgreSQL snapshot between a read-only repeatable-read transaction and the Compose PostgreSQL container's `pg_dump`. It retains a restorable database archive, schema, migration checksums, primary-key and row-hash inventories, current projections, historical cutoff hashes, source registrations and verified source bytes, champion checksum, history coverage, queue state and observable locks. Database row contents stay in the local backup; row inventories contain keys and hashes. API captures are separately timed observations because live sync remains enabled.

Missing or unverifiable legacy source bytes are reported individually and produce `PASS_WITH_WARNINGS`; they are never silently repaired. The dump preserves their registrations. An interrupted capture remains `INCOMPLETE`. Keep all output under ignored `.local/` storage, with the same access restrictions as the original data, and leave old R3 evidence untouched.

Restore `database.dump` using PostgreSQL 18's `pg_restore --exit-on-error --no-owner --no-acl` into a new, empty database. Never restore over the operating database. Then select the restored database through `DATABASE_URL` and run:

```sh
uv run --locked python -m scripts.capture_architecture_v2_baseline \
  --output .local/remediation/matchforge-architecture-v2/new-restore-verification \
  --verify-restored-baseline .local/remediation/matchforge-architecture-v2/phase-0
```

Verification requires exact table and historical-cutoff hashes, the original dump checksum, and intact archived source bytes. Current-time views are captured for reference rather than compared at a later wall-clock time. A successful capture alone does not prove a successful restore or completion of Architecture V2.

### Versioned resource observations

The typed contracts in `football.contracts.observations` have a checked-in JSON Schema at `schemas/contracts/resource-observations-v1.schema.json`. Each resource has its own fields. Fixture scheduling excludes scores; results, lineups, availability, events, shots, xG, named statistics, standings and odds remain separate. An absent resource produces no observation. Within an observed resource, `null` means unreported or unknown; zero and false remain observed values. Unknown source values require an explicit mapping or quarantine before construction.

Native identifiers remain scoped to the named provider. A missing native ID requires a source-record locator, such as a CSV row; names never create canonical IDs. Canonical references remain null until independently resolved. Every observation binds a registered source snapshot, resource and byte checksum, and records separate provider-schema, adapter, normalizer, observation-contract and optional resolution versions. An unknown provider schema or unresolved identity stays explicit rather than acquiring a fabricated version.

`observed_at` records when the source was observed, `acquired_at` matches the registered raw resource, and `known_at` records when MatchForge could know the observation. Knowledge cannot precede observation or acquisition. Optional `event_time`, `provider_updated_at` and the half-open `[valid_from, valid_to)` interval describe football/provider time independently. None of these fields alone establishes eligibility for a historical forecast; the existing point-in-time contracts continue to govern it.

Canonical UTF-8 JSON sorts object keys, normalizes timestamps to UTC and integral numbers to integers, rejects nonfinite values and duplicate fields, and ends with a newline. Its SHA256 determines immutable observation identity. A correction, changed knowledge time or changed processing version creates a new observation. The schema fingerprint is immutable for each contract version.

`football.observations.storage.ObservationArtifactStore` writes immutable typed JSON files and registers only provenance, time, version and file metadata in PostgreSQL. This shared registry contains no EAV domain values. Source provenance is checked against raw registrations, and SQL rejects updates/deletes to artifacts and contract versions. File publication precedes registration; rollback can leave an unregistered immutable file, and an identical retry converges. The caller owns the transaction. These shadow artifacts do not admit identity, replace existing serving/history tables, or alter forecasts.

`prepare` seals and publishes observation bytes without database access.
`register_prepared` checks their expected path, checksum, size and configured
root, then registers metadata without filesystem access. Shared work can prepare
files before entering its bounded publication transaction. The existing `publish`
method composes both operations for compatible callers.

With `scripts/toolchain.sh` loaded, `uv run --locked python -m football.observations.cli schema` emits the schema. The `validate INPUT` command checks a document; `store INPUT --data-root PATH` registers it using `DATABASE_URL`. Use a migrated shadow database until the later parity and cutover gates pass.

`PointInTimeRepository.resource_observation_ids_at` reads this registry by exact contract and provider with an explicit `knowledge_cutoff`. It returns all immutable observations whose `known_at` is at or before that cutoff, ordered by knowledge time and observation ID. Provider update times and earlier football validity never backdate MatchForge knowledge. Later corrections add observations; the reader preserves earlier evidence and does not choose a conflict winner or latest normalizer.

An explicit `football_cutoff` restricts history to observations with a reported `event_time` strictly before it, excluding simultaneous, future and unknown event times. A requested `valid_at` requires a reported validity start and applies `[valid_from, valid_to)`; a null end is open. Without these filters, the query describes source facts known at the cutoff, including known future schedules or announcements. Returned IDs can be loaded separately through `ObservationArtifactStore`; they do not establish canonical identity, model-history eligibility or a sealed forecast context. The existing modelling and serving paths remain active during shadow migration.

### Provider-native records

`football.providers.native` describes each provider's JSON records independently. FotMob keeps numeric/string IDs and camel-case fields; PitchAPI keeps its own string IDs, status vocabulary and snake-case fields. API-Football models its own fixtures, teams, lineups, injuries, statistics and standings. football-data.org retains its v4 fixture, score and standing structures. OpenFootball retains source names and file/row identity rather than inventing team IDs. Football-Data.co.uk continues to use `FootballDataUkCsvRecordV1` and its receipt-verified CSV parser, preserving string values and empty cells.

`native_record(Model, payload)` checks required fields and native types, rejects nonfinite/non-JSON values, and returns an independent typed copy. It preserves additive fields, unknown status values, string spelling, timezone text, numeric representation, omitted fields and explicit nulls. Football meaning and canonical identity belong to subsequent normalization/resolution. These are field-shape readers, not assertions that an API resource is enabled, complete or historically eligible. Existing acquisition and serving paths remain active during shadow migration.

For offline inspection, `uv run --locked python -m football.providers.native.cli --model FotmobFixture INPUT` returns the parsed native record with the exact input-byte SHA256. Duplicate JSON keys are rejected. The static model list selects a decoder; runtime provider availability belongs to the scoped runtime capability registry.

### Provider acquisition capabilities

`football.providers.sources.contracts` defines narrow fixture, result, competition, team, player, coach, lineup, availability, event, shot, xG, statistic, standing and odds ports. Implementations expose only acquisition methods backed by their existing clients. They return `ProviderPayload`: original immutable bytes, provider/resource identity, acquisition time, media type and available revision/cache/quota metadata. Football fields stay in the native payload until resource-specific normalization. A method's presence does not prove scoped coverage, access approval or historical eligibility.

HTTP implementations reuse the existing guarded FotMob, PitchAPI, API-Football and football-data.org clients. Queries and native season labels stay inside this boundary; football-data.org requires an explicit competition scope, and API-Football's current-only catalog filter remains in the resource key. FotMob's detailed capabilities share its physical match-details response; PitchAPI's xG capability uses its shot resource. Preserve those original bytes rather than creating synthetic provider responses. Coach and odds ports have no standalone acquisition implementation at this stage.

File implementations read existing Football-Data.co.uk receipts and pinned OpenFootball Git objects; they neither reacquire historical sources nor trust mutable working files or file modification times as knowledge evidence. StatsBomb retains its existing commit pin. These ports are for shadow ingestion; current production entry points remain active until the parity and cutover phases. Network work must finish before the later normalization/persistence transaction begins.

### Runtime resource capabilities

`CapabilityRegistry` persists append-only `DecisionRecordV1` evidence in
`provider_resource_capabilities`. Its exact key is provider, resource type,
provider-native competition key and native season key. Null scope keys describe
an explicit catalog request; they never act as wildcards or permit fallback to
another competition, season or resource. Static `ProviderCapabilityRegistryV1`
declarations remain compatible configuration, not runtime availability evidence.
No production states are populated from roadmap documents or method presence.

Each state records availability, inclusive historical date bounds, freshness in seconds,
expected completeness as an optional fraction, entitlement and retention
findings, rate limit per minute, timestamp precision, identity quality and exact
adapter/normalizer versions. Null metadata means unknown. Completeness is an
expectation, not measured canonical coverage. Identity-quality descriptions do
not grant identity admission. These records do not override provider terms,
credentials, existing quota budgets or acquisition policy.

`prepare_capability` publishes immutable evidence bytes before registration.
Registration verifies the prepared bytes, records database publication knowledge
and requires the current scoped predecessor. Corrections retain prior states;
database constraints prevent roots or successors from forking. `at` requires an
explicit knowledge cutoff. `plan` uses the latest committed scoped transition,
returns its decision ID, and permits only registered `SUPPORTED` or `PARTIAL` scopes with matching
processing versions and compatible requested dates. Other states block calls
until a new evidenced transition changes them; no retry interval is invented.
A database clock rollback cannot revive an older permission during acquisition.

`CapabilityRegistry.acquire` applies that plan before invoking a narrow provider
source. It requires an idle database connection and finishes the planning
transaction before provider I/O. Existing clients retain their byte, access,
quota and retry controls. The new path is exercised in shadow and test databases;
current serving and synchronization remain active until the cutover gate.

### Provider resource authority

`football.providers.resource_authority.AuthorityRegistry` records authority
assignments for an exact provider/resource/native competition/season scope and
an explicit half-open effective interval. Each assignment has a stable metadata
UUID; revisions preserve that ID and scope while correcting its interval, tier
or qualification state. The ID describes a policy assignment, not a football
entity. Prepared immutable `DecisionRecordV1` artifacts retain qualification
source references, decision time and effective time separately.

Authority tiers and qualification states are explicit owner labels. This
registry does not invent a global tier order, infer qualification from a
capability, or assign authority from static provider roles. Lookup returns all
applicable assignments, including negative qualification states and overlapping
claims, for the caller's approved scoped resolution policy. It never chooses a
conflict winner or changes source observations.

`at` requires both effective time and knowledge cutoff. It selects each
assignment's latest state known at the cutoff before applying its effective
interval. A correction that moves an interval cannot revive an older grant.
Publication knowledge starts at database registration; backdated effective time
does not change earlier knowledge. Revisions and artifacts are immutable, and
database constraints prevent assignment forks or scope relabeling.

Authority does not establish football identity. Canonical candidates still
require independent identity-owner bindings; an authority decision cannot be
used as an identity decision. Existing production resolution stays active until
the parity and cutover gates. No authority assignments are inferred during the
shadow schema upgrade.

### Resource normalization

`football.providers.normalization.pipeline.normalize_resource` verifies the registered source checksum and dispatches an explicit provider/resource pair. Fixtures and results, participants, lineups, availability, events, shots, xG, named statistics, standings and retained CSV odds produce separate observations. Missing resources produce no measurements. Unknown values and unsupported fields produce structured findings; a bad record does not replace valid sibling records. Repeated statistics may corroborate each other, while contradictory duplicates quarantine the affected measurement. This decoder registry does not establish runtime provider availability.

V2 contracts in `football.contracts.observations_v2` add `EntityReferenceV2.source_record_key`. This identifies an exact field within the observation's source resource when a provider supplies no ID. JSON pointers, CSV record/column locations and ZIP member locations preserve anonymous participants without treating names or generated IDs as provider identity. V1 schema fingerprints and serialized bytes remain unchanged; both versions use the existing immutable artifact registry. Match-specific inputs must agree with native fixture IDs or registered request scope. A lineup coach does not establish a global manager tenure.

Provider update timestamps retain their declared timezone. A local timestamp without a verified timezone stays in raw evidence and a finding; normalization does not assume UTC. FotMob/PitchAPI coordinates remain unnormalized until their coordinate frame is verified. StatsBomb shots reuse the existing 120×80 coordinate contract. Third-party predicted lineups remain `UNKNOWN`, rather than acquiring MatchForge's `PREDICTED_REPEAT_XI` label. Football-Data.co.uk statistics remain aggregates, and odds remain separate from model features.

The offline command below reads registered retained bytes and writes an immutable report containing source lineage, processing versions, output identities and findings. It performs no provider requests. With `--persist`, the existing work registry fences one NORMALIZATION job per report hash, binding the source, feature, native scope and processing versions. Files are prepared before the publication transaction; observation registration and work completion commit together. Identical retries reuse succeeded work and the original registered acquisition/observation clocks. File publication may leave safe orphan files after rollback. Reports describe normalization outputs, not canonical admission or historical eligibility. Use the isolated shadow database until the cutover gate passes.

```sh
uv run --locked python -m football.providers.normalization.cli \
  --source-resource-id RESOURCE_UUID --resource shots --fixture-native-id NATIVE_MATCH_ID \
  --data-root .local/football-data --artifact-root .local/shadow-observations --persist
```

`football.providers.data_audit` reads a repeatable, read-only diagnostic snapshot.
With `--data-root`, it verifies registered observation bytes before counting
fields by provider, contract and period. Known values, numeric zero, missing
values, source resources and observation revisions remain separate. Player
coverage compares distinct native references with recorded mapping claims; it
does not admit those claims or infer identity from duplicate names. Existing
participation and position stints establish fixture/season evidence, while
continuous membership, transfers and historical eligibility require their own
proof. Unknown qualification and expected coverage remain null.

Canonical resolution accepts V3 rich statistics and shots, period scores,
referee references and dated team ratings through the existing identity-owner
checks. Period and score basis, rating date/system and V3 semantic version stay
in the comparison context. An assisting player, assist event or referee requires its own
reference binding. No new identity owner or admission route is created.

### Rebuildable fixture projection

`football.fixture_read_model` materializes the current columns of
`product_serving_fixtures`, including exact fixture IDs, identity status, score
basis and availability. The unique fixture index and date/competition index
support direct serving reads without re-running the canonical view's identity
and competition lookups for every request. This is a disposable projection. It
does not create identities, resolve conflicts or provide historical PIT inputs.
Existing competition, forecast and team-context stores remain in use; additional
projections require an actual consumer.

The migration creates the projection without data. Reading an unbuilt projection
fails explicitly. Rebuild an isolated shadow with:

```sql
BEGIN;
REFRESH MATERIALIZED VIEW football.fixture_read_model;
COMMIT;
```

Refresh takes PostgreSQL's exclusive materialized-view lock and replaces the
projection atomically. Rollback retains the prior projection. Source changes
become visible in the cache only after another explicit refresh. Refresh performs
only database work, with no provider or file I/O. Scheduled refresh publication
must join the authoritative work engine before production cutover.

`product_serving_fixtures` remains the production fixture-list baseline until
parity is proven and controlled cutover is authorized. Detail references and
historical reconstruction continue using the original fixture IDs and dated
contracts. A proven duplicate can be absent from the list projection while both
its member and representative IDs remain available in the original tables.
Discarding or rebuilding the projection cannot delete those identifiers.

### Shared work orchestration

`football.work_items` and `work_dependencies` define the shared durable scheduling
contract. SQL functions own the state machine, claim ordering, lease checks,
retries, cancellation and completion. `football.work.storage.WorkRegistry` is a
thin Python worker adapter; Go submissions can use the same SQL contract. Domain
inputs remain in their existing stores or specific detail tables. The core row
does not contain provider payloads, model state or football decisions.

A work type and semantic key identify one immutable logical input. The request
binds its input SHA256, priority, maximum attempts, retry configuration, parent
and dependencies. Reusing the key with different bindings fails. An identical
request returns the existing work ID and preserves its current retry deadline
and outcome. Source generations, cutoffs and processing versions belong in the
semantic key when they change the logical input. `generation` in the scheduling
row is a monotonic lease/fencing epoch, not a replacement for source generation
or either football/knowledge cutoff. Terminal success, failure and cancellation
cannot be reopened.

`enqueue` joins its caller's database transaction. Publish the domain change and
enqueue its downstream request in that same transaction; rollback removes both.
Dependencies and the optional lineage parent must already exist. Dependencies
are sealed before enqueue returns and cannot subsequently change. Edges only
point to already sealed items, so concurrent construction cannot create cycles.
A deferred constraint requires each newly inserted item to be sealed before
commit. Dependent work is claimable only after every prerequisite succeeds;
failed or cancelled prerequisites do not silently qualify their dependents.

Claims select one ready item by priority, availability and work ID using
`FOR UPDATE SKIP LOCKED`. Every claim has a new token and fencing epoch. Claims,
heartbeats and control operations require an idle connection and finish their
short transaction before returning. Lease duration, attempt limit and retry
policy are explicit caller inputs. All lease and retry clocks use database time.
An expired attempt can be replaced after its configured backoff; an exhausted
final attempt fails instead of remaining running forever. A claim cleans up at
most one exhausted attempt and can still return other runnable work in the same
bounded transaction. Leases and scheduled availability must be finite.

The common retry classifications are `RETRYABLE`, `NON_RETRYABLE`,
`BLOCKED_EXTERNAL` and `CANCELLED`. SQL calculates capped exponential backoff
without overflowing on large attempt counts. Retry-After and provider cooldown
can delay the next attempt further. External blocks require explicit release;
release cannot bypass the attempt budget. Existing provider access and quota
policies still apply.

Acquire the required canonical coordination locks before entering
`WorkRegistry.publication`. Perform provider/file access and expensive computation
beforehand. The context verifies and locks the exact live lease, permits only
database publication work, then verifies the deadline and completes with an
explicit result checksum in the same transaction. Exceptions or a lost lease
roll back the published rows and completion together. The work-row lock
serializes publication, cancellation and replacement. Cancellation clears lease
rights before recording its terminal state.

Public fixture-context reports use a durable per-fixture refresh queue. Fixture,
eligible history, identity, coach and lineup changes enqueue affected fixtures;
the Go service schedules a bounded Python projection job in a separate public-report lane.
Each minute the worker can attempt at most 32 scopes per report kind. Half of
context capacity is reserved for oldest eligible backlog work; the rest prefers
fixtures from the preceding 24 hours through the next 72 hours. Attempts rotate
by last-attempt time, and unsuccessful scopes wait at least one minute. This is
a scheduling policy, not a measured production latency guarantee. Performance
and comparison work is enqueued transactionally by forecast, fixture/result,
selection and fixture-resolution changes. All seven Performance horizons are
queued independently. Successful completion still requires the captured
generation and the current source fingerprint; failures remain pending with
a last error and do not abort sibling scopes. The API serves only immutable
reports whose source fingerprint still matches current eligible context. While
a refreshed report is pending, the context endpoint reports temporary
unavailability instead of serving stale form.

The shared engine and Phase 17 queue adapters run on the isolated shadow path.
Operator runs and provider-history scopes retain their existing control/detail
records behind SQL adapters. Bulk history and pending forecast workers use shared
work directly. The original production checkout remains frozen until the
separate cutover gate; this migration does not authorize production cutover. Global lock ordering, the full adversarial concurrency matrix
and controlled production cutover remain their own required gates.

Compatibility workers can pass explicit work IDs to `WorkRegistry.claim`.
The shared SQL claim operation applies that set to both runnable selection and
exhausted-lease cleanup. An empty set claims nothing; unrelated work retains
its state. The existing unfiltered SQL entry point keeps its signature.
`WorkRegistry.progress` fences one database step while keeping work running.
It checks ownership before and after the step and joins an existing caller
transaction when present. Canonical coordination must be
acquired first, and provider/file I/O stays outside that transaction. Final
`publication` still commits domain writes and completion atomically.
Queue-specific adapters delegate claim, expiry, retry and completion to this
state machine. Controlled execution tests compare legacy outcomes before the
independent history scheduler is removed.

The retry policy can specify a fixed delay after lease expiry independently of
acknowledged-error backoff. A missing value preserves the original shared
backoff behavior. Bulk history requests configure immediate expired-lease
recovery while retaining their existing 60-second exponential error backoff,
capped at one hour and adjusted for attempts made before registration.

`register_history_request` binds a pending legacy history request, identified by
its job UUID and queued time, to immutable shared work. The association retains
provider competition, season and the prior attempt count. Registration locks
unclaimed shared work before its domain row and rejects previously claimed
work. Registration and the association commit together; a busy or changed queue
row rolls back both. Registration leaves the original queue row and cooldown
intact and rejects active legacy jobs. If another worker registers and claims
that same request while registration waits, the waiter skips it without
interfering with its ownership.

Concurrent enqueue of the same deterministic work identity handles conflicts
on either the primary or semantic unique index. Existing input, policy and
dependency checks still reject a primary identity used by different semantics.

History workers can select one request through `claim_history_request` and
complete or fail it through the corresponding shared-history operations. These
control calls own short transactions and require an idle connection. Shared
work decides eligibility, expired ownership, retry delay and attempt limits;
the SQL adapter projects status, attempts and deadlines into the matching
legacy request atomically. A busy detail row rolls back a tentative claim or
expired-attempt cleanup without publishing partial failure.
Ownership is checked after projection, so waiting beyond the lease rolls back
completion or failure. Repeated terminal claims leave queue detail unchanged.
`HistorySyncWorker` renews ownership between bounded provider/file operations and
short SQL publications. Raw files keep their existing paths, bytes and source
identities. An immutable result receipt binds the request hash, source snapshots,
resource checksums and result counts. Cancellation or expiry prevents subsequent
publication. Legacy recovery applies only to requests without shared bindings.

`product_provider_scope_work` associates current league/season detail with shared
work without changing retained scope columns. Claims use shared lease tokens;
explicit heartbeats renew them between committed history rows. Each publication
checks ownership before commit. Failures and deferrals use shared retry deadlines,
including the existing one-hour failure delay and provider retry-after deadline.
Shared cancellation projects a failed scope with an explicit cancellation reason;
an operator refresh creates a new request rather than reviving cancelled work.
Successful current seasons create new work when their freshness interval expires;
explicit refresh retains its existing eligibility and cooldown rules.

Operator run transitions delegate to shared work through SQL triggers. Existing
lanes, command launch, logs, summaries and manual retry-as-new-run behavior remain.
Shared root cancellation serializes with child publication through the existing
run-control fence. In-flight pre-migration controls may drain through their
compatibility path; all newly inserted runs receive shared work atomically.
Expired-run cleanup commits before a new run is submitted, preserving control
lock ordering and the lane uniqueness constraint.

Pending forecast work binds the captured fixture generation. Updates coalesce in
the existing detail row; completion records only the captured generation and a
hash of the existing forecast receipts. Busy detail rows return shared work to
retry without clearing pending generations. A superseded generation is cancelled;
the newer generation remains pending. Canonical ownership, work ownership
and completion join the caller's transaction. Commit or roll back each refresh
batch before beginning another batch, as required by transaction lock ordering.

### Work metrics

`python -m football.product.cli work-metrics` reads `football.work_metrics` in a
read-only transaction and emits Prometheus text. The five state gauges describe
all registered work, including expired items still marked running. Every work
type has explicit zero samples. The only label is the bounded `WorkType` enum;
fixture IDs, work IDs, owners and semantic keys never become metric labels.

SQL observes attempts for Python and direct SQL workers alike. Claim latency is
time after the configured ready deadline, including dependency waits; execution
duration ends at completion, cancellation, failure or the expired lease deadline.
Both durations expose summary sums and counts without invented histogram bounds.
Retries count replacement claims. Lease expirations count expired attempts when
a committed state transition observes them. Attempt counters start with this
migration; existing work is neither reconstructed nor rescheduled for metrics.

Fencing rejections and deadlocks in shared coordinator/work-row lock functions
advance PostgreSQL sequences, so rejected transactions retain their error count.
Deadlocks in unrelated SQL are outside this counter. Read-only transactions skip
these increments to preserve their original failure behavior. Restoring a backup
also restores its counter position; these are operational metrics, not audit logs.

`work_lock_wait_duration` measures acquisition elapsed time, including SQL overhead,
for the shared advisory coordinator and work-row lock functions. Samples commit
with their transaction; rollback and read-only coordination exclude those samples.
Each PostgreSQL session writes its own accumulator, avoiding a global metrics row
lock. Attempt observations also join the work transaction and roll back with it.
The exporter reads these stores without taking domain locks or changing counters.

### Worker transaction boundaries

MVP fixture and context acquisition commits the preceding database step before
another provider request. Bulk history workers commit and recheck shared ownership
between individual result imports. Provider ingestion loads retained geography
before identity coordination. Identity admission and reviewed corrections prepare
retained bytes before locking, then recheck registered evidence and mapping inputs
under coordination. A changed prepared input aborts the operation and requires a
fresh preparation; missing or tampered bytes keep their existing failure behavior.

Pending forecast refresh captures a bounded set of source generations and computes
from the existing point-in-time inputs before claiming canonical rows and shared
work. Publication requires the captured generation and fixture context to remain
current. An upstream change during preparation stays pending for another refresh.
Database results, captured-generation completion and downstream enqueue still
commit atomically. Runtime full refresh uses `commit_batches=True`, with each
fixture publication in its own transaction. The caller-owned refresh mode retains
its existing transaction contract for short composed operations.

OpenFootball and Football-Data.co.uk backfills own an idle connection and commit
individual match imports before reading or downloading another resource. CSV/archive
parsing finishes before registering a successfully parsed resource.
`product_history_resource_imports` records whether an import has completed; it
contains no claim, lease or retry policy. Resource registration and a pending
import record commit together. A partially imported resource remains eligible for
replay, and deterministic match identities make repeated rows converge. Only a
complete import becomes cached. Retained resources without an import record keep
their established cache behavior. Transaction-owning imports, full refresh and
provider scope claims reject borrowed transactions without committing their work.

### Transaction lock ordering

The shared ordering functions and publication checks enforce one class/key
order across significant current mutation paths. Controlled regressions cover
legacy identity, work references, fitted artifacts, forecasts, worker fences
and queue batches. The Phase 15 shadow gate preserves all 111 retained tables
and the exact fixture projection.

`football.storage.locks` and the SQL functions introduced by
`202610180800_transaction_lock_order.sql`, extended through
`202610181700_history_work_registration.sql`, order blocking coordination requests
by class, then exact key in C/Unicode order:

| Class | Order |
| --- | ---: |
| Worker control | 5 |
| Source | 10 |
| Identity | 20 |
| Scoped identity | 25 |
| Competition | 30 |
| Fixture | 40 |
| Work | 50 |
| Work domain detail | 51 |
| Dataset | 55 |
| Validation | 56 |
| Lifecycle | 57 |
| Kickoff | 58 |
| Labels | 59 |
| Feature | 60 |
| Model artifact | 65 |
| Publication | 70 |
| Evaluation | 75 |
| Promotion | 80 |

Declare a transaction's required scopes together through `acquire_locks`.
Already-held keys can be reentered. A new lower request fails before waiting;
reentry cannot change the key's class or hash convention. Existing 64-bit and
legacy 32-bit advisory hashes are retained explicitly. Ordering state is local
to the transaction and follows savepoint rollback. Lock-order errors use SQLSTATE
`MFL01` and remain distinct from lost work leases. Locks require a transaction
that stays open through the protected mutation.

`lock_fixtures` derives the existing parent competitions, acquires every
competition before its fixtures, and locks IDs in sorted order. It creates no
identity or fixture rows. If a fixture changes competition during acquisition,
the transaction must retry. `wait=False` defers busy scopes and rolls back all
locks and ordering entries acquired by that call; it does not leave partial
claims. Work publication records its blocking work-row lock, so acquiring a new
identity, competition or fixture scope afterward fails and rolls back its
publication writes. Acquire those scopes before entering publication.

Work publication uses `FOR NO KEY UPDATE`: lease and status writers remain
excluded, while child work can reference immutable parent/dependency keys
without waiting for publication. Operational fixture updates acquire the
existing identity admission lock before locking fixture rows, including
finished-result updates.
Bulk fixture, standings and historical-result writers acquire that same
existing identity lock before canonical mutations. Admission, correction and
fixture-crosswalk callers use the shared guard. The forward SQL migration
`202610181000_identity_lock_order.sql` also guards direct admission and history
qualification without changing their eligibility predicates or decision clocks.

Legacy forecast refresh defers busy work rows with `SKIP LOCKED` after acquiring
its competition/fixture rows. Deferred work stays pending; it is excluded from
that transaction's completed generation. This prevents history's existing work
lock from making refresh wait while holding canonical rows.

Fitted-artifact registration and publication acquire model scopes before
forecast publication. Multi-model batches order exact fit-specification keys;
artifact identity, state and returned model-family order stay unchanged.
The scientific evaluation CLI opens an autocommit connection so explicit
publication transactions end between walk-forward batches. Direct gate callers
must supply that same mode; the runner rejects an implicit outer transaction
without committing caller-owned work. This does not change scientific gates or
authorize running a frozen evaluation.

Legacy run and history-scope ownership checks acquire control fences before
blocking domain or work locks. `authorize_worker_publication` preserves the
existing shared run lock, heartbeat windows and scope-token checks. A failed
nonblocking domain request retains any control fences it already acquired.
Run creation, heartbeat, cancellation and deletion use separate control
transactions; a statement guard rejects mixing them with publication before
run rows can be locked. This prevents shared-to-exclusive upgrades and run-row
cycles while allowing independent heartbeat connections.

Legacy history recovery and enqueue use work-class keys
`history-queue:<provider_competition_id>:<season>` in C/Unicode order. Recovery
commits before enqueue. Enqueue snapshots pending backlog keys before taking
row locks, then processes that set and requested keys in one order. Original
request-order database timestamps retain queue priority; existing pending retry
state stays unchanged. Jobs arriving after that snapshot remain durable and
claimable, and claims attach the current run. Provider-scope refresh locks its
eligible rows by provider, competition and season in C order before updating.
Single-job claims use `SKIP LOCKED` and commit before provider calls; completion
and retry update one owned queue row and commit before further domain work.

Dataset, validation, lifecycle, kickoff and label registration follow their
existing input dependencies. Elo history uses the model class. Forecast,
evaluation and promotion writers use the later publication classes. All
Python advisory coordination requests now use this shared contract, retaining
their previous exact keys and hash namespaces. Forecast batches acquire keys
in semantic-hash order and return the original target/model-family order.

Phase 16 scopes pure history qualification by competition. It takes a shared
lock on the existing `product-identity-admission` key, then exclusive class-25
`history:competition:<competition-id>` keys in sorted order. Only competitions
with retained history rows need a scoped lock. Unrelated competitions can
qualify concurrently; overlapping qualification remains serialized.

Fact-changing ingestion, correction, source-validation and resolution paths
retain exclusive identity coordination because their effects can cross
fixtures, mappings and competitions. An already held exclusive identity lock
covers its qualification fan-out without adding per-match locks. Shared mode
cannot upgrade to exclusive mode inside the transaction; callers must declare
exclusive mutation first. Failed nonblocking requests restore the prior ledger,
and existing SQL lock entry points retain their original signatures.

The qualification predicates and decision clocks stay unchanged. The writer
remains volatile, so its query after coordination can observe committed prior
decisions under PostgreSQL's [function snapshot rules](https://www.postgresql.org/docs/18/xfunc-volatility.html).
Existing queue migration, full-route adversarial tests and controlled production
cutover remain required later gates.

## System Flow

```text
approved providers
        ↓
provider adapters
        ↓
immutable raw acquisition
        ↓
validation and normalization
        ↓
MatchForge identity resolution
        ↓
cross-provider reconciliation
        ↓
trusted publication or quarantine
        ↓
point-in-time dataset construction
        ↓
statistical models and feature systems
        ↓
match parameter generation
        ↓
optional Rust simulation
        ↓
probability aggregation and calibration
        ↓
immutable forecast registry
        ↓
API, evaluation, monitoring, governance
```

The learning layer estimates football capabilities and predictive distributions.

The simulation layer samples outcomes from an approved match context and parameter set.

These responsibilities remain separate.

## Language Boundaries

```text
Python:
football data, feature generation, statistical models, ML,
calibration, evaluation, model/forecast artifact creation

Rust:
pure deterministic high-volume simulation

Go:
production API, authorization, caching, job orchestration,
operational endpoints

SQL migrations:
relational persistence

Shared schemas/contracts:
cross-language messages and artifact shapes
```

### Python

Python owns:

- provider adapters;
- ingestion orchestration;
- normalization;
- point-in-time datasets;
- football feature engineering;
- Elo, Dixon-Coles, corner models, and later approved models;
- model fitting;
- calibration;
- walk-forward evaluation;
- forecast creation;
- model artifact creation;
- analytical reports.

Do not move football modelling logic into Go or Rust merely for symmetry.

### Rust

Rust owns:

- deterministic Monte Carlo simulation;
- simulation-specific random-number handling;
- parallel high-volume execution;
- simulation-specific numerical hot paths after profiling.

Rust must not own:

- provider ingestion;
- PostgreSQL data access for modelling;
- historical reconstruction;
- model fitting;
- feature engineering;
- HTTP serving.

Do not expand Rust modelling responsibilities before simulation is authorized.

### Go

Go owns:

- HTTP serving;
- request validation;
- authentication and authorization;
- rate limiting;
- cache coordination;
- job submission;
- health and readiness;
- observability;
- retrieval of already-generated forecasts and model metadata.

Go must not reimplement football model mathematics.

### SQL

SQL migrations are the sole schema authority.

Use the repository's approved migration framework.

Do not introduce a competing ORM migration authority.

## Storage Ownership

### Raw Provider Data

Use immutable filesystem or object-storage paths with checksums and exact source details.

Do not rewrite authoritative raw payloads.

### PostgreSQL

Use PostgreSQL for structured relational state and registrations, including:

- MatchForge competitions, seasons, teams, players, and matches;
- provider registry and provider-entity mappings;
- bitemporal source observations;
- canonical resource state and append-only resolution decisions;
- provider and canonical resource coverage, validation findings, and quarantine state;
- lineup and availability observations where applicable;
- source snapshot and resource registration;
- provider sync policy, cursors, request budgets, and shared work orchestration;
- `CanonicalChangeSetV1` registration where applicable;
- dataset and lineage registry;
- model artifact registration;
- forecast registration;
- evaluation report registration;
- promotion and governance events;
- durable operational state.

PostgreSQL should register model artifact identity, URI, checksums, compatibility, lineage, and governance metadata rather than opaque Python binaries.

The shared work registry owns durable job status, leases, retries, cancellation,
dependencies, and completion. These records remain relational operational state.
The event catalogue and temporal event references also remain in PostgreSQL;
full analytical event and shot facts belong in immutable datasets. Observation
artifact registrations bind paths and checksums to source/time/version metadata;
the complete observation files remain outside the database.

### Parquet / Object Storage

Use Parquet or object storage for:

- normalized event history;
- large shot datasets;
- StatsBomb 360 or equivalent high-volume data;
- curated modelling datasets;
- generated feature matrices;
- walk-forward predictions and outcomes;
- analytical evaluation and calibration outputs;
- simulation archives;
- model artifact files where appropriate.

Use the existing immutable file, raw-resource, observation, event-Parquet, and
evaluation-evidence stores. Files bind exact source inputs and physical/logical
checksums where their contracts require them. PostgreSQL keeps their registrations
and lineage. Do not move identity, canonical decisions, coverage, quality,
registries, or work state into Parquet. Compact serving reports and immutable
per-forecast monitoring records remain structured PostgreSQL records; bulk
evaluation corpora, feature matrices, and simulation archives remain artifacts.

### Redis

Use Redis only for ephemeral or cache concerns:

- prediction cache;
- cached simulation progress;
- API caching;
- other non-authoritative short-lived state.

Redis is never the authoritative model registry, forecast history, lineage store, or evaluation store.
Durable simulation work uses the shared PostgreSQL work registry; a cache loss
must not lose ownership, retries, or completion.

### DuckDB

Use DuckDB for local analytical queries and dataset inspection.

It is not a second source of truth.

## Identity

MatchForge identity is provider-neutral.

Provider IDs live in mappings and source observations.

Names are attributes, not identifiers.

Do not merge entities solely because their names look similar.

Resolution must be explicit, deterministic, and traceable.

`IdentityRepository.mapping_at` reads recorded states of the five existing provider-mapping tables: competition, season, team, player and match. Those tables remain the identity owners. `provider_mapping_history` records their inserts, identity changes and deletions atomically with the original write, retaining the original mapping, canonical and source-snapshot IDs. Routine `last_seen_at` touches leave the identity history unchanged. Mapping IDs and history rows are immutable; truncation cannot bypass recorded changes.

Each read requires a football-validity instant and an explicit `knowledge_cutoff`. Mapping validity follows the existing half-open ranges, where null bounds are unbounded. Season native IDs require their native competition scope. The reader selects the known state before matching its native key, so a renamed or deleted mapping cannot resurrect its earlier key. Initial capture establishes knowledge at capture time; it does not reconstruct unrecorded earlier states. Source and mapping clocks can delay knowledge, and subsequent states cannot move knowledge backwards.

A returned mapping is an identity claim with provenance. Qualification stays with the existing decisions: `admitted_identity_at` reads R2 admissions and revocations, and delegates team corrections to `product_team_identity_at`. Confidence alone does not create admission. The resolution-decision and R3 fixture-resolution owners remain in place; an R3 version label does not make its mutable rows an immutable historical record. Existing lineup participation and coach observations retain their fixture and time scope. Continuous membership or management tenure requires independent evidence. The new mapping capture is rehearsed in shadow/test databases before the controlled cutover.

Team corrections extend the R2 `product_identity_admissions` log. A correction
links one source mapping to a verified target mapping and the original fixture
contradiction using `corrects_decision_id` and `target_mapping_id`. It preserves
the original provider mapping, fixture decisions and source observations. Its
database-stamped `decided_at` makes it eligible prospectively; source acquisition
is recorded separately and never substituted for an admission time.

`product_team_identity_at(mapping_id, knowledge_cutoff)` resolves immutable
admissions at the requested cutoff. Current operational views expose effective
IDs without rewriting physical records. History qualification appends snapshots
with the eligible IDs; `product_eligible_history_at` keeps earlier snapshots
unchanged after corrections and revocations. Forecast refresh and historical
fixture context resolve target teams at the same cutoff as their history reads.
Team admission does not merge fixtures; fixture reconciliation retains its own
competition, season, orientation and conflict checks.

The typed correction operation and deployment procedure are documented in
[MVP-HISTORICAL-BACKFILL.md](MVP-HISTORICAL-BACKFILL.md#independent-team-identity-corrections).

`product.resolution_identity.mapping_detail` provides read-only diagnostics for
current operational mappings. It reuses retained-source qualification, existing
admissions, effective team corrections, explicit crosswalks and alias normalization.
`VERIFIED` requires both current qualification and a trusted admission. Missing
source proof and revocations remain blocked; contradictions remain explicit.
Alias candidates never authorize admission. The result includes bounded fixture
impacts, retained correction contexts and an evidence hash for later operator
review. Historical reads continue to use the cutoff-aware identity owners above.

## Decision records

`football.contracts.decisions.DecisionRecordV1` gives future identity, canonical-resolution, authority, capability, promotion and suspension decisions common semantics. The schema is `schemas/contracts/decision-record-v1.schema.json`. Domain owners supply stable subject and predecessor references, their disposition and reason, decision time, optional effective time and JSON evidence. Decision and effective time remain separate; future effective times are valid. Stored clocks normalize to UTC, and evidence is an immutable copy containing finite JSON values.

Use `to_dict()` or `to_bytes()` for serialization. Evidence hashes cover canonical UTF-8 JSON without a newline. The record checksum covers the complete canonical document with its trailing newline; its deterministic UUID identifies that semantic record. Unknown versions, fields, duplicate JSON keys and mismatched evidence hashes are rejected. Corrections produce new records linked to their predecessors.

Existing physical decision tables and domain checks remain the owners. `ResolutionDecisionV1.to_decision_record` preserves its original payload and checksum and requires an explicit stable subject ID. `ModelPromotionEventV1.to_decision_record` preserves artifact/evaluation/event IDs and requires a reason. These adapters leave effective time unreported when the original contract has none. Promotion approval remains with the existing registry and evaluation gates. Historical rows are not rewritten into a common table.

## Point-in-Time Contract

Historical forecast work separates:

```text
football_cutoff
knowledge_cutoff
knowledge_mode
```

Use separate contracts for:

```text
historical labelled training rows
label-free pre-match forecast context
post-prediction outcomes
```

Models do not independently query "previous matches" from current database state.

Current-state views are operational conveniences. They are not valid historical modelling inputs unless an explicit point-in-time reconstruction contract says otherwise.

When multiple matches could not legitimately observe each other's outcomes, forecast and freeze the whole batch before revealing any result.

## Dependency Direction

Preferred:

```text
raw provider data
→ validated provider observations
→ MatchForge records
→ point-in-time datasets
→ models
→ artifacts
→ forecasts
→ evaluation / simulation / API
```

Avoid cycles that allow downstream modelling state to mutate upstream source truth.

## Publication and Retry Boundary

Persistent publication must assume at-least-once execution.

Where applicable:

- immutable writes use deterministic identity and checksums;
- identical retries converge on the existing logical result;
- conflicting bytes fail closed;
- database registration and file publication have explicit recovery behavior;
- partial publication can be detected and reconciled;
- concurrency must not create multiple logical artifacts for one semantic identity.

Detailed retry and recovery behavior belongs in the owning subsystem document.

For product forecasts, a qualifying history decision or a changed future fixture
adds affected fixture IDs to `football.product_forecast_refresh_work` in the same
database transaction. The existing sync runner retries pending work in batches of
at most 32 fixtures. A batch marks its work complete in the same transaction as
its forecast and availability updates; interrupted batches remain pending. The
forecast builder still applies each fixture's football and knowledge cutoffs and
publishes immutable revisions only when its predictive inputs change.
New product forecasts use the `rolling-ten-v2` predictive-input hash and the
`transferable-rolling-goals-poisson-v1-rolling10-v2` product algorithm label.
The fitted model and probabilities are unchanged; older forecast versions remain
readable and are never rewritten.

## Artifact Boundary

Canonical fitted model state should use transparent, portable formats where practical.

Persist immutable identity and checksums.

Do not make pickle, joblib, or cloudpickle the canonical production artifact format.

Published artifacts are immutable. A correction or refit creates a new artifact.

## Simulation Boundary

The simulator is downstream of learned football capabilities and match parameters.

Simulation count controls numerical precision; it is not evidence of predictive quality.

Move a hot path to Rust only after:

```text
Python correctness prototype
→ benchmark/profile
→ justified Rust implementation
→ equivalence tests
```

## Multi-model Forecast Boundary

`FixtureFeatureSnapshotV1` seals provider-neutral, eligible inputs for the model
runner and model CLI. Its portable JSON contract is defined in
`schemas/contracts/fixture-feature-snapshot-v1.schema.json`. Football and knowledge
cutoffs stay separate. Target IDs, same-kickoff results, future facts and facts
known after the supplied knowledge cutoff cannot enter qualified history. The
production history query excludes all target IDs before returning result columns,
including when an earlier kickoff revision exists for the same canonical fixture.

The snapshot keeps goals history, existing rating/rest/congestion calculations,
qualified context, missingness, quality and source references. Missing context
remains null. League strength and home advantage remain model-specific rather
than fabricated shared estimates; tactical, corner, card and player features stay
null because this contract's current input does not supply qualified features for
those families. External context needs source
references and eligible knowledge times. Unknown quality is distinct from an
explicit empty finding list.

Feature exports have their own checksum. Existing model-input projections keep
their approved schema, predictive-input checksum and mathematics. Each model gets
an independent projection of the same sealed values, so mutable context cannot
change another model's input or the feature export. Training, replay and production
use the same rolling-feature arithmetic. The goals-only champion's ignored legacy
xG value remains confined to its existing model interface; unknown source xG stays
null in feature exports. Published artifacts and forecast rows are not rewritten.
The export includes the complete legacy model input for replay; its family views
are derived from that one sealed input.

Python constructs one immutable, point-in-time forecast snapshot per fixture and passes
that same snapshot to every eligible model through the model registry. One model failure
is recorded without suppressing successful forecasts from other models. Model artifacts,
per-model forecasts, evaluations, and external probability benchmarks have separate
append-only storage; the existing production forecast table remains the champion-serving
contract.

The canonical joint score distribution is the source for 1X2, totals, BTTS, clean-sheet,
and simulation inputs. Context features retain structured competition type, home/away
splits, missingness, rest, opponent-adjusted form, and recency-weighted head-to-head data.
External provider predictions are benchmark-only and require exact fixture mapping.

## Market targets and readiness

`football.forecasting.market_catalogue` defines versioned statistical targets,
periods, required fields and explicit selection/line/participation/rule parameters.
Targets exclude extra time and shootouts unless separately defined. Unknown
source meaning, card rules, player nonappearance or incomplete settlement stays
unqualified. A provider label does not establish SportyBet or Opta equivalence.

`football.product.market_capabilities` describes readiness without granting
publication. It reuses provider capability and canonical coverage contracts.
Coverage binds the target definition and exact parameters, input, canonical
competition/season and knowledge cutoff. Qualified component sets must share
canonical fixtures; multiple providers do not add independent fixtures. Generic
resource counts cannot qualify a target field. Sufficiency and evaluation come
from existing owner evidence, rather than a new sample-size threshold.

Diagnostic status and current publication status are separate. Research or
retired models cannot become public support; shadow eligibility is not public
eligibility. Even a complete diagnostic grants no new publication and does not
withdraw an existing forecast. Model loading, fitting, evaluation, promotion and
per-forecast numerical checks retain their existing owners.

The existing `models market-capabilities` command reads one repeatable, read-only
snapshot of the capability/coverage registries. It reports all target families,
required semantics, candidate native source scopes, unknown coverage and model
metadata. Native competition/season scopes are not silently joined to canonical
ones. Target families without bound parameters and qualification proof remain
unqualified; the command creates no probability, HTTP request or operating write.

## Runtime model registration

`ModelRegistration` records model/family/version, feature contract, the content
hash and interval of its training manifest, artifact URI/hash, implementation
version, original dependency fingerprint, competition/product eligibility,
evaluation/calibrator references and lifecycle state. The PostgreSQL runtime
registry stores immutable canonical bytes with a checked hash and registration
knowledge time. Exact-reference reads require an explicit knowledge cutoff;
registration does not create earlier historical knowledge. Metadata can be
superseded by a new registration, without changing an existing record.

This is runtime configuration that references fitted artifacts. Existing artifact
registries, fit lineage and promotion owners remain authoritative. The sole
champion compatibility import is the existing artifact `e856dedf...e46eb4`;
other champion declarations are rejected, and roadmap text grants no promotion.
The bootstrap file preserves the original development-manifest interval and
historical dependency fingerprint. Its negative evaluation reference remains
negative evidence. No fitted bytes or published forecasts are rewritten.

`football models registry-register --registration config/models/current-champion.json`
registers the declaration; `registry-show --registration-sha256 HASH --knowledge-cutoff TIME`
reads that exact version. These commands make no provider requests. Registration
never enables a model. `ModelRegistry.from_registrations` uses explicit selected
registrations, verified loaded artifacts, known adapters and an explicit enabled
set. It checks their identities, disables retired entries and enforces competition
and product eligibility before prediction. Central model eligibility rejects a
fitted artifact whose latest training-match kickoff is at or after either the
fixture football cutoff or its independent knowledge cutoff, in both legacy and
registered paths. This preserves same-kickoff outcome isolation. A null competition list preserves the
current champion's unrestricted competition scope; an empty list allows none.
The goals runner only accepts `SCORE_DISTRIBUTION`. Unsupported product metadata
cannot activate another distribution. Experiment identity includes the exact
registration when one is supplied. Legacy registry/run identities remain intact.

## Independent forecast products

Runtime registrations declare eligible products independently of provider acquisition.
The current runtime champion implements only `SCORE_DISTRIBUTION`. Its runner rejects
corner, card and player product selections before calling the goal model. Adding a
product requires an approved model, eligible feature contract and its own output
contract; naming it in registration metadata does not implement or activate it.
Existing research `CornerModels`, `CornerFixture` and `CornerForecastPayloadV1`
remain independent of goal inputs and score matrices. `BaselineForecastV1` can
carry a corner payload without a goal or match-result payload. Existing research
Elo result forecasts also retain their own contract and governance.

`football models products --forecast PATH` reads an existing score-model forecast
and projects 1X2, double chance, BTTS, totals, exact scores, team goals and clean
sheets from that same validated distribution. It performs no model execution or
publication. Analytic market probabilities, resolved mass and unresolved tails are
preserved. Legacy censored buckets retain their labels, are excluded from exact
score atoms, and their summed bucket indices are explicitly distinguished from an
exact total-goal distribution. Existing forecast serialization and hashes stay
unchanged. Exact support also projects draw no bet, winning margins, quarter-goal
Asian and whole-goal European handicaps, team/match totals and inclusive ranges,
result × strict totals and result × BTTS. Optional repeatable `--goal-line`,
`--asian-handicap`, `--european-handicap` and `--goal-range MIN MAX` arguments supply
explicit parameters. New projections refuse censored support. Each partition
keeps resolved mass, unresolved tail and marginal bounds; the existing numerical
tolerance governs comparisons. These mathematical projections do not qualify
period models, sportsbook semantics or publication. Cards and player products
have no runtime implementation or activation.

## Experiment runs

`ExperimentProtocolV1` freezes a hypothesis, explicit MatchForge fixture ID sets
for development, validation, evaluation and forbidden targets, candidate IDs,
feature contract and checksum-bound policy/authorization references. Its canonical
JSON and schema are versioned; corpus partitions are disjoint. The forbidden
manifest remains in the frozen protocol, independently of the evaluation corpus.
References record existing decisions and do not grant new research access.

`football.forecasting.experiments.run_experiment` accepts the exact development
feature snapshots and already-fitted candidates through the existing `ModelRunner`.
It rejects other targets and protected history before executing a model or writing
an artifact. Model/artifact identity, training cutoffs, feature hashes, eligibility
settings, code, dependency lock and explicit execution time bind the run identity.
All candidates run in protocol order; model unavailability yields a failed run.
There is no automatic candidate search, fallback or model promotion.

The existing immutable file store publishes the protocol, feature inputs, results
and `ExperimentRun`; identical retries converge and changed bytes conflict.
`ExperimentArtifact` records URI and SHA-256. `ExperimentDecision` retains the
common `DecisionRecordV1` and binds the exact published run/result checksum.
The common runner has no corpus loader or outcome reader. Fitting, calibration,
validation/evaluation scoring and promotion still require their existing governed
runners and owner decisions. Frozen historical scripts and evidence are preserved.

## Continuous post-match monitoring

`football models postmatch-evaluate` runs a bounded scan with explicit competition
IDs, kickoff window, forecast horizon, row limit and work lease. It reuses the
production performance selector for the latest eligible published pre-match
revision and verified regulation-time final result. It excludes active aliases,
incompatible results and result knowledge beyond the database clock. Research
forecasts and protected evaluation corpora are outside this path.

The shared `POST_MATCH_EVALUATION` work type owns retries and lease fencing. Pure
scoring finishes outside publication locks. Publication locks the fixture,
revalidates the selected forecast and result, and atomically stores immutable
checksum-bound input and evaluation bytes while completing the work. Inputs bind
fixture, forecast, original payload and artifact hashes, all temporal cutoffs,
result knowledge time, scoring policy, code commit and dependency lock. Supply
the existing root `--code-commit-sha` and `--dependency-lock-sha256` options or
their existing environment variables. Corrections create new work and records;
forecasts and earlier evaluation bytes remain unchanged.

`football models postmatch-monitor` reads a supplied window and knowledge cutoff
in a read-only transaction. It reports the latest captured result per fixture,
model and horizon known by that cutoff, with Log Loss, Brier, RPS, CRPS, calibration,
Shannon entropy in nats and scoring coverage. Segments use model, competition,
season, the existing minimum-lead-time horizon selections and data quality tier.
Tier is `UNKNOWN` because published forecasts do not carry a quality tier; later
data quality cannot be inferred as pre-match knowledge. Coverage counts selected
published forecasts, excluding fixtures without a forecast.

CRPS uses the current champion's published independent-Poisson parameters only
after checking its artifact, algorithm, matrix version, probabilities and compact
grid. The full count distribution is scored without folding outcomes into the
5+ display bucket. Other or inconsistent count distributions have explicit
missing CRPS; invalid result probabilities are unscorable without clipping.
Calibration is descriptive and reuses the existing evaluator. Optional numeric
review limits are caller-supplied; incomplete scoring also yields
`REVIEW_REQUIRED`. Monitoring never fits, recalibrates or promotes a model and
does not replace governed chronological evaluation or its frozen thresholds.

## Domain metrics

`python -m football.product.cli domain-metrics` exports Prometheus gauges from a
repeatable-read, read-only transaction. Supply `--competition` UUIDs and an aware
`--window-start` / `--window-end`; `--horizon` uses the monitoring selections above.
Optional repeated `--provider` values select from the seven implemented provider
adapters. Labels contain only those provider codes, normalizer resource names,
`OTHER` for other reported resources, and the eleven nullable feature families.
Fixture, competition, season, native scope, work and artifact IDs are never labels.

Provider gauges report retained request-budget reservations, current failed
lifecycle acquisition jobs and age since the latest validated real acquisition.
These records do not establish exact HTTP request/failure totals. Missing budget
or acquisition evidence is `NaN`; failed-job counts use the existing job owner.
Team identity measures current product teams without a trusted active mapping.
Fixture identity, resolved duplicate members and forecast availability use the
selected window and current serving/resolution owners. Forecast availability is
the existing future scheduled, verified `FORECAST_AVAILABLE` flag; it does not
execute a new eligibility or forecasting calculation.

Coverage selects the latest report for each exact scope using the coverage
registry's input-time, knowledge-time and publication ordering. The exposed ratio
is the minimum known scope ratio, with separate total-scope and known-denominator
counts. Unknown or empty expected universes remain unknown. Scopes are not summed
into a new universe; provider measurements cover their reported native scopes,
while canonical reports use the selected MatchForge competitions.

Optional repeated `--feature-snapshot SHA256 PATH` arguments read explicitly
supplied `FixtureFeatureSnapshotV1` exports. Their canonical checksum, existing
schema, competition, window and cutoff metadata are checked. Missingness counts
null nullable resource families in distinct supplied exports, with an explicit
sample count. It is not a population estimate, and no feature reconstruction or
model execution occurs. The existing schema is included in the Python package.
Without supplied exports, family ratios are `NaN`. Post-match score/coverage
and review gauges reuse the immutable monitoring reader, including corrected-result
selection; absent scores remain `NaN`. Scraping never publishes evaluations,
claims work, changes counters, calls providers or triggers model actions.

## Operational control plane

The existing Go application serves protected `GET /v1/admin/operations/{domain}`
views for `providers`, `work-orchestrator`, `ingestion`, `identity`, `coverage`,
`data-quality`, `forecasting`, `models`, `experiments` and `r3-audit`. Database views
use repeatable-read, read-only transactions and bounded metadata pages. The R3
view reads the existing tracked project-status owner and returns its file checksum;
it preserves deferred/failed dispositions and does not change audit decisions.
Models wrap the unchanged immutable registration alongside registration metadata.
The experiment view reports explicitly registered shared execution work. Run
manifests remain at caller-selected immutable artifact roots; the API does not
scan, import or infer experiments from research directories.

`GET /v1/admin/work` filters by shared state, including pending, running, retry
wait, blocked and failed work. Work detail includes lease owner/expiry/heartbeat,
generation, age, attempts, the dependency count and first 100 dependency IDs,
parent work/sync references and redacted errors. Publication lease tokens are
never exposed. Historical queue links require the exact retained request time;
a newer queue entry cannot be attributed to an older work item. Pagination uses
the existing 20/50/100 page sizes and rejects overflowing offsets.

`POST /v1/admin/work/{work_id}/cancel` delegates to existing cancellation and
parent sync-run controls, retaining their process stop and publication fencing.
`retry` releases explicitly blocked work through the existing SQL owner without
lowering its availability deadline. Already scheduled retries retain their
policy/deadline. Failed or cancelled parent sync runs use the existing fresh-run
retry path; other terminal work returns a conflict and requires a new request
from its domain owner. Terminal identities are never reopened, and work control
does not add an executor or authorize model fitting, evaluation or promotion.

All routes retain private-local binding/Host/peer checks and the existing trusted
browser Origin or origin-less owner credential. Mutations require JSON and accept
only an empty object/body. No new administration service, security boundary,
provider request, scheduler or model calculation is introduced. The versioned
OpenAPI contract documents the routes, metadata, nulls and failure statuses.

## API Boundary

The Go API exposes only capabilities supported by executed data and evaluation gates.

An endpoint's existence must not imply a model or data capability that has not been authorized and proven.

The API must not reimplement model mathematics owned by Python or simulation logic owned by Rust.

Python owns public performance scoring and rating, external selection comparison,
and form, H2H, coach and rest features. `football models public-reports` requires an
explicit report kind, scope UUIDs, horizon, limit, lease and code/dependency hashes.
It reads centrally eligible facts in a read-only repeatable snapshot, calculates
outside publication locks, then publishes immutable `product_read_reports` through
shared `READ_MODEL_PROJECTION` work. No fit, authoritative evaluation or promotion
runs. Repeated inputs converge; corrected facts create new report versions.

Go selects only reports matching the current SQL source fingerprint, verifies their
bytes and scope, and retrieves existing normalized availability, lineups and
standings. Missing or stale fixture-context reports return 503. Performance pages keep
available leagues and expose READY, EMPTY, PENDING or FAILED per league; pending
rows retain the selected forecast count and have null metrics. A missing report
never establishes zero samples. Individual unavailable Performance requests
retain 503. External comparisons expose READY, PENDING, FAILED, UNSUPPORTED,
NO_FORECAST or UNMATCHED independently of the existing agreement value. Score
freshness is UNKNOWN without a deadline; the legacy boolean alone never proves
freshness. A verified zero selected
forecast count retains the empty UNRATED performance state; missing reports never
become zero samples. Source fingerprints invalidate derived data and do not replace
canonical model/artifact checksums. Context history excludes the target fixture ID,
including earlier kickoff revisions. Form uses five matches, H2H ten, and rest
uses the existing Python helper; policy `pre-match-revisions-v2` is unchanged.

Live score reconciliation orders qualified match minutes and same-provider update
clocks separately from HTTP acquisition. Re-fetching a body changes fetch freshness,
not its original observation time. Missing provider clocks stay unknown. Future
provider timestamp claims cannot establish ordering. Unordered lifecycle changes
remain held, and terminal score corrections retain the existing review gate.
Serving binds canonical status/scores and prefers advanced match clocks before
transport tie-breaks. Current or unknown-clock score disagreements are visible as
partial coverage. The optional live-source ordering metadata describes available
evidence; it does not activate another provider or qualify a historical model input.

OpenAPI 0.9.0 describes domain context, normalized live data and external comparison
responses. Provider identifiers, status labels and original statistic fields remain
explicit source provenance for wire compatibility; they are not model keys or
provider-native payload contracts. Existing runtime processes are not cut over by
this change. Report production must precede serving cutover for required scopes.

## Detailed References

Use the owning document for implementation-level detail:

- [Data platform architecture](data-platform-architecture.md)
- [Source acquisition](source-acquisition.md)
- [Data model](data-model.md)
- [Temporal model](temporal-model.md)
- [Canonical ingestion](canonical-ingestion.md)
- [Event datasets](event-datasets.md)
- [Data validation](data-validation.md)
- [Ingestion reports](ingestion-reports.md)
- [Backtesting](backtesting.md)
- [Model governance](model-governance.md)
- [Engineering testing](testing.md)

Current project state belongs in the tracked project-status authority and applicable Wayfinder/evidence records rather than this document.


### Operational acquisition and historical recovery outcomes

Operational provider sync reports `current_acquisition` and `historical_recovery`
separately. The existing top-level counts still include both, and any failed
scope keeps the aggregate `COMPLETED_WITH_ERRORS`. A successful HTTP response is
not proof of identity admission. Held identities remain in lifecycle diagnostics.
A supported historical fixture absent from its native daily response retains
`RECOVERY_FIXTURES_MISSING` and waits one day before another request. Transport
and detail failures retain the existing short cooldown. No retry admits a fixture
by name or changes an identity decision. Independent daily sync and external
collection stages both execute; either nonzero exit makes the wrapper fail.

Root sync heartbeats remain 15 seconds with a two-minute lease. Shared work keeps
its exact owner/token/generation checks. After interruption, a new claim may
recover committed progress; an expired claim cannot renew or publish. Missing
host heartbeat/process evidence must not be interpreted as permission to extend
or bypass these checks.


Current live-resource serving excludes a retained resource when its provider's
verified native mapping points to a different effective fixture. The original
resource remains available for review. Detail acquisition cannot attach a
conflicting candidate through the read-only resolver. This does not choose which
fixture is correct or change a mapping decision.

`make build` embeds the code commit, uv.lock SHA-256 and clean/dirty source state
in the Go binary. `/version` returns these fields beside the existing version.
Direct builds without those linker settings report `unknown`; serving never
reads a moving checkout to infer a deployed revision. Operators can compare this
endpoint to the reviewed commit before starting work.

Open fixture panels refresh context after a completed request (60 seconds while
visible, 120 seconds while hidden); existing temporary-unavailability backoff
remains. Forecasts stay bound to their immutable ID. Admin discovers idle jobs
at 60 seconds, active jobs at 2.5 seconds, hidden pages at 120 seconds and refreshes
on visibility restoration. Polls remain sequential and superseded requests abort.


Active fixture summaries and external comparisons select from
`product_prematch_forecasts`: issue time must precede the current kickoff and
football/knowledge cutoffs cannot follow issue. A corrected kickoff can therefore
make a retained revision ineligible. That revision remains retrievable by ID in
history, while current consumers select an earlier eligible revision or expose
missing source data. No published forecast is changed or deleted.


The private-local `/v1/admin/resolution/{view}` read route delegates identity,
fixture and source inspection to the existing Python domain owners. Its
repeatable-read transactions cannot change domain state. Stable case keys reuse
mapping, fixture, resource and dataset IDs; history names the original decision
source and distinguishes mutable current fixture resolutions from append-only
records. The Missing Data list checks registered file bytes in bulk; dataset
details retain full logical integrity verification. File checks cannot establish
publication eligibility. Migration views verify the hashes of tracked readiness
evidence and do not claim to have rerun parity. Private responses are marked `no-store`.


Identity review writes use `/v1/admin/resolution/preview` followed by `/apply`.
Origin trust permits preview; apply additionally requires the existing owner
Bearer credential. The browser keeps this credential only in form state. Go
passes a credential fingerprint as actor, never the credential, to Python.
The apply transaction serializes the case, rechecks the preview under existing
identity locks, delegates to the existing domain owner and appends one immutable
review event. A request UUID binds the exact approved inputs and actor. Retries
return that event; stale versions and changed requests fail. Review-only actions
never imply admission, recovery or parity. Correction and revocation remain
prospective, with original provider observations and published forecasts retained.


Batch review is bounded to 20 independent cases per request. Preview shares
retained-byte verification, while apply requalifies each case under the existing
locks and commits each case separately. Shared target mappings, canonical entities
or fixture effects cannot be bulk-approved together. Per-case results and UUIDs
survive partial failures; a retry never substitutes a new approval. Queue grouping
uses known current competition/season memberships only and never grants identity
trust. Distinct case totals remain separate from overlapping group counts.


Resolution recovery freezes target IDs and source hashes in the approval transaction.
The existing Work Orchestrator owns its `CANONICAL_RECONCILIATION` leases, fencing,
retries and scheduling. Targets publish separate immutable receipts under a valid
lease; each page has at most 32 targets and a dependent continuation. All retained
byte reads precede identity/publication locks. Existing native fixture and identity
rules are rechecked using prepared bytes before publication. Scoped reconciliation
keeps complete competing-candidate neighborhoods; excessive neighborhoods remain
blocked rather than being split in a way that changes uniqueness.

Recovery requests existing context, eligible future forecast, performance and
external settlement generations. Immutable receipts record what was requested;
current case details separately report pending work in affected scopes. Neither a
completed recovery page nor an empty queue establishes identity or migration parity.
The original no-argument unknown-season SQL API delegates to the shared scoped rule.

Missing-data decisions in the Admin Resolution Center retain original registrations.
Exact retained-byte restoration queues approved `PROVIDER_ACQUISITION` work before
publishing to the original registered path. Immutable publication rejects different
existing bytes; a retry reconciles an authentic file whose receipt did not commit.
A fenced receipt records file verification separately from full dataset integrity.
Only a passing case queues scoped canonical recovery. Source clocks, old dataset
versions and published forecasts are preserved. Case exclusions name their exact
accepted scope and never waive complete-data migration parity. Source-backed
new-version reconstruction requires independent build approval and the existing
dataset publisher, complete source lineage and unchanged historical cutoffs.

Resolution Center parity rechecks use shared `READ_MODEL_PROJECTION` work and an
immutable verification history. Current source/identity/dataset diagnostics run in
a repeatable-read read-only transaction before fenced report publication. Retained
comparison artifacts and original arithmetic are checked against their registered
hashes and sizes; this does not extend their original comparison scope. Reports
bind the database identity, snapshot, source evidence and verification time. Copied
or outdated reports cannot establish current readiness. Missing required checks,
incomplete runtime scopes, unavailable data, identity failures and unresolved
59/327 discrepancies prevent full parity. Recovery/disposition requests retain the
cause and request dependent rechecks; a successful verifier job can report a
blocked parity gate.

Cutover controls retain versioned settings for all 13 established stages. Production
advance remains blocked by complete parity, dependency order, qualified runtime
bindings and separate acceptance. Explicit shadow operations are not production
replacements. The currently wired alternate fixture backend is `fixture_read_model`.
An owner-approved disposable-database rehearsal binds its exact projection hash and
configuration generation, rebuilds the real cache and selects its leased V2 route.
A savepoint restores the prior cache and route before a fenced immutable result.
Configuration events retain the exact approved stage/request. Lost or revoked trial
leases select legacy automatically; explicit rollback can clear stale trial metadata.
Go fixture serving accepts only the closed legacy/V2 relation mapping and rechecks
a V2 route before returning its response. These controls do not enable production
cutover, replace unbound stages, or authorize scheduler retirement.

Stage13 details and parity verification include read-only retirement preparation:
operator/history/provider-scope ownership, forecast generations registered on claim,
active/expired shared leases, unfinished dependencies and current source bindings.
Unbound pre-migration in-flight rows retain their compatibility consumers. Queue
emptiness does not prove deployed readers are retired or grant code removal.
Live retirement requires accepted Phase35 cutover, a deployed-scheduler inventory,
owned pending work, stabilization/rollback approval and separate authorization.


### Scoped Admin market diagnostics

`GET /v1/admin/market-capabilities` uses the existing private-local Admin access
policy and the Python capability/coverage reader. Canonical competition and season
IDs plus a nonfuture timezone-aware knowledge cutoff bind the report; the season
must belong to that competition. Cutoffs have at most microsecond precision.
The compact `MarketCapabilitySummary` is diagnostic, not a forecast or promotion.
It retains target semantics, missing inputs, source compatibility, configured
model traceability and publication/evaluation distinctions. Native candidates do
not establish canonical scope or historical eligibility. No database name or raw
provider payload is exported. Existing published forecasts are not withdrawn or
approved by this report. Request cancellation terminates the bounded reader.

The existing Data Sync page owns the scoped read form and grouped disclosures.
Its resource fails/retries independently of sync status. No new Admin app,
credential store, acquisition control, model fitting or runtime cutover is added.
