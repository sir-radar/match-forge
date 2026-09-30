# Accessibility verification

- Automated: axe-core 4.10.2 runs after inline fixture expansion in Chromium desktop and WebKit iPhone 13 projects; zero violations after remediation.
- Semantics: one page-level `h1`, labelled primary/mobile navigation, main landmark, fixture sections, disclosure buttons with `aria-expanded`/`aria-controls`, tabs/tabpanel, data tables and labelled probability summaries.
- Keyboard: native buttons, links, selects, date input and tabs remain in DOM order; skip link is available; no pointer-only handler is used.
- Focus: browser focus indication is retained with a three-pixel offset; no blanket outline removal.
- Responsive: desktop rail is hidden on mobile; data remains available through filters and grouped rows; wide tables/tabs/matrix scroll without page-level horizontal clipping.
- Motion/preferences: reduced-motion and forced-colors rules are present. No essential information is encoded only by animation.
- Screen reader boundary: H2H/context and external selections are explicitly described as display-only and cannot be mistaken for probability adjustments.
