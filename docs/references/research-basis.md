# Research Basis

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

Citations here are carried over from the user-supplied plan **without external re-verification**; they are rationale, not repository evidence or authorization.

---

## 23. Research and engineering basis

These sources inform the roadmap but do not override repository governance or provider terms:

- Hudl/StatsBomb Open Data: <https://github.com/hudl/open-data>. The repository provides selected competitions, match events and lineups, with 360 data only for selected matches; rich coverage must therefore be measured, not assumed.
- Mead, O'Hare, and McMenemy (2023), “Expected goals in football: Improving model performance and demonstrating value”: <https://doi.org/10.1371/journal.pone.0282295>. Supports richer shot context, team-quality/context features, and direct validation of xG's predictive value.
- Ridall, Titman, and Pettitt, “Bayesian state-space models for the modelling and prediction of the results of English Premier League football”: <https://doi.org/10.1093/jrsssc/qlae075>. Supports dynamic attacking and defensive states rather than static team strength.
- Macrì-Demartino, Egidi, and Torelli (2026), “Bayesian weighted discrete-time dynamic models for association football prediction”: <https://doi.org/10.1093/jrsssc/qlag032>. Supports adaptive historical borrowing when team strength changes.
- Settembre et al. (2024), “Factors associated with match outcomes in elite European football — insights from machine learning models”: <https://doi.org/10.3233/JSA-240745>. In a large European-match analysis, travel distance, Elo difference, match location, and recent performance were prominent model contributors, while rest, rotation, and manager tenure also contributed. These are associations and feature-importance results, not causal proof; the paper's lineup-stability result was not a clear universal effect, so every context family still requires MatchForge-specific ablation.
- Arntzen and Hvattum (2021), “Predicting match outcomes in association football using team ratings and player ratings”: <https://doi.org/10.1177/1471082X20929881>. Their experiments found the combined team-rating and starting-lineup player-rating covariates outperformed using either rating family alone, supporting a bounded team-plus-player challenger rather than replacing team strength.
- Hudl StatsBomb, “A New Way to Measure Keepers' Shot Stopping: Post-Shot Expected Goals”: <https://www.hudl.com/blog/a-new-way-to-measure-keepers-shot-stopping-post-shot-expected-goals>. Provides the modelling rationale for separating pre-shot xG/xGA from post-shot goalkeeper evaluation. This is a provider methodology reference, so MatchForge still needs semantic qualification, shrinkage, and independent held-out evaluation.
- Pipping-Gamón, Feng, and Sabin (2025/2026), “Beyond Expected Goals: A Probabilistic Framework for Shot Occurrences in Soccer”: <https://arxiv.org/abs/2512.00203>. Motivates research into possession-level shot-generation information that ordinary shot-conditioned xG omits. It is a preprint, so this plan adds only simpler pre-shot threat ablations and does not treat its reported improvement as established production evidence.
- socceraction documentation: <https://socceraction.readthedocs.io/>. Demonstrates provider loaders, normalized action representations, xT, VAEP, and Atomic-VAEP as feasible later research paths.
- Gneiting and Raftery (2007), “Strictly Proper Scoring Rules, Prediction, and Estimation”: <https://doi.org/10.1198/016214506000001437>. Supports evaluating probabilistic forecasts with proper scoring rules.
- Scikit-learn probability calibration guidance: <https://scikit-learn.org/stable/modules/calibration.html>. Useful implementation reference for out-of-sample calibration and reliability analysis.
- Google, “Rules of Machine Learning”: <https://developers.google.com/machine-learning/guides/rules-of-ml>. Supports establishing a trustworthy end-to-end pipeline, testing infrastructure independently from the learner, monitoring silent failures and freshness, assigning feature ownership, and removing unused features before adding model complexity.
- NIST SP 800-218, Secure Software Development Framework: <https://csrc.nist.gov/pubs/sp/800/218/final>. Provides the secure-development basis for preparation, protected software, vulnerability response, and verifiable release practices.
- SLSA specification: <https://slsa.dev/spec/v1.2/>. Informs build provenance and software-supply-chain integrity requirements without requiring a particular CI vendor.
- OpenTelemetry documentation: <https://opentelemetry.io/docs/what-is-opentelemetry/>. Supports vendor-neutral correlation of logs, metrics, and traces across the forecast API and worker pipeline.
- The derby literature is limited and context-dependent. Use rivalry only for a reviewed frontend tag and evaluation slice; matched-control analysis must not feed a derby coefficient back into the forecast.
- Game-state-adjusted xG/xGA is retained as a research hypothesis rather than a claimed established improvement. MatchForge must compare raw, stratified, and adjusted variants under the same chronological contract.
