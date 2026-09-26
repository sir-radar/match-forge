# PitchAPI V3 transferability evidence

All fitting and comparisons used Bundesliga 2021/22 development data only.
Evaluation outcome resources were not opened. Evaluation manifests were used
only to verify target counts, canonical team identities, kickoff order, and the
ten-prior-appearance condition.

## Compared approaches

| Approach | Development joint log loss | 1X2 Brier | Leakage and operational assessment |
| --- | ---: | ---: | --- |
| A. Frozen development prior | 3.1618035668 | 0.6222536785 | Simple and reproducible, but population shrinkage leaves promoted and cross-competition teams weakly individualized. |
| B. Fully transferable rolling features | 3.1423264645 | 0.6163093641 | Lowest development loss, no team-ID parameters, one causal algorithm for known and unseen teams, and bounded implementation complexity. |
| C. Online team state | 3.2886601493 | 0.6440332118 | Reproducible when ordered correctly, but most sensitive to update mistakes and short-run noise; worst development result. |

All three can cover the frozen corpus after ten prior appearances. Approach B
is selected because it performs best on development data, handles promoted,
renamed/remapped, and cross-competition teams without roster-specific fitting,
and has the smallest temporal state surface. The model consumes canonical IDs
only to retrieve strictly prior history; IDs are not predictive parameters.

## Leave-team-out check

Eighteen folds held each development team out of global fitting. The reference
scored 3.1634125839 joint log loss and 0.6227094643 1X2 Brier. The challenger
scored 3.1608153254 and 0.6200754315. Challenger-minus-reference deltas were
-0.0025972585 and -0.0026340328 respectively across 432 scored team-fixture
appearances.

## Frozen team-state rule

For both models, each team is represented by its last ten appearances strictly
before the target kickoff. Features are goals for, goals against, and raw
non-penalty xG for; the reference fixes the xG coefficient to zero. Same-kickoff
forecasts are all sealed before any outcome updates history. Population means
and all global coefficients are fitted only on Bundesliga 2021/22.

Structural verification found 216 + 216 + 280 = 712 targets, 40 evaluation
teams, and `unforecastable_evaluation_targets = 0`.
