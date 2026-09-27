# PitchAPI V5 calibration successor development result

## Disposition

`PITCHAPI_V5_CALIBRATION_SUCCESSOR_RESEARCH_V1` is complete.

Final development disposition: `DEVELOPMENT_REJECTED`.

The frozen global shrinkage vector-scaling candidate slightly improved held-out
1X2 proper scores, but it failed four preregistered admission checks. The raw
challenger's joint-score log-loss gain was `-0.0059837103`, short of the required
`-0.01`, and its 95% paired moving-block interval
`[-0.0274947840, 0.0069248957]` crossed zero. Calibrated draw intercept and slope
error also exceeded the frozen margins relative to the reference. No other
calibration family was tried.

## Frozen mathematics

Input is the unchanged challenger's strictly positive normalized 1X2 vector
`p = [p_home, p_draw, p_away]`. The calibrated vector is:

```text
q = softmax([
  a_home + b_home log(p_home),
  a_draw + b_draw log(p_draw),
  b_away log(p_away)
])
```

`a_away` is fixed to zero for identification. The fitted parameters minimize:

```text
sum_i -log(q_i[y_i])
+ (10 / 2) * (
    a_home^2 + a_draw^2
    + (b_home - 1)^2 + (b_draw - 1)^2 + (b_away - 1)^2
  )
```

L-BFGS-B uses initialization `[0, 0, 1, 1, 1]`, intercept bounds `[-3, 3]`,
scale bounds `[0.25, 4]`, function tolerance `1e-12`, gradient tolerance `1e-8`,
and at most `2000` iterations. Inputs outside `(0,1)`, non-finite values, and
normalization error above `1e-12` fail closed. No clipping occurs. Output uses a
max-subtracted softmax and must satisfy the same probability checks.

Shrinkage strength `10` was frozen before fitting. It represents ten units of
quadratic pull toward the identity transformation `[0, 0, 1, 1, 1]`. This was
used because one 216-target competition-season cannot support flexible
calibration. Strengths `5` and `20` were frozen diagnostic sensitivities, not
admission candidates.

## Chronological development design and coverage

The only source was Bundesliga 2021/22 development manifest
`be4251a4f53307bae0895c856b5a9ffdf21cdd64da9f0610c8273924d4bef62e`.
All 216 targets appear in the immutable coverage file:

- targets 1-72: forecasting-state fit only;
- targets 73-108: 36 genuine OOS predictions used only to seed calibration;
- targets 109-216: 108 held-out calibration-validation predictions in three
  expanding chronological folds of 36;
- all block boundaries preserve same-kickoff batches;
- every forecast uses ten prior appearances and observations strictly before
  its block kickoff;
- calibration folds fit on 36, 72, and 108 earlier OOS predictions;
- no target calibrates itself.

Exact target assignments are in
`pitchapi-v5-calibration-successor-research-2026-09-27/development-coverage.json`.

## V5 firewall

The experiment loaded no V5 evaluation manifest, no V5 target row, and no V5
outcome. V5 fitting/model-selection use is `false`; loaded V5 target and outcome
counts are both zero. The 712 V5 targets remain `SPENT_FOR_MODEL_SELECTION`.
V5 remains `COMPLETE / REFERENCE_RETAINED`; its challenger remains
`EVALUATED_REJECTED_CALIBRATION`.

## Held-out metrics

All values cover the same 108 held-out development targets.

| Metric | Reference | Raw challenger | Calibrated challenger | Calibrated minus raw | Calibrated minus reference 95% interval |
| --- | ---: | ---: | ---: | ---: | ---: |
| Joint-score log loss | 3.1993636976 | 3.1933799873 | 3.1933799873 | 0.0000000000 | [-0.0274947840, 0.0069248957] |
| 1X2 log loss | 1.0228548143 | 1.0177608283 | 1.0173892559 | -0.0003715724 | [-0.0231447153, 0.0059388237] |
| Brier | 0.6139956760 | 0.6100631051 | 0.6095632556 | -0.0004998495 | [-0.0181449188, 0.0037902897] |
| RPS | 0.2208810383 | 0.2188901046 | 0.2184242819 | -0.0004658226 | [-0.0091464857, 0.0011918296] |
| Total-goal CRPS | 1.0418676878 | 1.0396200218 | 1.0396200218 | 0.0000000000 | [-0.0152217616, 0.0089425714] |

Vector scaling changes only 1X2 probabilities. Joint-score log loss and
total-goal CRPS therefore remain exactly unchanged from the raw challenger.

## Calibration before and after

| Outcome | Raw intercept | Calibrated intercept | Raw slope | Calibrated slope |
| --- | ---: | ---: | ---: | ---: |
| Home | -0.0175777037 | 0.0347829579 | 1.4717263095 | 1.2889516292 |
| Draw | 0.1782503183 | -0.4499558504 | 1.2045328412 | 0.6322758128 |
| Away | 0.3288384275 | 0.0694818694 | 1.2198339144 | 1.0654387405 |

Pooled classwise ten-bin ECE changed from `0.0336137866` raw to
`0.0397163683` calibrated. Home and away calibration moved toward the targets;
draw calibration became less stable and worse. Draw uncertainty was large:
calibrated intercept SE `2.0135384577`, slope SE `1.5813186802`.

## Shrinkage, uncertainty, and stability

Unshrunk fold fits were unstable: draw scale reached the upper bound `4.0` in
two folds and was `3.8505902122` in the third; home intercept ranged from
`-1.9192221450` to `-1.1686080900`; away scale ranged from `2.4342154982` to
`2.4976293795`.

With frozen strength `10`, fold parameters stayed near identity:

- home intercept: `-0.0644578608` to `-0.0298136743`;
- draw intercept: `-0.0595980974` to `-0.0040181096`;
- home scale: `1.0518087582` to `1.1766024128`;
- draw scale: `1.0479104049` to `1.1292243843`;
- away scale: `0.9983926536` to `1.0625129341`.

The final 144-OOS-row fit is
`[-0.0426669434, -0.0262409644, 1.1501969510, 1.0829260073, 1.0199349352]`
for `[a_home, a_draw, b_home, b_draw, b_away]`. Observed penalized-Hessian
standard errors are `[0.2540201231, 0.2742919707, 0.2534388047,
0.2181492594, 0.2082091863]`.

Sensitivity remained small and did not change the scientific conclusion:

| Strength | 1X2 log loss | Brier | RPS |
| ---: | ---: | ---: | ---: |
| 5 | 1.0176254698 | 0.6097912671 | 0.2184753925 |
| 10 | 1.0173892559 | 0.6095632556 | 0.2184242819 |
| 20 | 1.0172847060 | 0.6095095193 | 0.2184503761 |

Joint-score log loss and total-goal CRPS are invariant to all three strengths.
Strengths 5 and 20 were not used for admission.

## Artifact and reproduction

The fitted calibration artifact SHA-256 is
`cd88bed5e1231dc740886573d7195cc32228b99b9135d2d6f2edab9408768452`.
It binds implementation commit `b31222c7fd17116f0be6bb4b01943d1624c2ab35`,
dependency lock `d14def6539f213b2af3011975062ed3e1e0bba2d86e8064803bd3d86d0a39e4e`,
the development manifest, preregistration, and OOS prediction manifest.

Two complete runs from the same clean inputs produced byte-identical outputs:

- artifact: `cd88bed5e1231dc740886573d7195cc32228b99b9135d2d6f2edab9408768452`;
- development coverage: `a3267608944dc3f041c93dc7d34c6a03f14e51bb20dc7ec48baf128c082dba16`;
- development evidence: `f98e40aabacce8835c85f6bf81196b1c597d52c33582de82969d8dd33b8d05f6`;
- OOS prediction manifest: `a5a4e805d1657cf3645daa56827f00de00d31457aca8bbec47fee1b6fb266f24`.

Both JSON schemas validate. The artifact is retained as immutable negative
research evidence; it is not promoted or admitted for confirmation.

## Limitations and owner boundary

Only one competition-season was available. The result cannot establish
cross-domain calibration, domain-specific effects, hierarchical pooling, or
transfer to unseen competitions. The 108 validation targets provide weak
class-specific calibration precision, especially for draws. Sensitivity to
temporal regime and team composition remains unresolved.

No confirmation-corpus proposal is produced because the candidate was not
admitted. No further authorization is implied. Any additional calibration
family, added development domain, provider acquisition, confirmation design or
execution, V6, promotion, or production use requires a new explicit owner
decision. This route stops here.
