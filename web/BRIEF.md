MatchForge — Comprehensive Product Requirements Document (PRD) & Product Brief
The formal Product Requirements Document (PRD) & Frontend Design Specification (v2.1.0) is maintained and published on your canvas as MatchForge — Product Requirements Document (PRD) & Frontend Design Specification (v2.1.0) (Document ID: MatchForge — Product Requirements Document (PRD) & Frontend Design Specification (v2.1.0)), fully synchronized with the design system ([Design_System]) and the complete 11-screen responsive UI suite.

Below is an executive summary and reference brief capturing the core product principles, technical architecture boundaries, capability governance, component models, and engineering handoff specifications.

1. Executive Summary & Vision
   Product Vision: MatchForge is a desktop-first, quantitative football fixtures and probabilistic simulation explorer. It pairs the high-density, date-driven, competition-grouped scanning experience of Soccerway with an inline, full-width analytical forecast dashboard that expands directly underneath selected fixtures without navigation loss or page reloads.
   Strict Non-Wagering Stance: Output pure relative implied densities (%), expected goals ($\lambda$), and joint score distributions. Strictly zero bookmaker odds, decimal prices, betting slips, affiliate referral links, or gambling calls to action.
   Model-Agnostic Engine Contract: MatchForge does not mandate a universal Bivariate Poisson or Dixon-Coles model. The active model family name is rendered dynamically only when tied to an loaded immutable forecast artifact (forecast_id).
   Mandatory Rust Simulation Validation & Publication Gating:
   Once activated under production policy, a newly generated forecast can be published only if it possesses a linked PASS simulation validation artifact.
   If validation is FAIL or INCONCLUSIVE, the candidate forecast must remain unpublished and cannot be displayed as a validated prediction.
   When the authorized analytic-only exception applies, the forecast must be visibly labeled ANALYTIC_ONLY.
   Previously published immutable forecasts remain accessible.
   Statistical Integrity Axiom: Simulation convergence demonstrates numerical consistency with the model's defined mathematical distribution; it does not prove predictive calibration on real subsequent football matches. Calibration is audited separately via chronological backtests.
   Decoupled Qualitative Display Tags: Contextual tags (DERBY, HIGH FORECAST UNCERTAINTY) provide qualitative structural context and never alter underlying model parameters, Poisson means, or probabilities.
2. Capability-Aware Presentation Matrix
   MatchForge maps UI presentation directly to backend capability registries and data licensing tiers to avoid fabricating predictions or placeholder zeros:

Capability State Backend Condition & Scope Frontend Visual Presentation
Supported Active production capability passed all validation checks in the competition tier. Full probabilities, progress bars, and expected means rendered normally.
Research Only Candidate model/feature under active research evaluation. Tagged RESEARCH ONLY; omitted from production totals; explicit descriptive note provided.
Pending Simulation validation or data ingestion in flight for this match. Animated skeleton / Validation Pending status pill; forecast probabilities and mini-bars are concealed in both collapsed and expanded views.
Unavailable Not supported or not licensed for this competition tier. Neutral card with explicit rationale: "Not available for this competition tier." Strictly no artificial zeros or placeholder odds.
Insufficient Data Historical sample or feature coverage below minimum statistical threshold. Informational card: "Insufficient qualified match history to estimate distribution."
Suspended Temporarily deactivated due to calibration drift, feed anomaly, or policy review. Amber notice: "Forecast market temporarily suspended pending review." 3. Screen Suite Architecture (11 Screens on Canvas)
The project includes 11 screens covering desktop and mobile viewports:

# Screen Title Device Key Analytical & Functional Elements

1 MatchForge — Desktop Fixtures List (Collapsed) Desktop Soccerway-style calendar table, date stepper, league groups, live/pre-match status, tri-outcome summary mini-bars, xG indicators, and inline expansion toggles.
2 MatchForge — Desktop Fixtures (Expanded Match Overview) Desktop Inline expanded hero panel: tri-outcome probability bar (43.9% / 26.4% / 29.7%), $\lambda_1$ vs $\lambda_2$, qualitative tags, top joint scoreline cards, and tab navigation bar.
3 MatchForge — Desktop Fixtures (Markets Tab) Desktop Grouped probability catalogue: 1X2, Total Goals O/U (0.5 to 4.5), BTTS, Individual Team Goals, Clean Sheets, and explicit unavailable cards for experimental markets (Corners, Cards).
4 MatchForge — Desktop Fixtures (Scores Matrix Tab) Desktop $4 \times 4$ joint discrete probability heatmap with modal score highlight (1–1 at 12.5%), dynamic coverage banner (91.8% in-grid, 8.2% tail mass mock baseline), and $7 \times 7$ enlargement toggle.
5 MatchForge — Desktop Fixtures (H2H Context Tab) Desktop Decoupled H2H reference table ("H2H Adjustment: Not used in this forecast"), historical encounters, managerial tenures, and regime stability metrics without distorting forecast distributions.
6 MatchForge — Desktop Fixtures (Team Statistics Tab) Desktop Side-by-side comparative parameters (10-match rolling xG, field tilt, rest days, squad availability) and predicted vs. confirmed lineup status without synthetic penalty deductions.
7 MatchForge — Desktop Fixtures (Simulation Evidence Tab) Desktop Dedicated validation card: PASS badge, engine version (v2.4.0-rust-sim), artifact ID, dynamic parity delta and policy threshold, convergence checks, and statistical truthfulness banner.
8 MatchForge — Desktop Fixtures (Diagnostics Tab) Desktop Authorized Research interface: parameter covariance ($\rho$), MCMC sampling decomposition (rendered conditionally only if algorithm uses MCMC), and reproducible seed checksums.
9 MatchForge — Desktop Fixtures (Forecast History Tab) Desktop Chronological immutable revision audit trail (T-48h, T-21h, T-5.5h iterations), knowledge cutoffs, revision reason codes, probability trajectory visual delta, and SHA-256 artifact export.
10 MatchForge — Mobile Fixtures List (Collapsed) Mobile (390px) High-density stacked team rows, kickoff time / minute status pill, tri-outcome mini-bar, and touch-optimized inline expansion affordances.
11 MatchForge — Mobile Fixtures (Expanded Overview) Mobile (390px) Inline expanded mobile dashboard with snap-scrolling analytical tab bar, high-contrast metric cards, and compact simulation validation summary without leaving the matchweek list. 4. Reusable Component Contracts
FixtureRow: Renders match time, clubs, crests, real score / status, tri-outcome mini-bar, and expansion chevron. If forecast_state === 'PENDING_VALIDATION' or UNPUBLISHED_FAIL, preview probabilities and mini-bars are concealed and replaced with an accessible status indicator.
ProbabilityBar: Tri-segmented colorblind-safe bar with explicit monograms (H, D, A) and pattern fills meeting WCAG 2.2 AA contrast standards ($\ge 4.5:1$).
SimulationEvidenceCard: Renders validation status (PASS, FAIL, INCONCLUSIVE), mode (RUST_VALIDATED, ANALYTIC_ONLY), eligible draws count, artifact ID, and dynamic parity checks ({ delta, threshold, passed }).
ScoreDistributionMatrix: $4 \times 4$ heatmap calculating visible_coverage_pct ($\sum P(i,j)$) and tail_mass_pct dynamically from the loaded forecast artifact without re-running simulations upon expansion. 5. Versioned Public & Research API Contracts
Existing Verified Endpoints:
GET /api/v1/fixtures?date=YYYY-MM-DD&competition_id=... — Returns fixtures, kickoff times, match status, and published forecast_id references.
GET /api/v1/forecasts/:forecast_id — Returns sealed immutable forecast artifact (1X2 probabilities, $\lambda_1, \lambda_2$, joint score probability array, knowledge cutoff, model identifier).
Proposed Additions (Formally Defined & Proposed):
GET /api/v1/fixtures/search?q=:query (PROPOSED) — Autocomplete search for teams, competitions, and venues.
GET /api/v1/fixtures/:id/forecast-availability (PROPOSED) — Lifecycle state (PUBLISHED, PENDING_VALIDATION, UNPUBLISHED_FAIL, ANALYTIC_ONLY_APPROVED, UNSUPPORTED_TIER).
GET /api/v1/forecasts/:id/simulation-evidence (PROPOSED) — Validation summary artifact.
GET /api/v1/fixtures/:id/forecast-history (PROPOSED) — Immutable pre-match iteration audit trail.
GET /api/v1/capabilities (PROPOSED) — Capability matrix across competition tiers and market types.
Authorized Research Endpoints (Authenticated):
GET /api/v1/research/forecasts/:id/diagnostics (RESEARCH ONLY) — Gated endpoint for parameter covariance, MCMC diagnostics, and reproducible seeds.
GET /api/v1/research/simulation/:artifact_id/full-parity-log (RESEARCH ONLY) — Full simulation verification manifests.
The complete specification is ready for engineering review, backlog grooming, and frontend implementation.
