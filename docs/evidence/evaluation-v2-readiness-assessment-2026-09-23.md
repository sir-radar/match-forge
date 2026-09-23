# Evaluation V2 readiness assessment — 2026-09-23

Status: `BLOCKED — OWNER PROVIDER-SCOPE DECISION PREPARED`

This assessment accepts the completed PitchAPI audit as technical evidence. It
does not qualify a provider, admit a corpus, amend a frozen decision, implement
the xG-for challenger, or authorize Evaluation V2.

## PitchAPI qualification result

| Requirement | Result | Category | Evidence or minimum next evidence |
| --- | --- | --- | --- |
| Complete candidate-season manifests | `SATISFIED_TECHNICALLY` | Satisfied | 306 Bundesliga 2023/24 and 380 Ligue 1 2022/23 matches; manifest and deterministic selection hashes matched the pilot. |
| Match shot-resource availability | `SATISFIED_TECHNICALLY` | Satisfied | 686/686 resources succeeded; no missing or malformed resource. |
| Shot xG validity | `SATISFIED_TECHNICALLY` | Satisfied | 17,873 finite values in `[0,1]`; no invalid value. |
| Penalty and period fields | `SATISFIED_TECHNICALLY` | Satisfied | 244 explicit `Penalty` situations; all shots used recognized explicit regulation periods. |
| IDs within the audited snapshots | `SATISFIED_TECHNICALLY` | Satisfied | No duplicate shot ID, duplicate match ID, or team-membership error was observed. |
| Bounded access behavior | `SATISFIED_TECHNICALLY` | Satisfied | 692/702 cumulative attempts, no retry or 429 in the full run, one request/second and concurrency one. The ten unused attempts remain unavailable. |
| Current field meaning | `DOCUMENTED` | Existing evidence can resolve | Official documentation defines `expected_goals` as pre-shot goal probability and documents the situation and ID fields. This does not identify the xG model. |
| Upstream xG supplier and model | `UNKNOWN_BLOCKING` | Unavailable provider information | Official documentation says shot xG is joined from shot data and warns that providers train different models. It does not name the supplier/model for either audited season. Need provider-issued scope-specific supplier and model identity. |
| Model version and one series across both seasons | `UNKNOWN_BLOCKING` | Unavailable provider information | No model/version field or dated series declaration is published. Similar values cannot prove identity. Need provider-issued version history binding both season resources to one series. |
| Corrections and immutable revisions | `UNKNOWN_BLOCKING` | Unavailable provider information | No correction log, response revision, prior-version access, or immutable provider snapshot identifier was found. Need provider-issued revision IDs and retrievable prior versions or a frozen export. |
| Provider ID stability through rebuilds | `FAIL_BLOCKING` | Existing evidence resolves negatively | Current docs call IDs stable, but the 19 September 2026 changelog records an Opta rebuild where match/team/player IDs changed and old IDs returned 404. Need a scope-specific immutable export or durable migration map. |
| Retention and private research use | `UNKNOWN_BLOCKING` | Unavailable provider information | The docs describe free authenticated access and fair-use burst handling, but no governing retention, archive, reuse, or post-access terms were found. Need published terms that explicitly cover immutable private-research retention or equivalent provider grant. |
| Historical point-in-time availability | `UNPROVABLE_FROM_CURRENT_API_BLOCKING` | Cannot be established retrospectively | A response observed in 2026 cannot show when the same fact first became available before a 2022/23 or 2023/24 match. Need contemporaneous versioned snapshots with publication/correction times. New MatchForge snapshots cannot repair this history. |
| MatchForge immutable snapshots and reconstruction | `IMPLEMENTED_NOT_APPLIED` | Internal implementation complete | Existing source manifests, dataset build specs/manifests, checksum verification, mappings, corrections, dependency records, and cutoff-aware repositories provide the internal machinery. Applying them to PitchAPI remains prohibited until retention and source scope are approved. |
| Exact eligible targets and firewall | `NOT_RUN_BLOCKING` | Requires implementation after source approval | Requires retained authorized source snapshots, MatchForge ID mapping, kickoff/lifecycle checks, prior-only histories, exact target-plan hashes, and protected/development intersection checks. Manifest match counts do not prove eligible-target counts. |

Official PitchAPI documentation reviewed on 23 September 2026:

- [API documentation](https://pitchapi.dev/) — endpoint fields, ID claims,
  coverage, xG caveat, and changelog;
- [API-key page](https://pitchapi.dev/get-api-key) — account access only; it
  does not supply the missing retention or version-history contract.

The provider documentation also says every provider's xG model differs and
must not be mixed with another source. That supports MatchForge's existing
single-series rule; it does not establish which series PitchAPI supplied.

## Existing reproducibility infrastructure

No new production contract was added. The required internal functions already
exist and are provider-neutral:

| Required function | Existing implementation | Limitation |
| --- | --- | --- |
| Immutable source snapshot | `SourceManifest`/`SourceSnapshot`, immutable raw publication, `source_snapshots` and resources | MatchForge identity; not a provider-issued revision. |
| Dataset version and SHA-256 | `DatasetBuildSpecV1`, `DatasetManifest`, physical/logical hashes, integrity verifier | Cannot authorize retaining source bytes. |
| Acquisition time | timezone-aware `SourceManifest.acquired_at` and resource observation records | Records MatchForge observation, not past provider publication. |
| Provider/model details | provider capability/resource contracts and model artifact manifests | Unknown upstream values must remain unknown. |
| Corrections/revisions | `BitemporalCorrectionV1`, append-only dependency edges and derived-state invalidation | Requires a provider correction/revision signal to populate accurately. |
| Stable internal IDs | reviewed `ResolutionDecisionV1` and provider mappings | Internal stability does not make provider IDs stable. |
| Deterministic reconstruction | build-spec checksum binds source/canonical refs, policies, feature versions, Git SHA, dependency lock, and configuration | Requires authorized immutable source inputs. |
| Point-in-time access | separate `football_cutoff`, `knowledge_cutoff`, and `knowledge_mode`; cutoff-aware historical repositories | Cannot reconstruct a provider's missing historical knowledge timeline. |

Existing synthetic and repository tests cover immutable retry behavior,
checksum corruption, deterministic build specifications, bitemporal
corrections, ID decisions, dependency invalidation, and cutoff validation. A
new wrapper would duplicate these responsibilities without resolving a
provider gap. PitchAPI raw responses were not retained.

## Evaluation corpus routes

Frozen Decision 2 requires at least three complete independent men's domestic
competition-season groups, at least two competitions and two seasons, at least
120 matches per group, and at least 500 eligible targets after ten prior
matches per team. The protected EPL admission and 280 targets remain
inaccessible. Development La Liga remains excluded.

### Existing StatsBomb route

StatsBomb Serie A 2015/16 is the only qualified independent group. It has 380
matches and 280 eligible targets, with zero protected/development provider
match-ID intersection. The pinned public catalog has no two further complete
men's groups. The route therefore still lacks:

- two independent men's groups;
- another competition and another season;
- at least 220 eligible targets;
- exact membership and final firewall hashes for a three-group corpus.

A licensed, immutable, versioned StatsBomb export for two complete eligible
seasons remains the shortest route that preserves Decision 1's frozen
`shot.statsbomb_xg` field. No such inventory, terms, export, or acquisition
authorization is currently evidenced.

### PitchAPI amendment route

Bundesliga 2023/24 and Ligue 1 2022/23 are technically complete candidate
groups, not qualified groups. They provide only two groups and their exact
eligible-target counts have not been established. They also cannot be combined
with the StatsBomb Serie A xG under the one-series rule.

This route would minimally require all of the following before corpus freeze:

1. resolve every provider blocker in the table above;
2. explicitly replace Decision 1's provider field with a new named,
   versioned PitchAPI/upstream series while keeping the approved mathematics;
3. amend Decision 2 so development and evaluation use that same compatible
   series without accessing protected data;
4. qualify a third complete men's group from the same series, spanning the
   required competition/season diversity;
5. acquire only under a separately approved scope, build immutable snapshots,
   resolve MatchForge IDs, and compute exact eligible-target/firewall hashes;
6. reapprove and freeze the complete pre-registration.

This is a possible future route, not a recommendation to weaken the frozen
rules. Understat, FotMob, Wyscout Open Data, and other reviewed free sources do
not currently supply a better fully permitted, versioned, single-series route.

## Recommendation for the owner provider-scope decision

Record PitchAPI as:

```text
TECHNICALLY_COMPLETE_RESEARCH_ONLY
Bundesliga 2023/24 and Ligue 1 2022/23
No raw retention, ingestion, corpus admission, or Evaluation V2 qualification
```

Do **not** approve either audited scope for Evaluation V2. Do not spend the ten
remaining attempts: none of the blocking facts can be proved by another
current API response.

The minimum evidence needed to reconsider PitchAPI is a published or
provider-issued contract that binds the two candidate scopes to an upstream
xG supplier and model version, permits immutable private-research retention,
provides corrections/revision identity and prior-version access, and explains
ID migrations. Historical point-in-time evidence must also exist; it cannot be
manufactured by a new snapshot.

The next decision is
`Owner decision: approve qualified Evaluation V2 provider scopes`. The
recommended answer is **no qualified PitchAPI scope**. After that, the owner
must choose whether to pursue a licensed/versioned StatsBomb scope, authorize a
fully requalified PitchAPI amendment route, or stop source qualification.

No provider acquisition or adapter engineering is immediately actionable.
`Implement approved Tier A shot acquisition` remains the next engineering
ticket, blocked by the provider-scope and source-route decisions, exact source
rights/version evidence, and a separately approved acquisition scope.

## Preserved constraints

- No API attempt or provider communication occurred during this assessment.
- No PitchAPI raw response was retained.
- No protected source, target, admission, or outcome was accessed.
- Historical evidence, baseline models, and published forecasts are unchanged.
- No frozen feature, corpus, threshold, budget, or ownership decision changed.
- The mandatory Rust simulation requirement is unchanged.

## Verification

- Focused synthetic and repository checks: 60 passed across source acquisition,
  dataset build identity, corrections, ID decisions, dependency history,
  point-in-time access, and PitchAPI validation/audit behavior.
- `make check`: Ruff format and lint passed; strict mypy passed for 194 source
  files; 459 Python tests, one Rust test, and all Go tests passed; Rust Clippy,
  Go vet/golangci-lint, migration and shell validation, Python/Rust/Go builds,
  package builds, and `ProjectStatusV2` validation passed.
- `git diff --check`: passed.
