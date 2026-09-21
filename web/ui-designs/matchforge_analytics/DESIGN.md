---
name: MatchForge Analytics
colors:
  surface: '#0f131c'
  surface-dim: '#0f131c'
  surface-bright: '#353943'
  surface-container-lowest: '#0a0e17'
  surface-container-low: '#181b25'
  surface-container: '#1c1f29'
  surface-container-high: '#262a34'
  surface-container-highest: '#31353f'
  on-surface: '#dfe2ef'
  on-surface-variant: '#bbcabf'
  inverse-surface: '#dfe2ef'
  inverse-on-surface: '#2c303a'
  outline: '#86948a'
  outline-variant: '#3c4a42'
  surface-tint: '#4edea3'
  primary: '#4edea3'
  on-primary: '#003824'
  primary-container: '#10b981'
  on-primary-container: '#00422b'
  inverse-primary: '#006c49'
  secondary: '#7bd0ff'
  on-secondary: '#00354a'
  secondary-container: '#00a6e0'
  on-secondary-container: '#00374d'
  tertiary: '#c0c1ff'
  on-tertiary: '#1000a9'
  tertiary-container: '#9699ff'
  on-tertiary-container: '#1d17b2'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#6ffbbe'
  primary-fixed-dim: '#4edea3'
  on-primary-fixed: '#002113'
  on-primary-fixed-variant: '#005236'
  secondary-fixed: '#c4e7ff'
  secondary-fixed-dim: '#7bd0ff'
  on-secondary-fixed: '#001e2c'
  on-secondary-fixed-variant: '#004c69'
  tertiary-fixed: '#e1e0ff'
  tertiary-fixed-dim: '#c0c1ff'
  on-tertiary-fixed: '#07006c'
  on-tertiary-fixed-variant: '#2f2ebe'
  background: '#0f131c'
  on-background: '#dfe2ef'
  surface-variant: '#31353f'
typography:
  headline-xl:
    fontFamily: Space Grotesk
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Space Grotesk
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0em
  body-lg:
    fontFamily: Geist
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
  body-md:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  body-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-lg:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0.02em
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.04em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '600'
    lineHeight: 12px
    letterSpacing: 0.06em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 0.75rem
  gutter-desktop: 1rem
  margin: 1rem
  margin-desktop: 1.5rem
  space-xs: 0.25rem
  space-sm: 0.375rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style

The design system establishes a high-density, scientific football intelligence environment calibrated for quantitative analysts, professional scouts, and data-driven researchers. The brand persona is dispassionate, authoritative, and methodically precise. It strips away all sensationalism, emotional fan tropes, and sportsbook artifacts (no betting slips, no flashing odds, no aggressive yellow accentuation). Instead, the interface mirrors institutional scientific workstations, Bloomberg-grade financial terminals, and refined computational labs.

The visual style synthesizes modern technical minimalism with architectural data structures. The UI communicates reliability through exact structural boundaries, ultra-crisp tabular layouts, muted informational status cues, and dense information hierarchies that allow continuous scanning of complex multi-variable models (such as Poisson distributions, Expected Goals / xG splits, and probabilistic match trajectories). The emotional response should be one of deep control, clarity, and analytical trust.

## Colors

The system relies on an uncompromising deep-slate chromatic architecture (`#090D16`) optimized for prolonged low-glare analytical sessions. Color is used strictly as an informational and semantic instrument, never for ornamental distraction.

- **Primary (`#10B981` — Tactical Emerald):** Denotes positive expectancy, favorable statistical thresholds, validated models, and high-probability confidence bands.
- **Secondary (`#38BDF8` — Precision Cyan):** Applied to active fixtures, temporal filters, interactive timeline nodes, and analytical focus states.
- **Tertiary (`#6366F1` — Deep Indigo):** Reserved for institutional meta-data, secondary distribution curves, and Bayesian predictive indicators.
- **Neutral Palette (`#090D16` base):** Stepped through strictly measured slate tiers:
  - Surface Foundation: `#090D16`
  - Elevated Container / Grid Rows: `#0F172A`
  - Subtle Surface Alt / Hover States: `#1E293B`
  - Structural Table Gridlines: `#334155`
  - De-emphasized Text / Metadata: `#94A3B8`
  - Primary Tabular Typography: `#F8FAFC`
- **Probabilistic Semantic Spectrum:** 
  - Risk / Variance Warning: `#F43F5E` (Crimson)
  - Neutral / Equilibrium: `#F59E0B` (Amber)
  - Home / Draw / Away Distributions: Subdued split fills using Emerald (`#10B981`), Muted Slate (`#64748B`), and Cyan (`#38BDF8`).

## Typography

The typographic system utilizes a specialized tri-font hierarchy geared for rigorous numerical comparison:

1. **Space Grotesk (Headlines):** Delivers clean structural framing with subtle computational geometry. It anchors module banners, competition titles, and primary analytical headers without decorative fluff.
2. **Geist (Body & Interface):** Provides ultra-neutral, legible structural copy for team descriptors, analytical narratives, and tooltips.
3. **JetBrains Mono (Data, Tabular Figures, & Badges):** The core engine of the system. All probabilities, timestamps, xG measures, coordinate vectors, and metadata labels are rendered in monospace with `font-variant-numeric: tabular-nums lining-nums`. This guarantees that columns align down to the pixel across complex fixture matrices.

## Layout & Spacing

The layout model is desktop-first, highly compact, and grounded in a 16-column flexible data grid. The philosophy rejects vacant, decorative whitespace in favor of rhythmic, dense information throughput similar to computational workbench layouts.

- **Breakpoints:**
  - **Desktop (>= 1280px):** 16 columns. Simultaneous display of competition tree, main multi-fixture probabilistic table, and an inspector/matrix sidebar.
  - **Tablet / Compact Desktop (768px - 1279px):** 8 columns. Sidebar docks into a contextual bottom drawer or secondary tab.
  - **Mobile (< 768px):** 4 columns. Compact single-column fixture stream with horizontal scroll locks for multi-variable data columns.
- **Rhythm & Compaction:** Vertical data rows utilize strict 32px or 36px fixed heights to optimize screen real estate, allowing 20+ fixtures to be visually digested in a single viewport. Padding follows an internal 4px/8px micro-grid.

## Elevation & Depth

Visual hierarchy is executed strictly through **tonal layering and low-contrast perimeter gridlines**, rejecting diffuse ambient drop-shadows or skeuomorphic bevels:

- **Level 0 (Canvas Base):** Deepest slate (`#090D16`), framing the workbench.
- **Level 1 (Data Surfaces & Tables):** `#0F172A` paired with hairline grid borders (`1px solid #1E293B`).
- **Level 2 (Sticky Headers & Focused Cells):** `#1E293B` with border accentuation using `#334155`.
- **Level 3 (Overlays, Flyouts, & Diagnostic Inspectors):** `#131E32` with high-definition boundary borders (`1px solid #38BDF8/30`) to crisply isolate floating analytics from background rows.
- **Focus & States:** Interactive rows and table data cells employ a sharp `inset 0 0 0 1px` stroke or subtle background shift to `#1E293B` rather than blurred outer halos.

## Shapes

The design system adopts a **Soft (Level 1)** geometric standard. Corner radiuses are restrained:
- Primary container panels, data grids, and cards use `0.25rem` (4px).
- Badges, status markers, and micro distribution cells use `0.125rem` (2px) or `0.25rem` (4px) to retain maximum architectural sharpness.
- Form inputs, buttons, and segmented probability bars maintain tight, disciplined corners. Pill shapes (`rounded-full`) are strictly forbidden, as roundness degrades tabular density and contradicts the scientific workstation tone.

## Components

### 1. Data Tables & Tabular Matrix Cells
- **Row Styling:** Alternating subtle row fills (`#0F172A` / `#0D1525`), fixed 34px height, hover state `#1E293B`.
- **Cell Borders:** Hairline borders (`#1E293B`) between columns. Right-aligned numbers formatted in `JetBrains Mono`.
- **Probability Matrix Cells:** Contain normalized 3-way percentages (Home/Draw/Away) with an underlying proportional micro-fill or heat-map background opacity (e.g. 5% to 35% alpha of primary/secondary colors).

### 2. Buttons & Action Bars
- **Primary:** Solid `#10B981` background, `#090D16` bold text, zero shadow, sharp 4px corners, 32px height.
- **Secondary / Filter:** Translucent `#1E293B` fill, `#94A3B8` text, `#334155` border. On hover: border shifts to `#38BDF8`, text to `#F8FAFC`.
- **Icon / Action Triggers:** 28px square compact toggles with monospaced glyphs or thin, geometric SVG vectors.

### 3. Metadata Badges
- **Analytical Indicators (`DERBY`, `ELEVATED RISK`, `PRE-MATCH FORECAST`):**
  - Font: `JetBrains Mono`, 10px uppercase, letter-spacing `0.06em`.
  - Construction: `#0F172A` background, `1px solid` border corresponding to status (Amber for Risk, Indigo for Forecast, Rose for Derby), subtle 10% tinted background fill. Compact padding: `2px 6px`.

### 4. Probabilistic Indicator Bars
- **Tri-segment Distribution Bar:** Integrated into match header rows. A 4px high segmented bar representing H / D / A probabilities in emerald, slate-400, and precision cyan. Zero gaps between segments, rounded only at outer parent boundaries (2px).

### 5. Form Inputs & Filters
- **Search & Parametric Sliders:** Background `#090D16`, border `1px solid #334155`, text `#F8FAFC`. Height 30px. Placeholder text `#64748B`. Focus indicator: `1px solid #38BDF8`.
- **Checkbox & Radio Controls:** Square 14px inputs with crisp, non-rounded internal tick markers. No floating drop shadows.

### 6. Cards & Inspect Panels
- Structured with an explicit header bar (border-bottom `1px solid #1E293B`, background `#0A101D`), compact internal padding (`0.75rem`), and strict tabular alignment of Poisson grids and xG goal expectation curves.