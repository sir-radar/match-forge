# PitchAPI domain-stratified V3 Rust validation policy

Status: `FROZEN FOR OFFLINE IMPLEMENTATION — EVALUATION NOT AUTHORIZED`

Protocol: `PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V3`

This policy carries forward V2's numerical simulation rules unchanged. The
protocol and seed-schedule identities change only because V3 uses transferable
model artifacts. No evaluation outcome informed this change.

## Engine and input

- Engine package: `simulation-core`.
- Algorithm: `pitchapi-score-categorical-v1`.
- Seed schedule: `pitchapi-v3-splitmix64-sha256-v1`.
- Input schema: canonical UTF-8 JSON with sorted keys and no insignificant
  whitespace, NaN, or infinity.
- Input bytes must match their supplied SHA-256 before parsing.
- Exact score atoms are ordered by home goals then away goals, followed by one
  `UNRESOLVED_TAIL` atom.
- Probabilities must be finite and in `[0,1]`; their sum must differ from one by
  at most `1e-12`; unresolved tail must be at most `1e-12`.
- Invalid input is rejected without clipping, flooring, or renormalization.

## Sampling

Use SplitMix64 with unsigned 64-bit wrapping arithmetic and constants frozen in
the engine tests. For every draw:

```text
u = ((next_u64 >> 11) + 0.5) / 2^53
```

Use inverse-CDF categorical selection in atom order. The first cumulative value
strictly greater than `u` is selected.

The base seed commitment is:

```text
SHA256("PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V3" || policy_sha256 || forecast_probability_hash)
```

Each batch seed is the first eight bytes, interpreted big-endian, of:

```text
SHA256(base_commitment || canonical_match_id || uint32_be(batch_index))
```

Batch indices are `0..3`. No entropy, clock, hash-map ordering, or
platform-dependent reduction is permitted.

## Count, indicators, and gates

Use exactly `112,460` draws per forecast in four batches of `28,115`.

Validate the same 62 indicators as V2:

- 36 compact score cells (`0..4,5+` by `0..4,5+`);
- three 1X2 outcomes;
- BTTS yes/no;
- over/under 0.5, 1.5, 2.5, 3.5, and 4.5;
- home and away clean-sheet yes/no;
- total goals `0,1,2,3,4,5+`;
- unresolved tail.

For every indicator:

- analytic parity must fall inside the exact two-sided 99% familywise
  Bonferroni Clopper-Pearson interval (`alpha=0.01/62`);
- the exact two-sided 95% familywise Bonferroni interval (`alpha=0.05/62`)
  must have half-width at most `0.005`;
- the maximum pairwise difference between batch proportions must not exceed
  `sqrt(ln(2*372/0.01)/28115)`.

Replay every input with one and four workers. Canonical output bytes and counts
must be identical. Any sampled unresolved tail, invalid input, hash mismatch,
non-finite value, overflow, unsupported identity, incomplete target, replay
mismatch, precision failure, parity failure, or stability failure prevents
`PASS`.

## Output

Emit canonical `SimulationValidationArtifactV1` JSON containing identities,
seeds, exact counts, intervals, half-widths, batch counts, tail draws, and
status. Simulation frequencies are validation evidence only and never replace
analytic forecasts.

Evaluation execution remains separately owner-authorized.
