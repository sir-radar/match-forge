# PitchAPI Rust parity investigation V1

Investigation: `PITCHAPI_RUST_PARITY_INVESTIGATION_V1`

Result: `RESOLVED — D_STATISTICAL_PARITY_POLICY_DEFECT + E_EXPECTED_MONTE_CARLO_VARIATION`

V3 remains permanently closed as
`PROTOCOL_EVALUATION_FAILURE_RUST_PARITY`. It was not rerun. No additional
evaluation outcome was inspected, no model was refit, and no provider/API or
snapshot mutation occurred.

## Exact reproduction

The frozen V3 failure reproduced with the original Rust binary:

```text
PARITY_FAILURE: score:1-4 analytic probability is outside parity interval
```

- Target: `96093e19-361b-53b0-a189-eca42666c280`
- Model: `REFERENCE`
- Input SHA-256: `bae0f12b8f179eb29618d69ef768f54951e3a1b95fdbb19b79970dcc48ba2d53`
- Forecast SHA-256: `65994c4978de57fca312ff97cae5f940f42e1aa7c5873778e5ba157212ec2532`
- Probability SHA-256: `be187e94a147d80446bd90248d79eadb66ab6812d67d266d12d92b22158af241`
- Home lambda: `1.6291133580872224`
- Away lambda: `1.3362479765334259`
- Analytic `P(1-4)`: `0.01115445204787229`
- Rust count: `1115` of `112460`
- Rust probability: `0.00991463631513427`
- Expected count: `1254.4296773037177`
- Batch counts: `272`, `283`, `257`, `303`
- Clopper-Pearson interval: `[0.00883812620640509, 0.011077245439911123]`
- Interval rule: two-sided `alpha=0.01/62`; individual confidence
  `0.9998387096774194`
- Worker count: `1`; one-worker and four-worker aggregate counts matched.
- Frozen Rust binary: `4f4709b38c8d6c72e93c433074fed3d7788eb4018cfddfe67f73ae5f438e209c`

The target normalized resource and target outcome were not read. Reconstruction
used target manifest metadata and strictly prior history. The original execution
had already revealed 55 earlier targets before this failure.

## Analytic oracle

Four independent calculations agreed:

- production: `0.01115445204787229`
- SciPy Poisson PMFs: `0.01115445204787227`
- direct double-precision formula: `0.011154452047872276`
- 50-digit decimal formula: `0.011154452047872274`

Maximum difference was `1.9081958235744878e-17`. The analytic oracle is
correct.

## Rust semantics

Rust sampling is correct. Tests and evidence passed for:

- home/away ordering;
- asymmetric `1-4`, `4-1`, `0-5`, `5-0`, `2-3`, and `3-2` scorelines;
- inverse-CDF categorical sampling;
- normalization and tail handling;
- seed derivation;
- one-worker/four-worker deterministic replay;
- worker partitioning without duplicate or omitted draws;
- serialization and integer aggregation.

The Rust implementation is not defective. The analytic implementation is not
defective. No model artifact is defective; both frozen V3 artifacts remain
valid and unchanged.

## Monte Carlo precision

| Draws | Count | Expected | Observed probability | Absolute error |
|---:|---:|---:|---:|---:|
| 25,000 | 236 | 278.8613 | 0.0094400 | 0.00171445 |
| 50,000 | 475 | 557.7226 | 0.0095000 | 0.00165445 |
| 112,460 | 1,115 | 1,254.4297 | 0.00991464 | 0.00123982 |
| 250,000 | 2,683 | 2,788.6130 | 0.0107320 | 0.00042245 |
| 500,000 | 5,470 | 5,577.2260 | 0.0109400 | 0.00021445 |
| 1,000,000 | 10,942 | 11,154.4520 | 0.0109420 | 0.00021245 |

Error shrinks at the expected Monte Carlo scale. The observed V3 failure is a
legitimate deterministic draw from the intended distribution.

## Multiple comparisons

V3 controlled 62 indicators within one forecast at nominal familywise alpha
`0.01`, but it required all `712 * 2 = 1424` forecast validations to pass.
That creates `88,288` cell tests without evaluation-wide correction.

- Expected false rejections at the nominal cell size: `14.24`.
- Independent approximation of at least one false rejection: `0.9999993466471561`.
- Per-cell alpha needed for a simple one-percent evaluation-wide Bonferroni
  rule: `1.1326567596955419e-07`.

Therefore V3 has a statistical policy defect even though its within-forecast
Bonferroni calculation is mathematically valid.

## Distribution-level evidence

For the exact failing input at 112,460 draws:

- score-matrix total variation: `0.005943222692824432`;
- maximum event error: `0.0013771842739591991`;
- 1X2 maximum error: `0.0013728958282052672`;
- home-goal marginal maximum error: `0.0032733044818157864`;
- away-goal marginal maximum error: `0.0018793840472705603`;
- score mass: analytic `1.0000000000000002`, simulated `1.0`;
- tail draws: `0`.

Six low-, moderate-, high-, balanced-, and asymmetric synthetic cases had
score-matrix total variation from `0.0006714937737811507` to
`0.00609079663639125`, with exact serial/parallel replay.

## V4 correction

Proposed V4 uses one compact 36-category score-matrix total-variation gate.
The Bretagnolle-Huber-Carol bound plus a union bound across all 1,424 forecasts
gives:

```text
TV_limit = 0.012794580429261083
global familywise alpha = 0.01
```

All 62 event errors remain diagnostics. An evaluation-wide Hoeffding warning
threshold of `0.008613326107968184` provides localization without creating 62
new hard gates.

V4 offline qualification passed the exact V3 failing input and six synthetic
regimes. Exact-input V4 total variation was `0.005155986291064673`; all cases
returned `PASS`, no warnings, identical one-worker/four-worker bytes, and no
tail draws.

V4 identities:

- Evaluation policy: `0c266e924f2439d1674d081f7a544cf0b91f156d925c162d77ab40092b88aef9`
- Rust policy: `b4127ae64bd0755ea0d7472da8e984e8c31c4226c93c8a516f10b93ff6df90bf`
- Rust release build: `8790a84673099475a2bd5b46c8c6785d5698c5b19d666bd90e06349d444e4d88`
- Execution configuration: `b5392dc83b87a715b48a5cd415718fcaf8852feab8b467ab40f0d135ef3ee7ec`
- Preregistration: `87c00aecf99c348319014831746a7ba0a0abadc304a92ee18f5dab93d9fac318`
- Qualification evidence: `519fe944fc0f3fd7f2e51693dcb6c1e68429bebc8cc134e67d7fb5539b0247f0`
- Implementation source: `719a04300bf2c6438f2a4cafb4fe52ad0f03f9ea`

## Exact V3 to V4 differences

1. Protocol, Rust algorithm, seed schedule, policy, build, configuration, and
   preregistration identities advance to V4.
2. One evaluation-wide score-matrix total-variation hard gate replaces 62
   per-forecast cellwise hard gates.
3. Multiplicity covers all 1,424 forecast validations.
4. The 62 event errors become descriptive warnings.
5. Rust independently recomputes analytic indicators from score atoms.

Snapshot, corpus, firewall, aliases, models, rolling features, metrics,
bootstrap, aggregation, and target membership remain unchanged.

## Readiness and owner boundary

V4 is `PREPARED_AWAITING_OWNER_FREEZE_AND_EXECUTION_AUTHORIZATION`. It has not
been executed.

Before any V4 evaluation, a new append-only owner decision must set
`evaluation_execution_authorized=true`, authorize exactly one logical V4
execution, and bind the exact evaluation policy, preregistration, execution
configuration, reference/challenger artifacts, snapshot/corpus/firewall/alias
identities, Rust policy/build, implementation source, 712 targets, and 1,424
forecast validations listed above.
