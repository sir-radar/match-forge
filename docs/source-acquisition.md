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

MatchForge is a private, local, non-commercial experimental research project,
not intended for distribution, resale, or external publication of provider data.
Commercial-use and redistribution rights are not sought for this research scope;
this does not imply that other provider restrictions cease to apply.

### Standing owner decision: provider-wide research acquisition

The repository owner has expressly authorized MatchForge to **pursue automated,
including bulk, research acquisition across every configured or future football
data provider**, not only FotMob. The decision covers discovery, historical
backfills, incremental synchronization, raw retention, validation, normalization,
identity reconciliation, and eligible downstream recovery, within MatchForge's
existing architecture and scientific gates.

The owner's instruction is to proceed autonomously with technically accessible
research acquisition, even where published provider terms restrict automated or
bulk access, rather than repeatedly requesting the same owner approval. This
records the owner's risk decision; **it is not a statement that a provider has
given consent, a licence, or a contractual waiver**. Maintain an accurate,
source-specific record of terms, permissions, account entitlements, retention
limits, attribution obligations, and any unresolved legal or contractual risk.
Do not describe the access as provider-authorized unless independent evidence
establishes that fact.

Do not bypass authentication, CAPTCHAs, anti-bot protections, paywalls, account
boundaries, or other technical access controls. Respect enforced rate limits,
provider quotas, and the existing `ProviderRuntimePolicyV1`; never use account
multiplication, credential misuse, or technical circumvention to increase
capacity. Research and use legitimately available alternative sources whenever
access is denied or unavailable. Third-party data must not be redistributed or
published unless the corresponding rights permit it.

This standing owner decision replaces the need for repeated **project-owner**
approval of the same acquisition objective. It does not approve new paid plans,
new credentials, additional spending, technical bypasses, destructive data
changes, scientific evaluation, model promotion, or Architecture V2/V4 cutover.
Document genuinely new decisions separately. Provider-specific restrictions
remain recorded as facts, but should not repeatedly halt unrelated research,
recovery, or provider work.

### Development acquisition routes

The existing [development decision](evidence/owner-decision-public-development-data-access-2026-10-31.json)
also covers ordinary public JSON/browser endpoints, HTML and embedded state,
CSV/JSON feeds, open datasets and maintained community wrappers. Use the existing
cache, immutable storage, request budgets, quotas, cooldowns and orchestration.
Record the actual route and external restrictions separately from technical
availability. Access-control bypass remains prohibited. New experimental outputs
remain `EXPERIMENTAL_ONLY` until independently qualified; public access does not
prove canonical identity, source meaning or historical availability. MatchForge's
own Admin authentication, Origin checks and consequential-operation approvals
remain unchanged.

### Source verification and recovery priority

Prefer primary/official sources for missing historical facts. When primary
records are unavailable, two genuinely independent credible sources may support
a corroborated factual observation if existing identity, provenance, temporal,
and validation contracts permit it. Mere agreement in names or scores does not
establish a provider-native identity. Preserve source URLs, observation times,
independence analysis, original bytes and immutable hashes. Never represent
newly corroborated data as a replacement for a missing, checksum-registered
original. Prioritize data that measurably improves eligible football history and
forecast readiness; never weaken qualification gates to improve status counts.

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

## Provider capability registry

### Provider-wide execution and access register

The standing decision above applies to each row below and to future adapters.
This register was checked against provider documentation on 3 November 2026.
Advertised coverage is not proof of retained coverage or this account's access.

| Provider | Existing acquisition owner and resources | Coverage and access limits |
| --- | --- | --- |
| API-Football | `ProductSync` / `HistorySyncWorker`; fixtures, results, standings and enabled lineup/injury context; additional capability ports | League/season coverage and credentials are account-specific. Keep `API_FOOTBALL_MAX_HISTORY_SEASON` and persistent daily/minute quotas. [Official rate limits](https://www.api-football.com/news/post/how-ratelimit-works) and [coverage guidance](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide) do not authorize a larger plan. |
| football-data.org | Existing explicit-crosswalk history fallback; competition fixtures, results and standings | v4 resources and historical access depend on subscription. The free plan advertises ten calls/minute; history is separately offered in paid plans. Keep the existing client pacing and entitlement failures. [API reference](https://www.football-data.org/documentation/quickstart), [plans](https://www.football-data.org/pricing). |
| FotMob | `OperationalProviderSync`, `provider_history_scopes` and `FotmobSource`; calendar/season results and match, team and player resources | Seasons come from native catalogues; detail depth varies. [Published terms](https://www.fotmob.com/tos.txt) restrict automated/systematic use. The owner decision is recorded separately; ordinary access failures stop that source without bypasses. |
| PitchAPI | Existing operational client, season checkpoints and `PitchApiSource`; results, events, shots, statistics, lineups and ratings | [Reference](https://pitchapi.dev/) advertises catalogue history from 2021 and no daily allowance, with a fair-use burst guard and `Retry-After`. Missing analytics remain missing. Current access does not establish historical knowledge or compatible xG-series identity. |
| OpenFootball | Existing commit-pinned mirror and bulk JSON importer | [football.json](https://github.com/openfootball/football.json) publishes public-domain fixtures/results, with season directories from 2010/11. File coverage and update completeness vary; it does not supply event, player, injury or xG data. |
| Football-Data.co.uk | Existing bounded CSV/ZIP discovery, immutable manifests and bulk importer | Results/statistics columns differ by country and season; odds remain outside baseline features. [Column notes](https://www.football-data.co.uk/notes.txt) and the [fair-use policy](https://football-data.co.uk/contact.php) distinguish personal/academic use and light automated downloads (at most twice weekly) from heavy automated training projects. The catalogue returned HTTP 429 during this review; do not evade it or infer a complete current catalogue. |
| StatsBomb Open Data | `SourceAcquirer`, pinned adapter and canonical ingestion | [Open repository](https://github.com/statsbomb/open-data) supplies selected competition/seasons, events, lineups and selected 360 files. Preserve its licence and attribution. Broader acquisition does not resume paused model research, protected evaluation, 360 normalization or automatic product-history admission. |
| Flashscore | `FlashscoreSource` and native normalizers through the existing source pipeline; experimental retained summaries, events, statistics and lineups | [Terms](https://www.flashscore.com/terms-of-use/) restrict substantial extraction and automated requests. Public pages are research evidence, not an undocumented API contract or provider-native crosswalk. |
| Soccerway | `SoccerwaySource` through the existing source pipeline and shared native resource contracts; experimental only | [Terms](https://www.soccerway.com/terms-of-use/) impose extraction/automation restrictions. Flashscore and Soccerway are both Livesport services: do not assume their agreement supplies independent corroboration. |
| TotalCorner | Documented candidate; no configured production adapter | [Official API](https://www.totalcorner.com/page/api) requires a VIP token and account timezone/language; it advertises history from 2014 and 30 requests/minute in ten-second windows. No new subscription, token or paid boost is authorized by this task. |
| Sportmonks | Existing external-prediction integration, not a general historical import adapter | [Football API](https://www.sportmonks.com/football-api/) offers results, player/context resources and optional xG. An existing prediction token does not establish historical data entitlements. Keep prediction collection separate from model inputs. |

Use the existing provider-specific command or capability port rather than adding
a second acquisition engine. Before enabling a new provider, establish its native
resource/schema contract, actual credentials and coverage, runtime policy,
immutable retention/provenance and normalization support. Unknown support stays
unknown. Resource capabilities and source registrations do not by themselves
admit identities, complete a season or qualify forecasting markets.

For measurements, count retrieved resources, parsed records, admitted identities,
eligible history and newly available forecasts separately. Live background-worker
additions are not attributable to a controlled recovery run. Preserve a fixed
knowledge cutoff for before/after historical comparisons and record the actual
later admission time.

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

Ordinary private research follows the provider-wide standing owner decision
under **Project use policy**. Research acquisition and technical feasibility
must be evaluated separately from third-party contractual permission. Record
published terms, current account entitlements, source capabilities, restrictions,
and observed technical access accurately; do not infer provider consent from
public accessibility or from non-commercial project status. Within existing
approved request budgets, Codex may research and execute bounded acquisition
without repeatedly asking for the same project-owner approval. New spending,
new accounts, expanded paid quotas, bypasses of access controls, and any other
separately governed actions remain subject to their existing authorization rules.

Research acquisition is not Evaluation V2 qualification or publication
approval. Provider-specific source limits, immutable retention evidence, model
provenance, point-in-time requirements, and the evaluation firewall remain
independent gates. A source unsuitable for Evaluation V2 can still be studied
and reported as experimental evidence without silently promoting its outputs.

Research contract fixtures and sanitized, bounded technical checks do not
qualify a provider for Evaluation V2. Evaluation qualification additionally
requires complete frozen coverage, exact source and xG-series identity,
permitted immutable retention, correction/revision lineage, stable traceable
identifiers, source hashes, and every applicable corpus and firewall rule.
Experimental outputs must be labelled `EXPERIMENTAL_ONLY` and cannot be used as
Evaluation V2, promotion, or production evidence.

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

That qualification restriction concerns the Evaluation V2 adapter. The existing
operational PitchAPI client and historical season checkpoints use their separate
contracts, as listed in the provider register above; their acquisition is not
Evaluation V2 qualification.

TotalCorner is a gated `tier_b`/`tier_c` candidate under the official JSON REST
API (`/v1/`). Technical enablement still requires valid credentials, account
timezone/language, documented coverage scopes, and a compliant provider runtime
configuration. Record its access terms and any restrictions separately under
the provider-wide standing owner decision; do not misstate owner authorization
as provider consent. Its aggregate statistics cannot substitute for Tier A event
geometry, and provider-defined fields such as `dangerous_attacks` retain provider
provenance. Evaluation V2 qualification remains separately gated.

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

Snapshots from the PostgreSQL lifecycle reader include `unmeasured_fields` and
`PROVIDER_MEASUREMENTS_UNAVAILABLE` when that scope has no durable measurement
for a field. Consumers must treat the named fields as unavailable, including
zero counters and the legacy `CLOSED` circuit value. These placeholders do not
establish provider health. Measured snapshots without missing fields keep their
existing serialization and digest. The reader also lists `current_state_fields`
for job discovery, retry and processing-failure counts. These describe current
job state; an earlier observation time does not reconstruct their past values.

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
