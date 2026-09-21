# Canonical hashing v1 — proposed executable contract

**Status: proposed**. Approve a single encoding with cross-language golden fixtures before publishing new V1 hashes. Do not recompute, retrofit or reinterpret the hash of any older artifact.

## Two domains, no circular dependency

- `canonical_probability_hash = SHA256(domain_separator || canonical_probability_payload_bytes)` where `domain_separator` is UTF-8 `matchforge/forecast-probabilities/v1\n`. The payload includes **only** probability-bearing forecast outputs and uncertainty from a fixed `ForecastProbabilityPayloadV1` projection.
- `artifact_hash = SHA256(UTF8("matchforge/forecast-artifact/v1\n") || canonical_forecast_record_without_artifact_hash_bytes)`; includes its own `canonical_probability_hash`, immutable lineage, version and cutoff, but never simulation/enrichment. The domain separator is raw bytes obtained by unescaping `\n` to a single LF.
- `simulation_validation_hash` and optional `enrichment_hash` live entirely in their respective sidecars and may reference forecast hashes. The forecast never references these mutable-lifecycle artifacts inside its hashed contents.

## Exact V1 payload projection

```text
schema_version = "ForecastProbabilityPayloadV1"
probability_distributions = {
  home_draw_away,
  home_goal_distribution,
  away_goal_distribution,
  exact_score_matrix,
  score_tail,
  total_goal_distribution,
  btts,
  clean_sheets,
  approved_market_lines
}
expected_goals
uncertainty
```

Each array has an explicit stable index convention, goal-bound inclusive range and tail representation; missing **unsupported** products must be explicitly declared by the forecast product schema, not silently omitted in an existing product. Derived markets must be coherent with the joint score distribution and explicit tail accounting. Any product expansion creates a new projection/schema version. The tuple of `schema_version`, approved distribution policy version and market-line registry version is frozen with the forecast.

## Serialization to freeze before implementation

1. Use a precisely versioned JSON schema and canonical JSON encoding (RFC 8785/JCS for ordering, whitespace and string escaping). JSON object keys are lexically sorted by its algorithm; array order is schema-defined, never rearranged by clients.
2. Store and hash **forecast probability numbers as base-10 strings of exactly 12 fractional digits**, rounded once using a declared round-half-even policy **at forecast sealing**; never round again during API rendering. Nonfinite numbers, `-0`, locale commas, exponent notation and out-of-range values fail. Signed quantities such as model intervals obey their own validated range. The integer representation and precision are a **proposal** requiring compatibility testing with current forecast precision; if destructive, version the projection instead of coercing historical outputs.
3. Represent every optional field as an explicitly schema-defined `null` or absence; require consistent handling. Normalize string identifiers to Unicode NFC before encoding; reject ambiguous duplicated keys. Encode bytes as UTF-8 without BOM and without a trailing newline.
4. Reject incoherent/negative probabilities, loss of required tail mass, unknown lines, mismatched goal support and invalid intervals **before hashing**. The rounded serialized values must satisfy the frozen distribution-coherence tolerance; do not silently renormalize to fix a failed test.
5. Freeze golden fixtures covering key reordering, tiny probabilities, tails, zero representation, escaped text, null, goals > support, and independent Rust/Python/Go encoders. Byte/hash parity is an acceptance gate.
6. Persist and audit hash version, encoder revision and payload bytes or an immutable content-addressed object. `artifact_hash` excludes only its self-referential field, not arbitrary metadata. Request IDs and enrichment/tags do not become immutable forecast fields.

**Important nuance:** the probability hash proves the stored forecast output was not changed by a post-forecast step. It does not, by itself, prove no forbidden tag was read upstream; dependency/taint analysis and integration tests must also prevent that.
