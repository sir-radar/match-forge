# PitchAPI domain-stratified V2 Rust validation policy proposal

Status: `OWNER APPROVAL REQUIRED — DO NOT RUN`

Protocol: `PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2`

The approved V2 policy requires a mandatory Rust result, but the repository
contains only `simulation-core 0.1.0` scaffolding. This proposal makes the
remaining material choices explicit. It does not authorize implementation or
simulation.

## Engine and build identity

- Engine package: `simulation-core`.
- Proposed engine algorithm version: `pitchapi-score-categorical-v1`.
- Toolchain: `rustc 1.97.1-aarch64-apple-darwin`, edition 2024.
- Current pre-implementation identities: `Cargo.lock`
  `8b691b8359186f1770e2961e1a5b269d819c475b575e6dc28d92f8e4c826b3e8`;
  crate manifest
  `2cb97a61cffdc1748a46b3891548abb8cdb7a8058c61cd27df4598b87433a3f2`;
  scaffold source
  `6364acfead024b3c8c9b50455de8a179741117402d8e8a438ccae47aba2b127d`.
- An accepted implementation must replace the scaffold source identity with
  exact engine commit, source-tree hash, release-binary SHA-256, target triple,
  compiler verbose version, Cargo.lock hash, build profile and CPU feature set.

## Input contract

Python remains responsible for point-in-time data, model fitting and the final
analytic distribution. Rust receives sealed canonical JSON only:

1. protocol, target, forecast, model-artifact and probability hashes;
2. an ordered list of exact `(home_goals, away_goals, probability)` atoms;
3. one final `UNRESOLVED_TAIL` atom;
4. independently calculated analytic probabilities for the 62 required event
   indicators below; and
5. the policy and seed-schedule IDs.

Atoms are ordered by home goals then away goals, with the tail last. Every
probability must be finite and in `[0,1]`; exact-score atoms must be unique; the
sum must differ from one by at most `1e-12`; unresolved tail must be at most
`1e-12`. Inputs outside these rules fail. Rust must never clip, floor or
renormalize them. The compact `5+ by 5+` cell is not a valid sampling atom
because it cannot determine win/draw/loss; exact atoms are therefore required.

Canonical JSON is UTF-8, sorted keys, no insignificant whitespace, no NaN or
Infinity, and SHA-256 bound before parsing. Parsed decimal probabilities use
IEEE-754 binary64. Cross-language golden fixtures must confirm the exact parsed
bits and cumulative sums.

## Algorithm and RNG

Use inverse-CDF categorical sampling over the ordered atoms. Cumulative sums
are binary64 in fixed atom order; choose the first cumulative value strictly
greater than `u`. A draw equal to one is impossible.

The proposed RNG is SplitMix64 with unsigned 64-bit wrapping arithmetic and
the published constants fixed in the implementation tests. For each draw,
`u = ((next_u64 >> 11) + 0.5) / 2^53`. No system entropy, thread-local RNG,
clock, hash-map order or platform-dependent reduction is allowed.

The base seed commitment is
`SHA256("PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2" || policy_sha256 || forecast_probability_hash)`.
Each of four batches uses the first eight bytes, interpreted big-endian, of
`SHA256(base_commitment || canonical_match_id || uint32_be(batch_index))`.
Batch indices are 0 through 3. Targets and batches may run concurrently, but
their integer counts are merged in sorted target/batch order.

## Simulation count and precision

There are 62 registered indicators per target:

- 36 compact score cells (`0..4,5+` by `0..4,5+`);
- 3 1X2 outcomes;
- BTTS yes/no (2);
- over/under for 0.5, 1.5, 2.5, 3.5 and 4.5 (10);
- home and away clean-sheet yes/no (4);
- total goals `0,1,2,3,4,5+` (6); and
- unresolved tail (1).

Use exactly 112,460 draws per target, four batches of 28,115. The initial
normal approximation is `ceil(z^2/(4h^2))=112264`, where `h=0.005` and
`z=Phi^-1(1-0.05/(2*62))=3.3505709013`. The count is increased to the smallest
multiple of four whose worst-case exact two-sided Clopper-Pearson 95%
familywise Bonferroni half-width is at most 0.005: 0.004999935 at 56,230
successes. At `p=0.5`, the expected standard error is about 0.001491 and the
marginal 95% normal half-width is about 0.002922.

## Parity, convergence and tolerances

- Report exact integer counts and two-sided Clopper-Pearson intervals for every
  indicator. Analytic parity passes only when every analytic probability lies
  inside its 99% familywise Bonferroni interval (`alpha=0.01/62`).
- Precision passes only when every two-sided 95% familywise Bonferroni interval
  has half-width at most 0.005.
- Batch stability passes only when, for every indicator, the largest difference
  between any two batch proportions is at most
  `sqrt(ln(2*372/0.01)/28115)`, approximately 0.01998. This is a 1% familywise
  Hoeffding bound over 62 indicators and six batch pairs.
- Replay the same input twice with different worker counts. Canonical output
  bytes and all counts must be identical.
- An independent Python reference must pass fixed golden vectors for SplitMix64,
  seed derivation, atom selection and all 62 event reductions. RNG words,
  selected atom indices and counts must match exactly.
- Probability normalization and tail tolerances are `1e-12`. No general
  floating-point parity tolerance replaces the count/interval checks.

Any sampled `UNRESOLVED_TAIL`, invalid input, hash mismatch, non-finite value,
arithmetic overflow, unsupported schema, timeout, cancellation, incomplete
target, replay mismatch, golden-vector mismatch, precision failure, parity
failure or stability failure prevents `PASS`. Proven invariant violations are
`FAIL`; timeout, cancellation, resource exhaustion or unavailable mandatory
reference evidence is `INCONCLUSIVE`. Neither status permits a complete V2
disposition.

## Output contract

Emit a new immutable `SimulationValidationArtifactV1` for each target and an
aggregate manifest. Include the required fields in
`docs/contracts/simulation-validation-v1.md`, the 62 analytic probabilities,
counts, intervals, half-widths, batch results, tail draws, elapsed time, peak
memory, input/output hashes, engine/build identity and failure codes. Output
JSON uses the same canonical encoding as input. Raw simulation-derived
frequencies are validation evidence only and never replace analytic forecasts.

## Required owner decision

Owner approval must freeze this policy's exact SHA-256 before implementation.
Implementation acceptance then requires golden fixtures, deterministic replay,
resource measurement and the full repository suite on non-evaluation synthetic
inputs. A separate owner authorization is still required before any V2
simulation or evaluation run.
