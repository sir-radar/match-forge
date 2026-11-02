# Source acquisition

## Boundary

Source acquisition preserves provider bytes before parsing or normalization. The production flow is:

```text
FootballDataProvider
    → pinned provider resource descriptor
    → bounded fetch
    → immutable raw publication
    → SourceManifestV1
```

Canonical ingestion consumes this boundary only after re-verifying the immutable manifest and every declared resource. See [Canonical ingestion](canonical-ingestion.md). Normalized event publication then consumes the same verified acquisition and registered canonical catalogue. See [Event datasets](event-datasets.md). Published event datasets receive policy-driven [data validation](data-validation.md), and each ingestion publishes immutable [ingestion reports](ingestion-reports.md). 360 normalization remains a later phase.

## Project use policy

MatchForge is a local, private, non-commercial experimental research project. This document establishes a **standing internal owner authorization** to investigate, request, acquire, and locally retain football data needed for development and unfinished research tasks. This authorization applies to all providers, competitions, seasons, and technically accessible public routes; it is not limited to specific named sources or a single task.

**Local experimental acquisition is allowed by MatchForge's internal policy even when provider terms have not been reviewed, permission is unresolved, or published terms restrict automated or bulk acquisition.** Do not stop local experimental acquisition solely because a provider's terms status is `UNKNOWN`, `UNRESOLVED`, `RESTRICTED`, or `PROHIBITED`, and do not repeatedly seek an owner decision for the same policy question. This rule removes an _internal research-eligibility gate_; it does **not** constitute provider consent, override an external contract or law, or establish that the activity is permitted by the provider.

Before or during acquisition, record the provider, source URL or route, terms and permission status, known restrictions, purpose, request limits, acquisition time, and compliance limitations in source evidence. Keep those limitations visible; never relabel restricted or unresolved access as provider-approved. Treat actual access failures, missing credentials, source unavailability, explicit operational stops, and immutable-data or security checks as real blockers rather than falsely reporting successful acquisition.

Acquisition remains bounded and local. Respect configured rate and concurrency budgets, backoff, quotas, caching, credential handling, and provenance. Do not bypass authentication, CAPTCHAs, paywalls, access controls, or anti-bot protections. Never distribute or externally publish third-party raw data unless the applicable rights permit it. The local research authorization does not enable production collection, public release, Evaluation V2 qualification, model promotion, or production cutover; these retain their separate scientific and operational gates.

### Development acquisition routes

The [current owner decision](evidence/owner-decision-public-development-data-access-2026-10-31.json) and the standing project-use policy above authorize investigation and bounded local acquisition from technically viable football-data routes without a new per-provider or per-task approval. Official API documentation or a commercial integration is not a prerequisite for internal experimental acquisition. Routes may include official APIs, undocumented public JSON and browser endpoints, public HTML and embedded state, CSV/JSON feeds, open datasets, maintained community wrappers/scrapers, and normal public request formats implemented directly in MatchForge.

Record the actual access route separately from resource capability, provider permission status, and downstream qualification. Inspect the source, make bounded requests, preserve exact bytes and observation time, and measure coverage. An unofficial endpoint, wrapper, or scraper is not by itself an unavailable source. A failed request is evidence for that tested route and scope, not proof that every resource is inaccessible. A restrictive or unresolved terms status must be recorded as a compliance limitation, not silently converted into a technical acquisition failure or a provider-approval claim.

Use the existing cache, immutable storage, request budgets, quotas, cooldowns, schema validation, and shared work orchestration. Do not defeat authentication, CAPTCHAs, paywalls, technical access restrictions, or anti-bot controls. Identity, semantic, and point-in-time qualification remain prerequisites for canonical/model use; public access alone does not qualify data or establish earlier historical knowledge. Label new data collected under this standing exception `EXPERIMENTAL_ONLY` until separately qualified.

This policy concerns external football data. MatchForge's own admin/API authentication, private-local checks, browser Origin checks, owner approvals for consequential operations, and request validation remain governed by their existing contracts. Historical decisions and frozen evaluation scopes are preserved; this standing experimental acquisition authorization applies prospectively and does not reopen closed scientific routes.

### Flashscore and Soccerway under the standing experimental policy

The [R03 owner decision](evidence/owner-decision-flashscore-soccerway-research-exception-2026-11-01.json) is an earlier source-specific example of the standing experimental policy. Flashscore and Soccerway are eligible for bounded **local experimental acquisition under MatchForge's internal rules** even where provider permission is unresolved or automated-acquisition restrictions have been identified. The same internal rule now applies to other providers; no further exception is required for each experimental task.

Record the named provider restrictions and unresolved permission accurately in acquisition evidence. Internal owner authorization is not provider permission and does not erase external compliance risk. Do not bypass authentication, access controls, CAPTCHAs, paywalls, or anti-bot protections. Preserve request bounds, source isolation, identity and point-in-time checks, and `EXPERIMENTAL_ONLY` classification until independent qualification.

## WhoScored historical requests

`WhoScoredSource.season` accepts the native region, tournament, season and slug
from retained league-selector links. Its optional stage ID selects the linked
monthly fixtures page. Normalization checks both requested season and stage IDs
against the embedded fixture payload. A reachable season page or month is not
complete-season coverage. Native UTC values and source-side IDs still require
independent canonical identity and target qualification before historical use.

## Auditing retained provider data

Run a read-only inventory against the configured database:

```sh
set -a; . ./.env; set +a
. ./scripts/toolchain.sh
uv run --locked python -m football.providers.data_audit --artifact-root .local/provider-audits
```

The command writes a content-addressed diagnostic report through the existing
immutable file store. It reads existing registrations, observation tables and
registry counts; it makes no provider requests or qualification decisions.
Native statistic fields are measured separately by provider, stored competition
and season IDs, and period. Current competition display labels never supply a
historical season. Missing scope IDs remain unknown.

Resource revisions, repeated measurements and distinct stored fixtures have
separate counts. Numeric zero remains distinct from an unreported value. A
recognized normalizer field does not prove physical raw-byte retention,
semantic/identity/PIT qualification or model support. Those unknown states remain
null. Use existing capability, authority and coverage owners for qualification;
this diagnostic report is not another registry or a historical feature reader.

## Provider capability registry

Understat's development adapter uses its public JSON resources after the ordinary
anonymous page/session bootstrap. Cookie values remain private and ephemeral.
Every HTTP request can use the existing scheduler/budget guard. Wire bytes and
checksums remain immutable; gzip expansion uses the established source byte limit
before strict JSON/native validation. The existing historical manifest and
registration owners support retained resources without inventing Git revisions.

Use the existing normalization CLI with `results` or `shots` after registration;
shot decoding requires the explicit native fixture scope. Unknown source timezones
remain DATE_ONLY fixture metadata with no inferred event time. Shot assistant
names and final match scores do not become identities or before-shot context.
Coordinate frames and market/PIT/identity qualification remain separate. Adapter
availability and scoped sample capability do not enable production collection.

Each provider declares an immutable `ProviderCapabilityV1` before it is enabled. The declaration
records terms status, supported competition/season scopes, resource-level historical coverage,
update semantics, cursor/webhook support, rate limits, credential references, and adapter version.
The registry stores only non-secret credential references; API keys and tokens never belong in the
capability declaration.

The current StatsBomb Open Data adapter declares World Cup 2022, Premier League
2015/16, La Liga 2015/16, Liga F 2023/24, and Serie A 2015/16 scopes. Serie A
`12/27` is authorized only for research qualification of pinned fixtures,
events, and lineups; its declaration does not admit it to Evaluation V2 or
authorize model implementation. Its commit-pinned snapshot contract is enabled
for research use without a credential reference. This registry describes capability, not global
source authority; later reconciliation policy remains responsible for field-level source selection.

Provider roles use the versioned `tier_a` (event intelligence), `tier_b`
(match/statistical enrichment), and `tier_c` (market benchmark) vocabulary. A
provider may declare more than one role; roles describe supplied capability, not
trust priority. StatsBomb Open Data is currently declared as `tier_a` only.

### Research and Evaluation V2 are separate qualification levels

For **local experimental research**, the standing project-use policy permits bounded acquisition without a provider-terms approval gate. Public accessibility is not proof of permission: retain the actual provider terms/entitlement status, known restrictions, and any unresolved compliance limitations, including when automation or retention is prohibited or uncertain. Do not infer that MatchForge's internal authorization grants rights against a provider. Do not treat a terms-only concern as a reason to abandon unrelated acquisition, adapter implementation, missing-data recovery, or research tasks.

Live requests still require a documented request budget within the standing owner-authorized research scope. The V4 programme's bounded investigation authorization remains in effect, so routine requests do not require repeated approval. Frozen research/evaluation budgets and separate scientific or production-cutover approvals remain binding. Access-control bypass and unsafe or unbounded requests remain prohibited.

Research contract fixtures and sanitized, bounded technical checks do not qualify a provider for Evaluation V2. Evaluation qualification additionally requires complete frozen coverage, exact source and xG-series identity, appropriate rights for immutable retention, correction/revision lineage, stable traceable identifiers, source hashes, and every applicable corpus and firewall rule. Outputs obtained under the experimental exception must be labelled `EXPERIMENTAL_ONLY` and cannot be used as Evaluation V2, promotion, or production evidence unless independently admitted under the stricter applicable qualification requirements.

`validate_pitchapi_audit` is the offline PitchAPI qualification boundary. It
accepts externally supplied fixture manifests, match-scoped shot responses, a
sanitized request log, a predeclared request budget, and explicit qualification
evidence. It performs no network or persistence operation. It separately emits
technical and Evaluation V2 dispositions, treats missing shot resources as
missing rather than zero, accepts only explicit regulation periods, identifies
penalties only by provider situation, rejects non-finite/out-of-range xG and
mixed xG-series claims, and never includes raw payload values in its report.

The owner-authorized full-season audit completed for Bundesliga 2023/24 and
Ligue 1 2022/23: 686/686 match-shot resources, 17,873 finite in-range shots and
244 explicit penalties, with no observed missing, malformed, duplicate,
period, situation, xG or team-membership error. This establishes current
technical completeness for those two audited snapshots only. It does not
authorize raw retention or ingestion and does not establish the upstream xG
supplier/model/version, cross-season series identity, correction and revision
history, provider-ID stability through rebuilds, or historical point-in-time
availability. PitchAPI therefore remains research-only and is not an
Evaluation V2 provider. See the [readiness assessment](evidence/evaluation-v2-readiness-assessment-2026-09-23.md).

Offline contingency preparation adds an evidence-backed PitchAPI xG-series
gate and provider-neutral synthetic corpus firewall. These are validation-only:
they do not fetch, retain, register or normalize provider data. A production
adapter remains blocked until an approved fixed export supplies exact schema,
revision, model, correction, ID-migration and retention evidence. The current
Git-specific `SourceManifestV1` and `DatasetManifestV1` must not represent an
API snapshot with a fabricated Git SHA. See the [contingency preparation
record](evidence/pitchapi-contingency-qualification-preparation-2026-09-23.md).

TotalCorner is a gated `tier_b`/`tier_c` candidate under the official JSON REST API (`/v1/`). Bounded local experimental acquisition can proceed when required credentials, account timezone/language, and coverage scopes are configured, without requiring separate private-research or access-terms approval. Record actual terms and entitlement status as evidence, not as a claim of permission.

This does not enable production or Evaluation V2 use. Its aggregate statistics cannot substitute for Tier A event geometry, and provider-defined fields such as `dangerous_attacks` retain provider provenance.

Enabled providers also require an immutable `ProviderSyncPolicyV1`. It binds
resource and competition/season scope to configurable discovery cadence,
look-ahead/backfill windows, historical-backfill mode, cursor strategy,
timeouts, bounded retry delays, rate/burst limits, freshness objective, and
adapter version. A webhook can trigger work, but scheduled reconciliation
remains required for recovery; a missing update is never treated as valid data.

Provider-specific `ProviderRuntimePolicyV1` separately governs request timeout,
concurrency, steady/burst limits, quota budgets, retryable status/error classes,
bounded exponential backoff with jitter, circuit-breaker thresholds/cool-down,
probe cadence, and stale-data escalation. Runtime degradation is observable and
must not silently publish missing data or create an unbounded retry storm.

Provider resources declare `ProviderResourceContractV1` with explicit schema,
adapter, parser, and normalizer versions plus required/optional fields and
enumerations. Compatibility inspection accepts additive fields, surfaces
unknown enum values as warnings without relabeling them, and quarantines
missing required fields or unsupported explicit schema versions. Historical
fixtures for each declared contract remain deterministic evidence for adapter
upgrades.

Authenticated providers use `ProviderCredentialRefV1` and `ProviderConfigV1`.
Only non-secret URI references, credential type, rotation metadata, HTTPS base
URL, and policy references are persisted. Tokens never enter source control,
manifests, logs, exceptions, artifacts, or reports. Credential rotation changes
the reference metadata, not provider identity or historical source lineage.

`ProviderSyncWorkerV1` remains Python-owned. Its callback performs one complete
acquisition/validation/publication cycle and advances durable progress only
after that cycle is safe to retry. The worker supports cooperative shutdown
between cycles; restart is therefore at-least-once and relies on durable
cursor/job identity for semantic convergence. Go may expose controls later but
does not own provider normalization or reconciliation.

`AutomaticAcquisitionFlowV1` fixes the steady-state order: discover, checkpoint,
acquire, preserve, validate, normalize, resolve, reconcile, quarantine, publish,
advance the cursor, emit a change set, then trigger downstream eligibility.
Failure stops the flow before later stages; a successful fetch is never treated
as canonical publication.

Durable synchronization state is relational: `provider_sync_runs` records
operational attempts, `provider_resource_cursors` records checkpoints,
`acquisition_jobs` provides at-least-once semantic identity,
`acquired_resources` binds published bytes to source lineage,
`quarantine_records` isolates unsafe units, and `canonical_change_sets` records
trusted downstream changes. Cursor advancement is valid only after the linked
resource contract completes; retries converge on the same resource revision.

## Contract fixtures

Contract fixtures exercise a provider adapter without becoming provider evidence.
Their source snapshot has `source_kind = CONTRACT_FIXTURE`, a required immutable
`fixture_id`, and the same provider ID as the adapter under test. Real sources
use `source_kind = REAL_PROVIDER`; existing source rows retain that meaning by
default. `fixture_processing_attempts` and `quarantine_resolution_outcomes`
append each failed, reviewed, and reprocessed result without replacing the
original quarantine.

Fixture-backed `CanonicalChangeSetV1` records use
`publication_scope = CONTRACT_FIXTURE`. They are acceptance-only: fixture
snapshots cannot create normal analytical datasets, and downstream model or
rebuild readers must consume only `REAL_PROVIDER` change sets. A successful
fixture publication therefore proves the publication path without affecting
provider coverage, missingness, model training, evaluation, features, ratings,
forecasting, or continuous learning.

`PartialFailureReportV1` isolates each resource outcome as `SUCCEEDED`,
`RETRYABLE`, `QUARANTINED`, or `FAILED`. Aggregate status is `SUCCEEDED`,
`PARTIAL`, or `FAILED`; one bad resource never silently invalidates or marks
unprocessed resources as complete.

Trusted publication emits immutable `CanonicalChangeSetV1` evidence binding sync
runs, source-resource checksums, affected canonical IDs, added/superseding
observations, analytical partitions, football/knowledge-time ranges, and both
resolution and quality policy versions. Downstream eligibility responds to this
change set, never to raw provider notifications.

## Observability

Each provider/resource observation is emitted as an immutable,
machine-readable `ProviderObservabilitySnapshotV1`. It records freshness
timestamps and target, discovery/fetch/unchanged counts, acquired bytes,
validation and resolution outcomes, quarantine and conflict backlog, retries,
rate-limit responses, processing latency, publication/reconciliation failures,
change-set emissions, cursor lag, and circuit state. The snapshot exposes a
deterministic freshness status and alert-condition codes for stale or never
successful resources, open circuits, and present validation, quarantine,
conflict, publication, or reconciliation failures. Spike and drop thresholds
remain versioned operational configuration; consumers compare these snapshots
without changing the recorded evidence.

Phase 2B extends the same snapshot with schema-compatibility failures, quota
exhaustion, resolution-review backlog, dataset-rebuild queue depth, stale
dependency count, and cursor-advance time. These fields make the required
foundation health signals consumable without requiring a dashboard.

`ProviderPlatformAcceptanceReportV1` records the reviewed Phase 1B gate. It
requires explicit evidence references and reports provider schema/runtime
safety, secret-reference boundaries, resolution, quarantine/reprocessing,
cross-source reconciliation, and trusted change-set publication. Overall PASS
requires at least two approved provider namespaces exercised end-to-end;
missing evidence remains `NOT_RUN` and a single exercised provider is `FAIL`.

## StatsBomb Open Data

`StatsBombOpenDataAdapter` implements the provider boundary for competitions, season matches, lineups, and events. It also exposes StatsBomb 360 resources without adding them to the provider-neutral protocol.

Every adapter instance requires a full 40-character lowercase Git commit SHA. Resource URLs use `raw.githubusercontent.com` with that immutable revision; branches and tags are rejected. Requests have a 60-second timeout and a 128 MiB per-resource limit. Provider identifiers must be positive integers.

The shared HTTP transport retries only `URLError`, `OSError`, and HTTP 408, 429,
500, 502, 503, or 504. It makes at most four attempts, with fixed delays of one,
two, and four seconds between attempts. A terminal failure identifies the exact
URL, attempt budget, exception class, HTTP status when available, and provider
error; it does not publish a partial source manifest.

StatsBomb attribution is retained in every source manifest:

```text
Data provided by StatsBomb
```

## Football-Data.co.uk Phase 1B proof

`FootballDataUkAdapter` is restricted to the approved Phase 1B corpus:
`notes.txt`, Premier League `E0/2526`, and Premier League `E0/1516`. It uses
the `football_data_uk` namespace, direct provider-published CSV resources, no
credentials, and the Tier B match/statistical-enrichment role. Its
`FootballDataUkHistoricalLeagueCsvV1` contract requires result fields,
preserves additive columns, and quarantines missing or duplicate headers.

This adapter does not expose event, lineup, or 360 resources. A URL is only a
locator: later acquisition records immutable raw-byte SHA-256 identities and
the observed MatchForge acquisition time. It must not claim strict historical
provider knowledge time or alter Sprint 2 evidence.

`FootballDataUkSourceResourceV1` is the content-addressed receipt for each
captured resource. It binds the frozen path, HTTP response metadata, byte size,
SHA-256, MatchForge observation time, adapter/parser/normalizer versions, and
the matching MatchForge resource contract. It records no provider-native schema
version and classifies historical knowledge as `retrospective`; the resource
cannot imply when Football-Data.co.uk first knew a historical row.

`FootballDataUkRawStoreV1` writes a receipt-verified payload beneath a path
containing both the source-path digest and raw SHA-256. A later capture at the
same provider path with changed bytes therefore receives a separate immutable
file. A same-byte retry verifies the existing file; a receipt/payload mismatch
fails before any write.

`FootballDataUkAcquisitionEvidenceStoreV1` immutably publishes the ordered R1,
R2, and R3 source receipts separately from raw bytes. Its identity hashes the
full receipt metadata, including request/observation times and HTTP metadata;
same-evidence retries verify the prior file, while changed evidence produces a
separate record.

`parse_football_data_uk_csv` validates receipt-matched UTF-8 CSV bytes before
provider normalization. It keeps header order, records a deterministic header
SHA-256, reports per-column non-null/null counts and coverage for that exact
resource checksum, preserves additive columns, and rejects malformed rows.
Missing required fields return schema quarantine evidence rather than a
partially normalized dataset.

A leading UTF-8 BOM is treated only as an encoding marker during parsing; the
immutable raw payload and its checksum remain unchanged. This prevents a valid
provider `Div` header from becoming a different field name while retaining the
exact bytes that supplied it.

`FootballDataUkCoverageEvidenceStoreV1` publishes the complete per-column
coverage report as an immutable JSON artifact keyed by its canonical report
SHA-256. A retry verifies the exact existing report; it cannot rewrite
missingness evidence for the same identity.

`normalize_football_data_uk_record` then produces a provider-normalized
match-level observation only. It validates full-time and half-time score/result
consistency, preserves a timezone-naive provider date/time, and retains all raw
columns. Recognized shots, corners, fouls, cards, booking points, free kicks,
offsides, and woodwork fields remain provider aggregate statistics; this path
does not create events, lineups, or 360 data.

The frozen CSV contract accepts provider `Date` values in either `dd/mm/yy` or
`dd/mm/yyyy` form. Both normalize to the same calendar date while the original
field remains in the immutable raw row; no timezone or kickoff instant is
invented.

`FootballDataUkAcquirerV1` is the only bounded live-acquisition entry point for
this proof. It requests `notes.txt`, E0/2526, then E0/1516; captures request
start and observed completion time plus HTTP status/content type/ETag/Last-
Modified; creates the content-addressed receipt; and writes the receipt-verified
bytes immutably before returning. It cannot accept paths outside that frozen
three-resource scope.

`FootballDataUkOverlapPrefixSelectionV1` applies the frozen P1 source order:
provider match date, valid local kickoff time when present, then CSV record
index. It selects the shortest prefix covering the R3 team universe, a valid
HC/AC pair when those columns exist, and a record explicitly supplied as trusted
by later canonical-resolution evidence. It neither resolves identities nor
derives trust from names, scores, or provider IDs.

`FootballDataUkAcceptanceCorpusManifestV1` freezes the exact bounded proof
inputs: content-addressed R1/R2/R3 receipts, R2 and R3 coverage reports, the
P1 selection-rule version, ordered selected CSV record indexes, trusted selected
record indexes, and provider team universe. Each coverage report binds its own
raw resource SHA-256, while selected rows bind R3; changing any source bytes
creates a different manifest identity.

`FootballDataUkAcceptanceCorpusStoreV1` publishes that manifest immutably,
without copying any provider payload. A same-manifest retry verifies the existing
artifact; a different bounded corpus receives a distinct content-addressed path.

`FootballDataUkPostgresSourceRegistryV1` registers the frozen receipt bundle in
PostgreSQL before any resolution or canonical publication. It creates or verifies
the `football_data_uk` provider as `file_download`, records the receipt-bundle
SHA-256 as the source-snapshot revision, and registers each raw resource using
its exact path, byte size, SHA-256, media type, and MatchForge observation time.
`notes.txt` is `not_applicable` to CSV parsing and already valid as acquisition
evidence. R2 remains pending downstream parse and validation; R3 may reach the
separate bounded P1 publication path only after its reviewed resolution and
reconciliation checks. Any existing provider, snapshot, or resource with
incompatible metadata fails explicitly rather than rewriting provenance.

`FootballDataUkPostgresTrustedPublicationV1` is limited to the frozen R3 P1
overlap resource. It verifies the reviewed `AUTO_ACCEPTED` match decision before
adding each completed score observation, keeps the source snapshot/resource and
MatchForge observation time, and emits one immutable `CanonicalChangeSetV1`.
The caller supplies the reviewed quality-policy version. Repeating identical
evidence verifies existing observations and the existing change set; this path
does not advance a provider cursor or resolve quarantined records.

`PostgresResolutionDecisionStoreV1` persists each existing
`ResolutionDecisionV1` as an append-only semantic record. Its decision SHA-256
is the unique key; an identical retry verifies the stored fields, while a
different record at that key fails. Canonical candidate, selected, and
superseded decision references must be UUIDs at this PostgreSQL boundary. The
store alone creates no resolution decision and publishes no canonical fact.

`FootballDataUkTeamCrosswalkV1` maps an exact provider label only after review.
`resolve_football_data_uk_team` creates an append-only `ResolutionDecisionV1`
when that reviewed mapping agrees with one context-qualified canonical candidate.
An unreviewed label is never auto-merged: it remains review-required when
candidates exist and is quarantined when none exist.

`FootballDataUkMatchResolutionContextV1` requires those reviewed canonical
competition, season, and ordered team IDs together with the provider match date.
`resolve_football_data_uk_match` auto-accepts only one date-compatible canonical
candidate, recording an append-only `ResolutionDecisionV1`. No candidate or a
date mismatch is quarantined; multiple candidates require review. Scores and
results are deliberately absent from match identity.

## Immutable layout

The local production store writes beneath a configured data root:

```text
raw/
  provider=statsbomb_open_data/
    snapshot=<git-sha>/
      data/...

manifests/
  provider=statsbomb_open_data/
    snapshot=<git-sha>/
      scope=<resource-set-sha256>/
        source-manifest-v1.json
```

Provider paths must be normalized relative POSIX paths. Absolute paths, parent traversal, backslashes, symlink escapes, and immutable-path conflicts are rejected.

Publication writes a temporary file on the target filesystem, flushes it, and creates the final path with an exclusive hard link. Concurrent writers can never replace an existing final file. Temporary files are removed after success or failure.

## Idempotency and recovery

The manifest scope key is deterministic for provider, source revision, resource paths, and media types. A completed identical rerun verifies the manifest and raw checksums without network access or file modification.

If an interrupted first acquisition preserved some raw files but did not publish a manifest, the retry fetches those resources and byte-compares them before reuse. If a manifest exists but a raw file is missing, the resource may be restored only when fetched bytes match the manifest checksum and size. Existing changed bytes are never overwritten.

Checksum conflicts use the stable `SB_SOURCE_CHECKSUM_MISMATCH` code defined by the StatsBomb quality policy. They are fatal for the acquisition scope.

## Storage evolution

`ImmutableRawStore` currently provides the local filesystem implementation used for development and deterministic tests. A later object-store implementation must preserve the same exclusive publication, checksum, path, manifest, retry, and attribution contracts.

## Reep identity evidence

Use the dated v1 download distribution, not the frozen v0 CSV interfaces. The
packaging schema currently calls its selection/release documents
`reep-public-selection/v1` and `reep-public-release/v4`; these are distinct from
the register's v1 data model. Verify the pinned release hash and the declared
length/hash of `bridges.csv.gz` and `redirects.csv.gz` before extracting evidence:

```sh
uv run --locked python -m football.identity.reep \
  --release /path/to/release.json --release-sha256 <verified-release-sha256> \
  --inventory /path/to/exact-native-ids.json --artifact-root /experimental/root
```

The inventory is a JSON array with exact `provider`, `namespace`, and
`external_id` strings. Translate provider codes explicitly when constructing it
(for example MatchForge `statsbomb_open_data` to Reep `statsbomb` with
`offline_team`, `offline_competition`, `offline_match` or `offline_player` for
the corresponding open-data IDs; ESPN athletes use `person`). Extra fields
can identify existing Resolution Center cases. The reader keeps release hashes,
original bridge fields and redirect chains, rejects conflicting IDs, and writes
immutable review evidence through the existing file store. It never writes
mapping or admission decisions. Confidence and a shared Reep ID cannot override
UUID-origin contradictions, missing source anchors, historical knowledge times
or player membership/minute requirements. Check the release's own quality gates
separately; downloadable does not mean qualified.

ClubElo's `ratings_archive` normalizer consumes the inspected seven-column CSV
format through the existing normalization CLI. Keep the archive repository,
revision, original URL and acquired bytes in source evidence. `From` is the
rating's source calendar date; `To` stays in the raw CSV and does not establish
intraday availability or a MatchForge membership interval. Acquisition/knowledge
time remains the actual collection time. Daily CSV labels differ from website
slugs, so team references remain anonymous until the identity owner accepts an
exact mapping. This archived path does not establish current website/Vega access,
complete rating history, or permission to redistribute provider data.

Sofascore's `retained_event`, `retained_statistics`, `retained_lineups` and
`retained_incidents` resources read the inspected upstream research envelopes.
Keep the Git revision/URL, exact envelope, original provider URL/fetch clock and
`trimmed` flag. The reader validates fixture/family scope and reports
`__trimmed__` omissions. Source fetch time never becomes MatchForge knowledge
time. These samples do not prove live access, complete seasons or full lineups.
Player `teamId` can identify a club outside the sampled fixture, so it does not
bind the match team or establish historical membership. Unsupported measurements
and periods remain findings; partial-period xG is not a match-total observation.
No upstream browser challenge-solving transport is used.

FBref's `archived_match_html` resource consumes retained original match pages.
Archive containers and extracted members keep separate hashes/registrations;
member keys include the parent archive hash and the native match ID. The parser
checks the original canonical URL, scorebox team/competition IDs and match-specific
summary table IDs before emitting observations. It reads visible or commented
HTML tables without running scripts. Player minutes, shots, cards, passing and
other supported fields come from individual match rows; footer aggregates are
excluded. An explicit venue Unix epoch provides a native UTC claim. A venue date
without that epoch remains `DATE_ONLY`. Score/status and settlement qualification
remain unknown where the source does not establish them. Acquisition/knowledge
time remains the archive's actual local acquisition time.

Classify these pages as `FBREF_ARCHIVED_HISTORICAL`. A community SQLite export is
`THIRD_PARTY_FBREF_DERIVED`; inspecting its tables does not turn it into an official
current response. Neither archive establishes current basic-table access or
restores the advanced feed removed in January 2026. Keep original-provider and
archive reuse limitations visible, and obtain independent identity, time and
target-use decisions before historical modelling.
