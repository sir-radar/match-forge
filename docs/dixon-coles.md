# Dixon–Coles goal baseline

The Sprint 2 goal baseline fits a time-weighted Dixon–Coles model to completed canonical matches.
It estimates one log attack effect and one log defensive vulnerability per team, a global log home
advantage, and the Dixon–Coles low-score correlation parameter.

## Fit contract

Training matches require a unique canonical match UUID, timezone-aware kickoff, distinct canonical
teams, and non-negative integer goals. The fitter sorts inputs by kickoff and match UUID. The latest
kickoff is the training cutoff; older log-likelihood contributions receive exponential half-life
weights. Time weighting may be disabled.

For home team `h` and away team `a`:

```text
lambda_home = exp(attack_h + defence_vulnerability_a + home_advantage)
lambda_away = exp(attack_a + defence_vulnerability_h)
```

Attack effects sum to zero, removing the model's translation ambiguity. L-BFGS-B fitting uses
explicit finite bounds and fails closed when it does not converge. Model configuration and ordered
training facts each receive canonical SHA-256 identities.

## Low-score correction

Independent Poisson score probability is multiplied by `tau` only for these scores:

```text
tau(0, 0) = 1 - lambda_home * lambda_away * rho
tau(0, 1) = 1 + lambda_home * rho
tau(1, 0) = 1 + lambda_away * rho
tau(1, 1) = 1 - rho
```

All other scores use `tau = 1`. Configuration or fitted parameters that create a non-positive
low-score probability are rejected.

## Forecast contract

A forecast returns `lambda_home`, `lambda_away`, arbitrary exact-score probabilities, and a 6×6
matrix labelled `0`, `1`, `2`, `3`, `4`, `5+`. Tail buckets preserve all probability mass rather
than truncating the distribution.

The same corrected joint distribution produces:

- home win, draw, and away win;
- over 1.5, 2.5, and 3.5 goals;
- both teams to score;
- home and away clean-sheet probabilities.

The model does not calibrate or promote itself. Walk-forward evaluation and calibration remain
required before it can be treated as a production forecaster.
