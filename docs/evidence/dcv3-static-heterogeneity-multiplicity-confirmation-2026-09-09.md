# DCv3 static team heterogeneity multiplicity confirmation — 2026-09-09

## Map

~~~
Static Team Heterogeneity Multiplicity Confirmation
~~~

This follow-up consumes the retained frozen La Liga forecast/residual artifact. It does not refit DCv3, fit a challenger, tune a parameter, access EPL targets, or reuse the shared-pace admission population.

## Bound input and reproducibility

~~~
Dataset: StatsBomb La Liga 2015/16
Dataset version: 670662d6-6ed7-5fa1-ba3c-1cfd561e524f
Source snapshot: 01a08471-f763-7787-80ca-4293316b7e44
Diagnostic targets: 280
Target SHA-256: b758e795d41f0cc84145626d20d791eccbcfbd9fb94d2767039bdcdf50f3eb18
Input diagnostic SHA-256: 120ca2e0e135942d7d0b0316d8035562e9d57426225fe3d49dedf4ada445ee5e
Warm-up: first 100 chronological matches
Frozen DCv3: unchanged
~~~

The method was frozen in [dcv3-static-heterogeneity-multiplicity-protocol-2026-09-09.md](dcv3-static-heterogeneity-multiplicity-protocol-2026-09-09.md) before output generation.

It used a circular chronological moving-block bootstrap over retained kickoff batches:

~~~
Sampling unit: retained records grouped by identical UTC kickoff string
Kickoff batches: 243
Block length: 10 kickoff batches
Replicates: 2,000
Seed: 20260909
Eligible team threshold: 12 appearances
Primary family: all 20 attack plus all 20 defence series
~~~

Each selected block retains every match record in each kickoff batch. This keeps same-match home/away coupling, team appearance coupling, chronological blocks, and the shared frozen forecast/refit sequence. It does not resample team series independently.

Eligible-team identity SHA-256:

~~~
53d9ad4c01d1b19a8661a60c17ba3fe2124326e26af7f8427547998aa1d13a28
~~~

The script SHA-256 is a1aeb589b13a1238caa8bbb08c60cd2eeee2b09ad1274ff246992983922aac39. The retained input records the original diagnostic script SHA-256 f1dc8d1223e90ef7cea83f06e50e1d3476303cf5485fbd051ced00261352fc63, dependency-lock SHA-256 d14def6539f213b2af3011975062ed3e1e0bba2d86e8064803bd3d86d0a39e4e, and input code SHA 72361cabedfaff850ee8ff73c32e97eadb8c7499.

## Results

The 40-series primary analysis used the maximum standardized bootstrap error. Its 95% critical value was 3.2926580862065236.

| Result | Value |
| --- | ---: |
| Eligible attack series | 20 |
| Eligible defence series | 20 |
| Global statistic | 66.76518075871745 |
| Global bootstrap reference interval | [19.543531808885394, 70.18152436933794] |
| Global upper-tail reference probability | 0.039 |
| Primary 40-series simultaneous exclusions | 1 |
| Attack-family secondary simultaneous exclusions | 1 |
| Defence-family secondary simultaneous exclusions | 0 |

The global statistic is above most of its bootstrap reference distribution, but it remains inside the frozen two-sided reference interval. The primary family has only one simultaneous exclusion. Under the predeclared confirmation rule, the global result plus one surviving series is not enough to establish a population-level mechanism; the result is not treated as a team-specific parameter authorization.

The only primary-family survivor is reported descriptively:

| Team ID | Dimension | Mean residual | Primary simultaneous 95% interval | Appearances |
| --- | --- | ---: | --- | ---: |
| 01a08230-a2dc-7d58-8b99-c8a3b6eb73a8 | ATTACK | 0.998030957850915 | [0.035701810726047944, 1.960360104975782] | 28 |

This one series is not a license to add a team correction. The conclusion is about the population-level mechanism, not a named team.

## Classification

~~~
B. STATIC_HETEROGENEITY_NOT_CONFIRMED_AFTER_MULTIPLICITY
NO_STATIC_HETEROGENEITY_CHALLENGER
~~~

The original seven marginal intervals were an interesting independent diagnostic signal. After simultaneous 40-series inference and the predeclared global decision rule, the evidence is not robust enough to justify further static-heterogeneity challenger research.

The machine-readable result is [dcv3-static-heterogeneity-multiplicity-confirmation-2026-09-09.json](dcv3-static-heterogeneity-multiplicity-confirmation-2026-09-09.json).

~~~
Joint result SHA-256: 600e14bcbc55204e697d7e3e9724ac4c6e9bf84121a79ea7e9592cc989e8f32c
Output SHA-256: 0e2bc6b197ca2149b4b821dc568377f5b8517c3e90ecf1a9b863003bc771cd66
Repeated output SHA-256: 0e2bc6b197ca2149b4b821dc568377f5b8517c3e90ecf1a9b863003bc771cd66
~~~

## Owner handoff

~~~
Recommended next action:
NO_CHALLENGER_YET

Frozen DCv3: UNCHANGED
La Liga forecasts: NOT REFIT / NOT RETUNED
Candidate models: NOT FIT
Frozen EPL 280 outcomes: NOT ACCESSED
Protected admission population: NOT REUSED
Authoritative evaluation: NOT RUN / NOT AUTHORIZED
Sprint 2: FAIL
Model promoted: false
Phase 3: BLOCKED / UNAUTHORIZED
Production changes: NONE
~~~

Wayfinder map: COMPLETE
