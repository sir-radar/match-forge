# Mandatory Validation

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Authorization status:** future required product gate, *not* permission to implement/enable Rust today. This is the detailed proposed procedure from the supplied plan; pass thresholds, reference fixtures, resource budgets and engine eligibility must be frozen by explicit approval **before** implementation acceptance/production use.

The canonical machine-readable record is [SimulationValidationArtifactV1](../contracts/simulation-validation-v1.md); [publication state machine](publication-state-machine.md) owns transition semantics.

---

## 11. Mandatory Rust simulation and validation policy

**Product decision:** Rust Monte Carlo is the **default mandatory gate for all newly published production fixture forecasts** and an independent gate for promoting every simulation-capable candidate, **after** separate implementation authorization and engine acceptance. It is not a retroactive requirement for completed baselines, immutable historic evidence, or the already authorized minimal Phase 3A xG research. It is not permission to expand the currently deferred Rust scaffold. Detailed executable criteria live in `docs/simulation/mandatory-validation.md`; the immutable sidecar schema lives in `docs/contracts/simulation-validation-v1.md`.

### 11.1 What simulation proves — and what it cannot

- **Numerical/structural validation:** Rust's seeded samples approximate the same finalized probability distribution as the analytic model within a pre-registered Monte Carlo tolerance. Check 1X2, score, total goals, approved over/under lines, BTTS, clean sheets, corners if independently qualified, moments, dependence, and explicit tail mass.
- **Predictive calibration:** use forecasts issued without future outcomes and compare them with *real* later results across many distinct matches. Report proper scores, reliability, uncertainty, segments, and chronological stability. Simulation frequencies alone cannot improve or establish real-world calibration.
- **Posterior/predictive checking:** on a separately authorized development or untouched evaluation protocol, compare simulated aggregate statistics with observed match statistics to identify potential misfit. Any proposed fix starts a new registered training-only hypothesis; never tune on frozen evaluation observations or automatically alter the published forecast.
- Simulation is a validation and scenario product. If simulation-derived probabilities are ever proposed as the forecast's authoritative output, define a new model contract and separately prove scoring, coherence, calibration, and promotion; never silently replace analytic probabilities with Monte Carlo frequencies.

### 11.2 Mandatory production and promotion gates

1. Python generates eligible point-in-time inputs and approved model parameters; calibration parameters are fitted only on earlier out-of-sample real forecasts and final distributions are coherent before sampling.
2. Seal the forecast candidate and its canonical probability hash. Rust receives only approved versioned parameters/distributions and an independent seed schedule: no tags, post-match information, raw training labels, or model fitting.
3. The Rust engine produces reproducible runs and a `SimulationValidationArtifactV1` linked to the candidate hash and engine build. Required results include run count, seed policy, convergence, event coverage, parity and tail checks, numerical precision, and failure reasons.
4. A **new production fixture forecast** may be published as simulation-validated only if all mandatory numerical checks pass; after activation this is the default required production route, not an optional decoration. Publish the identical sealed forecast and its validation evidence, using an atomic/recoverable publication boundary; never mutate probabilities to make parity pass.
5. If simulation fails, times out, or is unavailable, retain the sealed candidate for debugging and return an explicit `SIMULATION_UNAVAILABLE`/unavailable state for the simulation-required product. Existing published forecasts remain retrievable. An analytic-only response is allowed only under a separately approved policy, prominently marked `ANALYTIC_ONLY`, and never advertised as validated simulation output.
6. Every simulation-capable model proposed for promotion requires a passing reference-fixture suite and representative batch parity/convergence/cost evidence. Promotion still additionally requires real-outcome evaluation and an explicit owner decision. A passing simulation test is never a predictive promotion decision.
7. Optional post-forecast enrichment remains independent: tag generation may fail without invalidating a successfully published forecast or its simulation evidence. Tags cannot enter the simulator.

### 11.3 Initial scope and counts

Implement a **minimal** Rust sampler against the existing approved score distribution first. Defer time-varying hazards, red cards, substitutions, event-by-event corners, multi-scenario lineups, and H2H counterfactuals until their separate contracts and data sources pass qualification.

| Use | Initial engineering count (not an accuracy guarantee) |
| --- | ---: |
| Development / smoke checks | 1,000 |
| Routine production candidate | 10,000 |
| Detailed inspection / difficult convergence | 100,000 |
| Long-run capacity benchmark | Up to 1,000,000, only if justified |

Counts are configurable **starting points**, not fixed pass conditions. Run additional independent seeded batches until event-specific pre-registered confidence half-widths and parity thresholds pass or a compute/time budget is reached; otherwise mark `INCONCLUSIVE`, not `PASS`. Rare outcomes may require much larger samples or an approved analytic calculation. Record effective draws, independence/variance assumptions, numerical tolerances, seeds, hardware/build, elapsed time, and cost. Prefer analytic exact probabilities when available; never degrade them merely to add Monte Carlo noise.

### 11.4 Supported future scenario scope (authorization required)

After minimal engine acceptance, separately qualify any of: goal timing and current score; lineup scenarios; posterior parameter uncertainty; match-state-dependent goal rates; dependence between team scores; qualified red-card or substitution hazards; and independently validated corners processes. If sampling uncertain parameters, include the scenario weights and uncertainty source; do not mistake multiple seeds for new uncertainty about team strength.

### 11.5 Validation requirements

- deterministic seed schedule, repeatability across identical build/platform where promised, and well-defined cross-platform tolerance otherwise;
- parity against analytic distributions wherever analytic references exist;
- convergence across independently seeded batches with confidence intervals and explicit failure/inconclusive handling;
- normalized 1X2/exact score/market relationships, monotone lines, finite values, realistic support, and preserved score-tail mass;
- distribution-level and segment-level comparison with real outcomes under the separately frozen evaluation contract;
- bounded latency, throughput, memory, costs, cancellation, idempotent retries, and reproducible immutable artifacts;
- no feature training, calibration, promotion, or probability changes in Rust or triggered automatically by a simulation discrepancy.

The engine is the mandatory default validation dependency for **all new production fixture publication** after separate approval, except a separately approved and explicitly labelled analytic-only fallback; it is not a reason to reopen Sprint 2, access its frozen 280 targets, or stop authorized analytic-only research.

### H2H counterfactual simulation suite

When H2H parameter candidates reach simulation research, run matched variants for the same fixture snapshot using common random numbers and the same seed schedule:

```text
S0: approved base parameters, no H2H adjustment
S1: H2H-informed mean adjustment only
S2: H2H-informed dispersion adjustment only
S3: H2H-informed mean plus dispersion
S4: H2H-informed score correlation, only if separately qualified
```

Compare full distributions, not one historical result or one simulation run. Record changes in 1X2, expected goals, total goals, BTTS, exact-score distribution, and tails. Estimate every adjustment on training data, freeze it before the evaluation window, and evaluate each variant on untouched matches. A same-seed counterfactual isolates the effect of the H2H parameter change; it does not by itself prove predictive value.
