# Corner count baselines

Sprint 2 compares Poisson and NB2 Negative Binomial regressions on the same corner observations and
pre-match feature design. This is separate from the goal model because corner counts have different
dispersion and predictors.

## Leakage-safe input

Each completed match supplies canonical match, competition, and team UUIDs; a timezone-aware
kickoff; observed home and away corner counts; and features computed strictly before that kickoff:

- possession tendency;
- shot rate;
- cross rate;
- recent corners.

Realized possession, shots, crosses, or later matches must never populate these fields. Inputs are
sorted by kickoff and match UUID, and older likelihood contributions receive configurable half-life
weights.

## Shared regression design

Home and away corner counts become two observations. Their log expected counts include:

```text
intercept
+ attacking team's corner strength
+ opponent's corner-concession effect
+ competition effect
+ home advantage, for the home observation only
+ standardized possession, shot, cross, and recent-corner features
```

Team attack and opponent-concession effects each sum to zero. One competition is the reference.
Training feature means and scales are retained with the fitted parameters so forecasts apply the
same transformation.

## Distribution comparison

The Poisson baseline assumes `variance = mean`. NB2 adds fitted dispersion `alpha`:

```text
variance = mean + alpha * mean^2
```

Both models use the same weighted observations, feature design, bounds, and optimizer. The result
records observed mean and variance, flags empirical overdispersion, and selects the lower-AIC model.
This is model evidence, not a deployment decision; walk-forward out-of-sample scoring remains the
next required gate.

Forecasts expose home and away expected corners, variances, and exact count probabilities for the
selected distribution. Configuration and ordered training facts have canonical SHA-256 identities.
