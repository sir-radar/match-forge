# Phase 1C StatsBomb La Liga Tier-A xG qualification — 2026-09-21

## Result

```text
XG_SEMANTIC_COVERAGE:                    PASS
PHASE1C_TIER_A_XG_SOURCE_QUALIFICATION:  PASS_WITH_WARNINGS
PHASE3A_MODEL_RUN_READY:                 NO
EVALUATION_V2_CORPUS_ELIGIBILITY:        NOT_DETERMINED
```

This qualification is authorized by owner decision
`RETAIN_SPRINT2_FAIL_CLOSE_SHARED_PACE_AND_AUTHORIZE_PHASE3_RESEARCH_V1`,
item 9. It measures provider/resource coverage and source semantics only. It
does not fit a model, generate a forecast, reveal or score an evaluation
outcome, authorize Evaluation V2, or promote a capability.

## Exact source

```text
Provider:                    StatsBomb Open Data
Provider competition/season: 11 / 27
Competition/season:          La Liga 2015/2016
Canonical competition ID:    01a051db-552e-782d-b2ac-b3f0ec58441b
Canonical season ID:         01a051db-553a-754a-9560-d79eceeb72b6
Dataset version:             670662d6-6ed7-5fa1-ba3c-1cfd561e524f
Source snapshot:             01a08471-f763-7787-80ca-4293316b7e44
Source Git SHA:              4b73468fc5b0f1950f9f66fada70ad3a4f9327cb
Dataset manifest SHA-256:    cd32d1c44620116cedefc09860efeccb91da19db4e6006ace8b8b6df1dd8e4e0
```

The qualifier required the exact manifest path and SHA-256, dataset ID, source
Git revision, canonical competition and season, and normalized path scope
before opening any Parquet file. It then verified all 380 file checksums and
manifest row counts. The source-snapshot relationship is a retained lineage
prerequisite from the linked dataset requalification; this coverage scan did
not re-query that registration.

## xG and shot coverage

| Check | Result |
| --- | ---: |
| Normalized event files / matches | 380 / 380 |
| Normalized events | 1,295,354 |
| Shot events | 9,168 |
| Matches with at least one shot | 380 / 380 |
| Shots with `shot.statsbomb_xg` | 9,168 / 9,168 |
| Finite xG values in `[0, 1]` | 9,168 / 9,168 |
| Missing canonical shot type | 0 |
| Missing canonical team | 0 |
| Missing canonical player | 0 |
| Missing source location | 0 |
| Out-of-bounds shot location | 0 |
| Malformed shot payload | 0 |
| Shot periods | period 1: 4,116; period 2: 5,052 |
| Provider shot types | open play: 8,661; free kick: 409; penalty: 97; corner: 1 |

Observed provider xG ranges from `0.00018` to `0.9800704`; total retained xG
is `979.7748007951`. These totals describe source coverage. They are not a
feature definition, fitted parameter, forecast, or evaluation result.

## Point-in-time and protected-target checks

The retained [PIT scope correction](statsbomb-pit-kickoff-policy-scope-correction-2026-09-09.md)
records `POINT_IN_TIME_SUITABILITY: PASS` for all 380 matches. The retained
[dataset requalification](statsbomb-laliga-diagnostic-dataset-requalification-2026-09-09.md)
binds the same dataset/source pair and records zero intersection with both the
100-match Sprint 2 admission population and the frozen 280 targets. This run
did not open the protected EPL dataset or either protected target population.

## Warnings and limits

- StatsBomb Open Data supplies a commit-pinned retrospective snapshot, not
  historical provider-publication timestamps. Evaluation V2 must freeze an
  explicit compatible knowledge mode before this source can enter its corpus.
- The retained validator warnings remain unchanged. This qualification checks
  xG-bearing shot rows and does not clear unrelated event warnings.
- The scan includes every provider shot type, including 97 penalties. The
  Phase 3A feature must separately freeze penalty treatment, aggregation,
  window/decay, missingness, and model integration before implementation.
- One qualified competition-season does not satisfy the proposed Evaluation
  V2 multi-season, multi-competition corpus requirement.

## Reproduction

Machine-readable coverage and qualification result:
[Phase1CStatsBombXGCoverageV1](phase1c-statsbomb-laliga-xg-coverage-2026-09-21.json).

```text
Qualifier commit:       de68e960d412d2b95f19da219c277d692d3de91d
Qualifier SHA-256:      8b5d475a1ccb7c35ab7db57b24cb3e2446c8a2a52aa851d0966d3a76ff3d85f0
Evidence JSON SHA-256:  0779cbadd2ad3d68d2e280f64148e034961487afd174b50ede1fde50d9eef003
uv.lock SHA-256:        d14def6539f213b2af3011975062ed3e1e0bba2d86e8064803bd3d86d0a39e4e
PyArrow:                25.0.1
Python:                 3.13.14
```

The outcome is `PASS_WITH_WARNINGS` for this exact Tier-A xG source only.
Phase 1C remains in progress, and Phase 3A remains blocked on a frozen
experiment specification and eligible research corpus.
