# Public API vs private contracts

**Status:** design proposal; current endpoints have not been inspected. The proposed [OpenAPI spec](openapi.yaml) must be compared with the existing API before implementation. Breaking changes require an explicitly versioned route/migration.

## Classification

- **Public, approved product only:** fixture/forecast IDs, issue and knowledge-cutoff time, horizon, probability distribution and market support, expected goals/intervals where approved, public probability hash, coarse permitted provenance/version identifiers, simulation delivery mode and a linked validated `PASS` indicator only when true, approved optional tag codes and public reasons.
- **Restricted diagnostic/internal:** raw feature snapshots, provider payloads/licences, detailed H2H evidence, lineups with restricted rights, private model parameters, seed schedules, budget/cost, exact calibration fit details, internal risk components, raw incident details, evaluator targets and complete lineage. Internal contract access needs RBAC/audit and must not be automatically surfaced in public schema.
- The API is a projection; `request_id`, current enrichment availability and response headers may vary. For a fixed forecast ID, **forecast-owned fields and hashes must not**.

## Response behavior

`RUST_VALIDATED` requires approved engine, linked immutable simulation evidence `PASS`, matching candidate hash, eligible capability and validated event coverage. `ANALYTIC_ONLY` requires a separate recorded exception and conspicuous label, never fake simulation count or artifact. On required validation failure, surface `SIMULATION_UNAVAILABLE`; older forecasts remain readable. Optional tag sidecar may be absent/partial/unavailable and may not block forecast delivery or mutate probability hash. Unsupported markets are omitted/marked unsupported per versioned product policy, never set to 0 by default.

## Evolution

Freeze error codes, nullable/optional semantics, distributions/tails, numeric precision and deprecation window with the actual existing clients. Use additive compatible optional fields within V1 and a versioned route/schema for incompatible changes. Validate with generated OpenAPI tooling, fixture snapshots, auth/redaction tests, older consumers and backward-compatibility diff. Coordinate read adapters for legacy `FixtureDisplayTagsV1` / `ForecastRiskAssessmentV1` until approved migration to one `ForecastEnrichmentV1` sidecar.
