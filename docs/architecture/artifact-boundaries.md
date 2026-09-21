# Artifact boundaries and causal ordering

## Artifacts

1. `ForecastArtifactV1`: sealed, immutable probability-bearing forecast with point-in-time snapshots, model/calibrator and forecast outputs. A canonical probability hash covers only approved forecast outputs; a separate artifact hash covers immutable record content.
2. `SimulationValidationArtifactV1`: immutable evidence linked to the *sealed forecast hash* and approved input/engine fingerprints. Validation is **required for new production publication only after separate implementation, acceptance and activation decisions**; old/analytic research artifacts are not retroactively blocked.
3. `ForecastEnrichmentV1`: optional, append-only, post-publication tags and diagnostics. It references the forecast and its hash but is never hashed into the forecast or used as an input to forecasting.
4. Forecast revisions: fresh `ForecastArtifactV1` objects with later eligible cutoff, a new ID and predecessor reference. Old artifact remains readable.
5. Post-match shock/evaluation artifacts: independent subsequent evidence; never insert into the match's own pre-match feature snapshot.

## Lifecycle

`BUILD → SEAL → [RUST VALIDATE → ATOMIC PUBLISH] → OPTIONAL ENRICH → API PROJECT → POST-MATCH EVALUATE`.

A candidate is internally complete at **SEAL** but not yet public under simulation-required policy. Rust sees only validated parameters/coherent distribution and stable seed schedule, not tags or realized scores. Do not conflate simulation validation with outcome calibration.

## Hash boundaries

- Probability hash: forecast output only, fixed schema and canonicalized encoding; excludes IDs, sidecars and transport metadata.
- Forecast artifact hash: immutable forecast metadata and output, excluding its own hash; never includes simulation/enrichment. No hash cycle.
- Validation hash: immutable simulation evidence, referring to forecast hashes but never the reverse within the forecast artifact.
- Enrichment hash: optional evidence, referring to forecast/validation where appropriate; neither referenced artifact changes because of it.

A public response is a **projection**, not the immutable stored artifact. Request IDs, cache headers, selected latest enrichment and temporary unavailable states may vary while the immutable forecast bytes and forecast-related hashes remain stable. Public/provenance fields are contract-controlled; no raw diagnostics are automatically exposed.

See [forecast schema](../contracts/forecast-artifact-v1.md), [simulation schema](../contracts/simulation-validation-v1.md), [enrichment](../contracts/forecast-enrichment-v1.md), [hashing](../contracts/canonical-hashing-v1.md) and [publication algorithm](../simulation/publication-state-machine.md).
