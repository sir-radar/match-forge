# Canonical ingestion

## Boundary

`football.ingestion.StatsBombCanonicalIngestor` consumes an `AcquisitionResult` and a PostgreSQL connection. It supports StatsBomb competition, season-match, lineup, and event resources. 360 resources are registered with pending processing state for a later phase.

Before opening a database transaction, ingestion re-reads the immutable manifest and every declared raw resource. Paths must remain beneath the configured data root, symlinks are rejected, reads are bounded, and sizes and SHA-256 checksums must match the manifest.

## Transaction and lineage

One transaction registers the provider, acquisition-manifest scope, and resources, then publishes all canonical rows, provider mappings, observations, lineup hierarchy, and event catalogue entries. Parsing, missing mappings, inconsistent teams, temporal ordering errors, and database failures cannot leave partial source registration or canonical state.

The deterministic manifest scope directory is stored as `source_identity`. Distinct scopes at the same pinned Git revision therefore remain independently registered. An identical completed rerun reuses the same source snapshot and creates no duplicate canonical, mapping, observation, participation, stint, or card rows.

Successfully consumed resources move to `parse_status = 'parsed'` and `validation_status = 'valid'`. A source snapshot becomes `validated` only when none of its resources remain pending.

## Canonical publication order

```text
competitions → seasons → teams → matches → match teams
                                      ↓
                         players → lineup participation
                                      ↓
                           position stints and cards
                                      ↓
                         ordered event catalogue
```

Canonical UUIDs stay provider-neutral. Provider identifiers live in mapping and observation tables. One provider-scoped advisory transaction lock serializes canonical publication without consuming one PostgreSQL lock per event. Event resources resolve referenced entities once, stage each match through PostgreSQL `COPY`, and publish mappings and observations with set-based statements. Later snapshots reuse mappings, advance `last_seen_at`, close the previous half-open knowledge interval, and publish a new source-linked observation.

Provider timestamps are parsed into `TIMESTAMPTZ` only when the source includes a timezone. Raw text is always retained when present; timezone-naive StatsBomb timestamps remain raw-only.

## Validation behavior

Required identifiers, JSON shapes, dates, local times, scores, lineup membership, jersey numbers, cards, event UUIDs, event clocks, periods, and source indexes are validated before publication. A lineup must contain exactly the match's two current teams. Event and possession teams must belong to the event's match. Duplicate players, event IDs, event resources, per-match event indexes, and conflicting same-snapshot event facts fail the whole ingestion.

Contradictory player metadata is preserved differently because the pinned source can legitimately
contain multiple variants for one provider player. Every lineup and event variant is registered in
`player_source_facts` with exact snapshot and resource lineage. Canonical player fields contain only
single-valued consensus; a disputed field is `NULL` and `fact_status` is `conflicting`. Validation
emits `SB_CONFLICTING_PLAYER_FACT` with all variants instead of selecting a winner or rewriting raw
provider bytes.

StatsBomb position `from`/`to` values are preserved as provider observations. Real source rows can be non-monotonic across periods and clocks, so ingestion validates presence, shape, positivity, and paired nullability without inventing corrected intervals. Raw bytes remain available for the later data-quality and quarantine phase.

Event resources can be ingested with their match bundle or as a later manifest scope. Existing rich team and player observations are reused; an event-only scope does not replace them with partial event references. New event observations close prior half-open knowledge intervals while retaining stable event identity and match linkage.

## Canonical resource decisions

The Architecture V2 shadow path keeps normalized observations immutable. A
`CanonicalCandidate` binds every entity reference to identity-owner evidence and
identifies one resource context, such as a fixture result with a specific score
basis or one team's statistics for one fixture and period. Reported validity
intervals remain separate contexts. Event and shot units
require their own identity; a fixture ID cannot identify an individual event.

`resolve_canonical_resource` consumes an explicit `ConflictRecordV1` selection.
It records exact-value supporting and conflicting observations in a
`DecisionRecordV1`; it does not infer a winner from provider counts or confidence.
Review and quarantine decisions expose no selected value. Sources retain their
original IDs, values, bytes and clocks.

Prepare immutable decision and identity-evidence files before calling
`CanonicalResolutionRegistry.register`. Registration verifies observation hashes
and the existing persisted `ResolutionDecisionV1` evidence or an exact R2
admission proof, then commits the conclusion and all lineage together. R2 proofs
come from `IdentityRepository.admission_proof_at`, which reuses the existing
admission/correction owner at the requested knowledge cutoff and binds the full
source decision with its native provider identity. Registration recomputes that
proof; changed, unregistered, superseded or revoked evidence cannot authorize a
new conclusion. Earlier valid cutoffs retain their original proof. A bare mapping
or confidence is insufficient, and anonymous source-record references still
require independently verified record scope. Other identity owners need an
explicit publication adapter before their evidence can be registered here.
No identity is created by the canonical resolver.

Canonical revisions are append-only, reference the current predecessor within
the same resource context, and cannot fork. Knowledge starts at database
publication time. Reads require the context hash and an explicit knowledge
cutoff; a later review or quarantine remains visible instead of exposing an older
winner. Read the selected typed observation separately through
`ObservationArtifactStore`. This shadow path does not replace current product
serving or historical eligibility rules.

## Resource coverage snapshots

`football.coverage.resources` keeps provider coverage separate from canonical
coverage. Provider snapshots count explicit expected, observed and qualified
native/source-record unit keys. Canonical snapshots use MatchForge competition
and season IDs, count distinct qualified canonical unit IDs, and retain each
supporting provider. Multiple provider observations or retries cannot increase
the count of one canonical fixture. Provider coverage can remain partial while
qualified sources together provide complete canonical coverage.

Eligibility owners supply the frozen expected unit set and already-qualified
inputs, with evidence references and an explicit knowledge cutoff. For fixture
resources, qualification must establish the required resource completeness
before supplying a fixture ID; one partial team row is not a complete fixture.
Coverage code does not infer identity, qualify raw observations, derive an
expected total from observed rows, or rewrite R3 provider-specific history.
Qualified provider units must be observed; qualified units must belong to any
declared expected set. Unexpected raw observations remain in the input evidence.

Ratios are distinct qualified units divided by the explicit expected count.
An unknown or empty expectation produces an unknown ratio and status, never a
claim of complete coverage. Positive expectations are complete only when every
expected unit is qualified. Provider and canonical reports retain their own
metrics and inputs.

`prepare_coverage` writes immutable canonical JSON containing the input sets,
metrics and evidence references. `CoverageRegistry` registers provider and
canonical summaries in separate tables after verifying those bytes. Canonical
competition/season pairs and supporting providers must be registered. Queries
require both input and publication knowledge to be available at the requested
cutoff; a later calculation of an older input snapshot cannot replace a newer
snapshot. Artifact reload verifies checksum, identity, scope and metrics.
Existing production coverage reports remain active until parity and cutover.

## Structured quality assessments

`football.validation.quality.DataQualityAssessment` records a stable subject
reference and resource, input knowledge cutoff, assessment time, and eight
independent dimensions: identity state, completeness, freshness, precision,
consistency, temporal integrity, provenance state, and conflict state. Each
`QualityDimension` retains its domain owner's state, actionable reason codes,
required action and retained evidence references. Existing validation findings
and policy decisions supply these values; the report does not invent thresholds
or infer missing checks from the absence of findings. Unknown dimensions must
be reported explicitly, with the action needed to assess them.

There is no combined confidence score or automatic acceptance result. A complete
resource can still have unresolved identity or conflicting evidence. A positive
identity state reports an existing owner's conclusion; canonical publication
still verifies that owner's independent identity proof. Quality reports cannot
be used as `CanonicalBinding` identity evidence.

`to_decision_record` binds all dimensions and their evidence in the existing
immutable `DecisionRecordV1` format, with a `data_quality_assessment` type and
`ASSESSED` disposition. Its checksum and deterministic ID identify the exact
assessment. The inverse adapter rejects missing or unknown dimensions, malformed
clocks and unsupported versions. Both clocks require timezones, and assessment
time cannot precede the input knowledge cutoff. Reports describe input quality;
they do not alter historical eligibility, qualification, quarantine, promotion
or production serving decisions.
