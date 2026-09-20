# Frozen DCv3 independent La Liga diagnostic — 2026-09-09

## Map

```text
Frozen DCv3 Independent Diagnostic Evaluation
```

This record completes the five authorized diagnostic tickets and stops at the
owner handoff. It does not authorize or implement a challenger.

## Ticket 01 — frozen protocol

The entry gate matched the qualified StatsBomb La Liga 2015/16 publication:

```text
Dataset version: 670662d6-6ed7-5fa1-ba3c-1cfd561e524f
Source snapshot: 01a08471-f763-7787-80ca-4293316b7e44
Dataset identity SHA-256: 5516752680f5863a0efbada19b3208fac3c64efb12fbeaa2c1894767c291d5e4
Competition ID: 01a051db-552e-782d-b2ac-b3f0ec58441b
Season ID: 01a051db-553a-754a-9560-d79eceeb72b6
Lifecycle / kickoff / corner labels: 380 / 380 / 380
```

`PRIOR_HISTORY_AVAILABLE: NO`. The local governed data contains no completed,
PIT-compatible La Liga season before 2015/16; no data was ingested.

The protocol was frozen before target goals were read:

```text
Warm-up: first 100 chronological La Liga matches
Target eligibility: prior competition history >= 100; each team history >= 10
Targets: 280 across 243 kickoff batches
Target SHA-256: b758e795d41f0cc84145626d20d791eccbcfbd9fb94d2767039bdcdf50f3eb18
Football-time range: 2015-11-06T20:30:00Z to 2016-05-15T17:30:00Z
Knowledge mode: retrospective-fixed-snapshot-v1
Knowledge cutoff: 2026-09-10T00:00:00Z
Refit frequency: one frozen DCv3 fit per kickoff batch
```

The unchanged model configuration is `sprint2-dixon-coles-v3`, 365-day time
decay, effect regularization 16.0, the existing SLSQP analytic-gradient
optimizer, and the existing score support.

## Ticket 02 — forecast freeze and controlled outcomes

All 280 target forecasts were frozen with the required target, training,
logical-model, joint-probability, and forecast-freeze checksums before the
script selected target home and away goals. Every recorded training cutoff is
strictly earlier than its target kickoff. Corners were not included in the
diagnostic output or model inputs.

The machine-readable result is
[dcv3-independent-laliga-diagnostic-corrected-2026-09-09.json](dcv3-independent-laliga-diagnostic-corrected-2026-09-09.json).
Its SHA-256 is:

```text
120ca2e0e135942d7d0b0316d8035562e9d57426225fe3d49dedf4ada445ee5e
```

The first generated JSON (`b811aa…7cdb`) omitted the actual fit cutoff from
each forecast record and is retained, not used for this handoff. The corrected
record above preserves the same target forecasts and residual results while
recording that required provenance field.

## Ticket 03 — predeclared diagnostics

The analysis used three equal-count forecast-mean buckets (93, 93, and 94
records), four chronological blocks (67, 67, 68, and 78), and a deterministic
moving-block bootstrap: 2,000 replicates, 10 kickoff batches per block, seed
`20260909`, and percentile 95% intervals. Team rows require at least 12
appearances; all 20 teams have 28 diagnostic appearances.

| Diagnostic | Finding |
| --- | --- |
| Conditional home variance | Only the highest-mean bucket had excess variance with a positive 95% interval: 1.30 goals², [0.29, 2.38]. |
| Conditional away variance | No bucket excluded Poisson variance. |
| Conditional total variance | No bucket excluded Poisson variance. |
| Conditional mean bias | Every bucket interval included zero; mean bias did not block variance interpretation. |
| Home-away residual correlation | -0.104, 95% interval [-0.218, 0.022]; no material positive shared-intensity signal. |
| Attack persistence | Lag-1 correlation 0.050, [-0.043, 0.134]; sign persistence 0.500, [0.474, 0.528]. |
| Defence persistence | Lag-1 correlation 0.081, [0.005, 0.146]; its lower interval is below the frozen 0.10 material threshold. |
| Static offsets | Four attack and three defence team mean-residual intervals excluded zero; the pooled persistence tests did not establish short-horizon movement. |
| Total-goal shape | DCv3 overpredicted zero-goal matches: 8.90% predicted vs 4.64% observed, difference -4.26 percentage points, [-6.23, -2.14]. Other total bins did not have intervals excluding zero. |
| Chronological signal | Only block 2 had a non-zero total residual interval (+0.51, [0.13, 1.00]); the remaining three included zero. |

La Liga alone cannot identify competition-level heterogeneity:

```text
COMPETITION_HETEROGENEITY_NOT_IDENTIFIABLE
```

## Ticket 04 — mechanism classification

```text
Conclusion: D. STATIC_HETEROGENEITY_SUPPORTED
Evidence strength: MODERATE
```

The frozen classification rule required at least two components with
conditional variance support for an overdispersion route, a lower correlation
interval of at least 0.10 for shared intensity, and a lower lag-1 interval of
at least 0.10 for dynamic strength. Those conditions were not met. The stable
team offsets meet the predeclared static-heterogeneity condition, but this is
one competition and its team intervals are descriptive, so the evidence is not
strong enough to select an implementation.

Mechanisms weakened: independent overdispersion, shared match-level intensity,
and persistent time-varying team strength. Remaining uncertainty includes the
isolated high-home-mean variance result, the zero-goal shape error, and the
single positive chronological block.

## Ticket 05 — owner handoff

```text
FROZEN_DCV3_INDEPENDENT_DIAGNOSTIC_COMPLETE

Recommended next action:
AUTHORIZE_CONTRACT_RESEARCH_FOR_STATIC_TEAM_HETEROGENEITY
```

No challenger was fitted or implemented. Frozen EPL 280 outcomes were not
accessed, the EPL admission population was not reused, shared-pace admission
was not rerun, no Sprint 2 evaluation ran, Sprint 2 remains `FAIL`, no model
was promoted, and Phase 3 remains blocked.

## Reproducibility

```text
Code Git SHA: 72361cabedfaff850ee8ff73c32e97eadb8c7499
uv.lock SHA-256: d14def6539f213b2af3011975062ed3e1e0bba2d86e8064803bd3d86d0a39e4e
Python: 3.13.14
SciPy: 1.18.1
Diagnostic script SHA-256: f1dc8d1223e90ef7cea83f06e50e1d3476303cf5485fbd051ced00261352fc63
Repeated output SHA-256: 120ca2e0e135942d7d0b0316d8035562e9d57426225fe3d49dedf4ada445ee5e
```

The repeated run produced the same target population, forecast records,
residual aggregates, and mechanism classification.
