web application/stitch/projects/8039649367732600182/screens/45fdba7d4a4a4db98decbd69c29be5e6

# MatchForge — Product Requirements Document (PRD) & Design Specification

**Document Version:** 1.0.0
**Status:** Approved / Specification Baseline
**Target Platform:** Responsive Web (Desktop-First, Tablet & Mobile 390px Optimized)
**Primary Archetype:** Quantitative Football Fixtures & Probabilistic Simulation Explorer

---

## 1. Executive Summary & Vision

### 1.1 Problem Statement

Mainstream football score platforms (Flashscore, Soccerway, Sofascore) focus primarily on historical scores and real-time live events, while sports prediction platforms are overwhelmingly dominated by sportsbooks, tipsters, affiliate wagering funnels, and misleading "guaranteed AI pick" claims.

Quantitative analysts, researchers, and serious football enthusiasts lack a **clean, transparent, non-wagering platform** where probabilistic match simulations (Poisson, Dixon-Coles, Monte Carlo draws) can be explored with data integrity, explicit uncertainty boundaries, and zero bookmaker clutter.

### 1.2 Product Vision

**MatchForge** is a desktop-first football fixtures and probability-analysis web application. It combines the rapid, date-driven, competition-grouped scanning pattern of Soccerway with an inline, high-fidelity quantitative forecast dashboard.

### 1.3 Core Axiom & Principles

1. **List First, Analysis on Demand**: Fixture lists remain scannable; clicking a row expands the analysis directly underneath the row without navigating away.
2. **Probabilities, Never Betting Odds**: Output pure relative implied densities (%), expected goals ($\lambda$), and joint distributions. Strictly zero bookmaker prices, decimal odds, betting slips, or affiliate links.
3. **Real Scores $\neq$ Forecast Scores**: Collapsed row scores represent actual past/live events; projected scorelines reside strictly within forecast views.
4. **Metadata Never Distorts Probabilities**: Badges such as `DERBY`, `ELEVATED RISK`, or `HIGH VOLATILITY` provide contextual explanation, never arbitrary synthetic probability nudges.
5. **Feature Truthfulness & Explicit Missing States**: Unsupported markets (e.g. Corners, Booking Points) display honest `Not yet supported` statuses rather than fabricated numbers.

---

## 2. Target Users & Use Cases

| User Persona                          | Key Objective                                                                      | Core Workflow                                                                                                                  |
| :------------------------------------ | :--------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------- |
| **Quantitative Researcher / Modeler** | Inspect underlying model parameters, calibration stability, and variance drivers.  | Navigates to Diagnostics & History tabs to audit MCMC convergence, low-score covariance ($\rho$), and Brier score calibration. |
| **Analytical Match Previewer**        | Understand tactical match dynamics and true goal expectation.                      | Evaluates team xG vectors, field tilt, and rest differentials on the Team Statistics & Overview tabs.                          |
| **Serious Football Enthusiast**       | Review deep scoreline distributions and probability spreads without betting noise. | Scans daily fixtures, expands top clashes, reviews exact score joint matrices and over/under lines.                            |

---

## 3. Information Architecture & Navigation

### 3.1 Global Chrome & Shell

- **Top Header**: Brand Logo (MatchForge vector icon + wordmark), Primary Nav (`Matches` [active], `Competitions`, `Results`, `Documentation`), Search (`Ctrl+K` for teams/leagues), Local Timezone selector (`UTC+0 / Local`), Feed Status (`Feed: Live`), and User Account avatar.
- **Left Sidebar**: Collapsible Competitions Tree grouped by Top Leagues (Premier League, La Liga, Bundesliga, Serie A, Ligue 1) and Continental Tournaments (UEFA Champions League, Europa League) with active match counters.
- **Main Viewport Header**: Date stepper (`< Prev Day`, `Today`, `Next Day >`, Calendar datepicker) alongside status segmentation tabs (`All Fixtures`, `Upcoming`, `Live Now`, `Finished`) and competition dropdown filter.
- **Footer**: Non-wagering regulatory disclaimer, Poisson engine build identifier, Monte Carlo cycle latency badge, and active socket status.

### 3.2 Continuous Inline Expansion Flow

Unlike traditional platforms that force a full-page redirect to a standalone match screen or open disruptive modals:

```
[ Fixture Row 1: Aston Villa vs Newcastle ]
[ Fixture Row 2: Arsenal vs Chelsea ]  <-- CLICKED
      ┌─────────────────────────────────────────────────────────────────┐
      │  INLINE FORECAST DASHBOARD (Expands in-place)                   │
      │  ├── Match Identity & Horizon Lock (e.g., 24h pre-kickoff)      │
      │  ├── Primary Probability Metrics (Home 43.9% | Draw 26.4% | Away 29.7%)
      │  ├── Lambda Means: Arsenal 1.42 xG vs Chelsea 1.18 xG           │
      │  ├── In-Panel Tab Bar (Overview, Markets, Scores, H2H, Stats...) │
      │  └── Tab-Specific Analytical Modules                            │
      └─────────────────────────────────────────────────────────────────┘
[ Fixture Row 3: Liverpool vs Everton ]
[ Fixture Row 4: Brighton vs Fulham ]
```

The user maintains complete visual grounding in the matchweek calendar at all times.

---

## 4. Detailed Feature Specifications

### 4.1 Screen 1: Desktop Collapsed Fixtures List (Landing State)

- **Scannable Table Rows**: Standardized grid columns: Time/Minute, Home Club, Home Crest/Crest Placeholder, Actual Score / Status, Away Club, Away Crest, Contextual Tag (`DERBY`, `TITLE CLASH`), Forecast Availability (`Forecast Ready`, `Forecast Pending`, `Pre-match archive`), and Expansion Chevron.
- **Match State Segmentation**:
  - _Pre-match_: Kickoff time (e.g. `15:00 UTC+0`), blank score (`— : —`), `Forecast Ready`.
  - _Live Match_: Minute tag (e.g. `63' LIVE`), real score (e.g. `1 - 0`), and `Pre-Match Ready` notice indicating forecast is frozen at kickoff.
  - _Finished_: Final score (e.g. `2 - 2 FT`), `Pre-match archive`.

### 4.2 Screen 2: Expanded Match Overview (Hero State)

- **Top Probability Bar**: High-contrast, colorblind-accessible tri-segmented bar displaying Home Win %, Draw %, and Away Win % alongside expected goal averages ($\lambda_1, \lambda_2$).
- **Context Badges**: `DERBY (London Derby)` and `ELEVATED RISK (+14% Sample Variance)` pills accompanied by explicit advisory: _"Information tags provide structural context; they do not alter model probabilities."_
- **Quick Metrics Grid**:
  - _Derived Poisson Markets_: BTTS (Yes 51.1% / No 48.9%), Total Goals Over/Under 2.5 (46.6% / 53.4%).
  - _Top 3 Scoreline Densities_: 1–1 (12.5%), 1–0 (11.2%), 2–1 (8.9%).
  - _Data Provenance & Ingestion_: Sample size (38 matches evaluated), H2H weight (`0.0% direct weight`), Model version (`v4.2.1-poisson.prod`).

### 4.3 Screen 3: Markets Tab

- **Full-Time Result (1X2)**: Proportional probabilities with dual Poisson parameter display ($\lambda_1 = 1.42, \lambda_2 = 1.12$).
- **Total Goals Distribution (0.5 to 4.5 Lines)**:
  - Over/Under probabilities for lines 0.5, 1.5, 2.5 (standard benchmark), 3.5, and 4.5 with paired percentage distribution bars.
- **Both Teams to Score (BTTS)**: Computed via bivariate convolution with dependency correction.
- **Individual Team Goals**: Discrete probabilities for 0, 1, 2, and 3+ goals for both home and away sides.
- **Clean Sheets & Margin Outlines**: Clean Sheet %, Win-to-Nil %.
- **Unsupported/Experimental Registry**: Explicitly labels unsupported markets (`Corners O/U 9.5 — Pending spatial model validation`, `Disciplinary Cards — Insufficient referee calibration`).

### 4.4 Screen 4: Scores Matrix Tab

- **$4 \times 4$ Joint Discrete Probability Matrix**:
  - Rows: Arsenal Goals ($0, 1, 2, 3$). Columns: Chelsea Goals ($0, 1, 2, 3$).
  - Cells display exact joint probability % and visual opacity shading. Modal density (`1-1 at 12.5%`) clearly demarcated.
- **Explicit Tail Disclosure**: Mandatory banner stating: _"Matrix Coverage: 91.8% accounted for in 0–3 grid. Outside displayed grid / tail events: 8.2% aggregate mass."_ Includes CTA to expand to $7 \times 7$ simulation.
- **Ranked Top 5 Density Cards**: Exact score, description, probability %, and fair statistical odds ratio benchmark.
- **Margin Density Breakdown**: Arsenal by 1 goal (24.3%), Arsenal by 2+ goals (19.6%), Draw (26.4%), Chelsea by 1 goal (18.2%), Chelsea by 2+ goals (11.5%).

### 4.5 Screen 5: H2H Context Tab

- **Non-Prior Protocol Notice**: Prominent callout declaring `H2H Influence on Predictive Model: 0.0% (Display-Only Context)`. Head-to-head records across varying managerial eras are excluded from Poisson parameter calculation to avoid regime-shift noise.
- **Sample Metrics**: 10-fixture sample window (2021–2024), aggregate score (18–14), and Regime Stability Index (`0.74 Elevated Variance` due to 4 distinct Chelsea coaching tenures).
- **Historical Encounters Table**: Date, competition, venue, score, halftime, Opta xG split, and managerial matchup (Arteta vs Pochettino / Lampard / Potter / Tuchel).

### 4.6 Screen 6: Team Statistics Tab

- **Side-by-Side Parameter Columns**:
  - Form badges (Last 5 domestic matches: W-W-W-D-W vs D-W-L-W-D).
  - 10-match rolling xG Generated vs Conceded (+1.42 vs +0.24 net xG differential).
  - Shot volume and target accuracy (16.8 shots/90 vs 13.2 shots/90).
  - Deep field tilt (68.4% vs 54.1% possession in attacking third).
  - Rest & conditioning cycles (6 days full rest vs 3 days rest with $-0.06$ xG fatigue adjustment).
  - Squad availability % (94.0% vs 82.0% with defensive absences noted).
- **Tactical Setup & Expected Threat (xT)**: Lineups explicitly flagged as `PREDICTED`, accompanied by rolling 6-match xT threat vector charts.

### 4.7 Screen 7: Diagnostics Tab

- **Risk Classification**: `STABLE SPECIFICATION` + `ELEVATED RISK (+14% Sample Variance)`.
- **MCMC Sampling Decomposition**: Monte Carlo convergence rate (`99.88%`), Gelman-Rubin convergence ($\hat{R} = 1.01$), and Dixon-Coles low-score covariance parameter ($\rho = -0.124$).
- **Variance Contributors**: Quantified impact of derby status ($0.00\%$ odds skew), lineup rotation ($+0.12$ variance), and pitch precipitation speed ($+2.1\%$ fast transition).
- **Data Quality Audit**: Ingestion latency (42 mins ago), missing feature values ($0/14$), and reproducible Monte Carlo seed (`#883910`).

### 4.8 Screen 8: Forecast History Tab

- **Pre-Kickoff Audit Trail**: Tracks model adjustments leading up to kickoff (e.g., T-48h opening baseline $\rightarrow$ T-21h midweek rest settlement $\rightarrow$ T-5.5h team arrival and weather calibration).
- **Horizon Stability Graph**: Visual delta line tracking probability movement across iterations with net 1X2 drift index (`0.018`, well within the $<0.05$ target threshold).
- **Cryptographic Audit Export**: SHA-256 verification hash and action to download full snapshot log in CSV/JSON.

---

## 5. Mobile & Tablet Responsiveness Matrix

| Component             | Desktop ($\ge 1200\text{px}$)                                            | Tablet ($768\text{px} - 1199\text{px}$)              | Mobile ($390\text{px}$)                                                                       |
| :-------------------- | :----------------------------------------------------------------------- | :--------------------------------------------------- | :-------------------------------------------------------------------------------------------- |
| **Fixtures Table**    | Horizontal multi-column layout with synchronized team labels and crests. | Preserves table layout; sidebar collapses to drawer. | Stacked team layout (Home above Away), compact status badge on right, tap anywhere to expand. |
| **Expanded Panel**    | Full-width inline container beneath row; multi-column analytical grids.  | 2-column stacked analytical cards.                   | Single-column stack; tabs horizontally scrollable with snap-scrolling.                        |
| **Score Matrix**      | Visible $4 \times 4$ grid with margin bars side-by-side.                 | Matrix full-width, margin bars underneath.           | Self-contained horizontal scroll container preserving fixed row/column headers.               |
| **Markets Catalogue** | 2-column structured comparison rows with progress indicators.            | Single-column grouped cards.                         | Compact accordion cards with large touch-friendly targets.                                    |

---

## 6. Technical Stack & Data Ingestion Architecture

- **Frontend Architecture**: Single Page Application with server-side rendered initial state; zero full-page reloads on match expansion.
- **Simulation Engine**:
  - Generalized linear bivariate Poisson model with Dixon-Coles low-score dependency adjustment ($\rho$).
  - Monte Carlo sampler: 10,000 draws per fixture run; stationary Markov chains with Gelman-Rubin $\hat{R} < 1.05$.
- **Data Ingestion**: Opta / StatsPerform tier-1 feed integration, synced on 15-minute scheduled intervals and pre-kickoff lineup confirmations.
- **State Management**: URL query-string synchronizes selected date and active expanded fixture (`?date=2026-09-28&fixture=epl-ars-che&tab=markets`) to support direct deep linking without modal loss.

---

## 7. Non-Functional & Regulatory Requirements

1. **Accessibility (WCAG 2.1 AA)**:
   - Contrast ratio $\ge 4.5:1$ on all text and metric labels across the dark theme (`#0f131c` canvas).
   - High-contrast visual patterns and numeric labels paired with all color-coded probability bars.
2. **Performance SLA**:
   - Time to Interactive (TTI) $< 1.2\text{s}$ on 4G connections.
   - Inline expansion panel render time $< 50\text{ms}$ (pre-computed client-side JSON cache).
3. **Compliance & Disclaimers**:
   - Zero real-money wagering, bet slip creation, affiliate referrals, or bookmaker pricing.
   - Mandatory visible disclaimer: _"MatchForge probabilistic model forecasts are independent statistical simulations for research purposes. Not a sportsbook or gambling operator."_
