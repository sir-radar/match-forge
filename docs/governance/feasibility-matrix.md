# Feasibility Matrix

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

Source-supplied feasibility classifications are **proposals**, not a verified capability registry. `Yes` means research feasibility, NEVER production activation. Use the actual [capability registry](../operations/capability-registry.md) for the enablement decision.

---

## 19. Feasibility matrix

| Feature | Feasible now? | Data dependency | Promotion condition |
| --- | --- | --- | --- |
| Minimal Rust sampler / mandatory simulation validation | Proposed; implementation not yet authorized by 20 September decision | Qualified parameters, coherent calibrated distribution, existing Rust scaffold, explicit new owner authorization | Reference parity, convergence, numerical integrity, independent-seed reproducibility, failure handling, cost and published validation artifact PASS |
| New production fixture forecast (simulation default) | Blocked until simulator and independent product enablement are approved | Approved model plus accepted Rust engine and artifact contract | A linked PASS for each new forecast by default; exceptional analytic-only fallback must be explicitly approved and labelled; real-outcome model evidence and promotion/enablement decision; no retroactive requirement on prior artifacts |
| Analytic-only reference research | Existing authorized subset remains allowed | Existing qualified data/model contracts | No Rust dependency for historical work or bounded 20 September Phase 3A xG research |
| Curated derby registry | Yes | Team identity plus reviewed rivalry sources | Registry QA; display metadata only |
| Derby display flag | Yes | Registry | API and forecast-parity tests pass |
| Unpredictability display tags | Yes after diagnostic validation | Issued forecast, model disagreement, residual history, OOD and data-quality evidence | Honest reason codes, sufficient evidence and forecast-parity tests |
| Derby model coefficient | No under this plan | Not applicable | Requires an explicit future policy change; never inferred from the display tag |
| xG and xGA rolling form | Yes after Tier A qualification | Shot events or compatible provider xG | Beats goals-only/xG-only ablations |
| Opponent-adjusted xG/xGA | Yes | Multi-team historical coverage | Generalizes across folds |
| Game-state-adjusted xG/xGA | Research now after event qualification | Event timeline, score state, and dismissal semantics | Beats or complements raw values without leakage |
| Residualized H2H | Yes, research only | Historical out-of-sample predictions | Adds signal after shrinkage |
| H2H counterfactual simulation | After H2H and simulator foundations | Qualified pair context and parameter generator | Held-out mean/dispersion variant improves full-distribution scores |
| Raw H2H win rate | Technically possible, not recommended | Results | Do not promote as designed |
| Entropy and model disagreement | Yes | Approved predictive models | Risk bands validate out of sample |
| OOD detection | Yes | Frozen training feature distribution | Correlates with measurable forecast degradation |
| Post-match shock labels | Yes where events exist | Qualified event data | Explanation/research only initially |
| Manager-change context | Feasible after qualification | Accurate historical dates | Ablation passes |
| Rest/congestion | Yes | Reliable kickoff times | Ablation passes |
| Travel/load context | Feasible | Venue coordinates, neutral flags, player minutes, duty and fixture history | Component and combined ablations pass |
| Predicted lineups | Later | Deep historical lineup/availability coverage | Separate lineup forecast gates pass |
| Lineup strength impact and continuity | Later | Player effects, lineup scenarios, historical units/minutes together | Adds value beyond lineup names and preserves uncertainty |
| Squad-transition context | Feasible after lineup/identity qualification | Retained minutes, departures, arrivals, roles and availability | Adds value beyond team rating and lineup strength |
| Team plus player ratings | Research after lineup qualification | Historical player minutes and leakage-safe player ratings | Combined candidate beats team-only and player-only references |
| Goalkeeper post-shot residual | Later | Qualified post-shot xG/xGOT and goalkeeper identity | Adds value beyond xGA with stable shrinkage |
| Pre-shot threat and territory | Research after Tier A qualification | Versioned event sequences | Adds value beyond xG/xGA without unstable provider semantics |
| Forecast horizons and revisions | Yes once snapshots exist | Reconstructable point-in-time inputs | Horizon-specific calibration and revision value validate |
| Objective competition-priority proxies | Research only | Table/knockout state, future schedule as known at cutoff, rotation history | Adds value without subjective motivation labels |
| Kickoff/circadian effects | Deferred research | Local time, travel and timezone history | Stable effect after controlling for schedule and travel |
| Weather/referee features | Deferred | Point-in-time historical coverage | Only after qualification and ablation |
| xT/VAEP | Later | Normalized event actions | xG foundation stable and separately authorized |
| Tracking/GNN features | Not near-term | Licensed tracking data and large corpus | Independent future research route |
| Live automatic recalibration | No | Would require mature online-learning governance | Explicit future research only |
