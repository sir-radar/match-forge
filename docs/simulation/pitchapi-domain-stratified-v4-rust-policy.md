# PitchAPI domain-stratified V4 Rust validation policy

Status: `PROPOSED FROZEN FOR OWNER REVIEW — EXECUTION NOT AUTHORIZED`

Protocol: `PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V4`

This policy corrects the V3 evaluation-wide multiplicity defect. It was designed
from synthetic cases, the development model contract, and the minimum retained
V3 pre-failure input. No additional evaluation outcome was inspected, and no
V3 metric was produced or used.

## Engine and input

- Engine package: `simulation-core`.
- Algorithm: `pitchapi-score-categorical-v2`.
- Seed schedule: `pitchapi-v4-splitmix64-sha256-v1`.
- Input schema: canonical UTF-8 JSON with sorted keys and no insignificant
  whitespace, NaN, or infinity.
- Input bytes must match their supplied SHA-256 before parsing.
- Exact score atoms are ordered by home goals then away goals, followed by one
  `UNRESOLVED_TAIL` atom.
- Probabilities must be finite and in `[0,1]`; their sum must differ from one by
  at most `1e-12`; unresolved tail must be at most `1e-12`.
- Rust recomputes all 62 analytic indicators from the score atoms and requires
  each supplied analytic value to agree within `1e-12`.
- Invalid input is rejected without clipping, flooring, or renormalization.

## Sampling and determinism

Use SplitMix64 and inverse-CDF categorical selection exactly as V3. Use exactly
`112,460` draws per forecast in four fixed batches of `28,115`.

The base seed commitment is:

```text
SHA256("PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V4" || policy_sha256 || forecast_probability_hash)
```

Each batch seed is the first eight bytes, interpreted big-endian, of:

```text
SHA256(base_commitment || canonical_match_id || uint32_be(batch_index))
```

Batch indices are `0..3`. Replay every input with one and four workers. Seeds,
counts, aggregate statistics, status, and canonical output bytes must match
exactly. Determinism is a separate hard gate from statistical parity.

## Distribution-level parity gate

Validate the 36-category compact score matrix (`0..4,5+` by `0..4,5+`) as one
multinomial distribution. Let:

```text
TV = 0.5 * sum_i |p_i - p_hat_i|
K = 36 compact score categories
F = 1,424 preregistered forecast validations (712 targets * 2 models)
n = 112,460 draws per forecast
alpha_global = 0.01
```

Use the Bretagnolle-Huber-Carol multinomial concentration bound plus a union
bound across all `F` forecasts:

```text
TV_limit = 0.5 * sqrt(2 * (K * ln(2) + ln(F / alpha_global)) / n)
         = 0.012794580429261083
```

`TV > TV_limit` is `FAIL`. Under the intended distribution, the probability
that any of the 1,424 forecast validations fails this parity gate is at most
`0.01`. This is an evaluation-wide familywise guarantee, not a per-forecast
claim.

Because total goals, 1X2, BTTS, clean sheets, and over/under markets are
deterministic aggregations of the score matrix, their probability errors are
bounded by score-matrix total variation. Report all 62 indicator errors, but do
not apply 62 independent hard gates.

## Warning threshold

For descriptive localization, use a simultaneous Hoeffding threshold across
all 62 indicators and all 1,424 forecasts:

```text
event_warning_limit = sqrt(ln(2 * 62 * 1,424 / 0.01) / (2 * 112,460))
                    = 0.008613326107968184
```

If total variation passes but any indicator absolute error exceeds this limit,
return `PASS_WITH_WARNINGS`. Indicator warnings do not replace or weaken the
distribution-level hard gate.

## PASS, WARN, and FAIL

- `PASS`: all identity, input, normalization, tail, determinism, and total-
  variation gates pass; no indicator warning fires.
- `PASS_WITH_WARNINGS`: all hard gates pass, but at least one descriptive
  indicator exceeds `event_warning_limit`.
- `FAIL`: any identity, input, normalization, analytic-reduction, unresolved-
  tail, serial/parallel replay, arithmetic, or total-variation gate fails.

Clopper-Pearson cell intervals and batch-difference statistics may be reported
as diagnostics. They are not V4 acceptance gates.

## Offline qualification

Before requesting V4 execution authorization, the implementation must pass:

- independent analytic Poisson checks;
- deterministic golden counts;
- asymmetric `1-4`, `4-1`, `0-5`, `5-0`, `2-3`, and `3-2` tests;
- low-, moderate-, and high-rate synthetic distributions;
- compact score-matrix normalization;
- 1X2, total-goal, BTTS, clean-sheet, and over/under aggregation checks;
- exact one-worker/four-worker replay;
- fail-closed malformed-input and parity-failure tests.

Simulation frequencies remain validation evidence only. They never replace the
analytic forecast.
