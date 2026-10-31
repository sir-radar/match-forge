# Accessibility verification

- axe-core 4.10.2: zero violations across fixtures, performance, predictions,
  and admin journeys in the configured desktop and mobile Chromium projects.
- Reverified `/predictions` on 3 October 2026 at 1187×1600 desktop and iPhone 13:
  zero axe-core violations; one top-level `main` landmark; labeled native filters;
  labeled previous/next-day controls; keyboard-focusable horizontal tables;
  visible text on every status color.
- Native links, buttons, inputs, selects, disclosures, tabs, and tables.
- Skip link, main/primary/mobile landmarks, complementary rail, grouped fixture
  sections, tablist, and tabpanel.
- DOM order matches task order; all actions are keyboard operable; visible focus
  uses a 2px cyan outline.
- Dedicated 390px mobile composition; wide tabs/matrix/tables scroll locally.
  Overflowing data tables are keyboard-focusable.
- Reduced-motion and forced-colors rules; labels accompany color/status values.
- Reverified `/` and `/performance` on 4 October 2026 in desktop Chromium and
  320px-wide mobile Chromium. Pagination uses labeled native controls, keyboard
  activation, disabled boundary states, and a polite page-status announcement.
  Back-to-top uses a 44px native button, keyboard activation, main-content focus
  transfer, reduced-motion scrolling, forced-colors styling, and mobile-nav
  clearance. axe-core reported zero violations in normal color mode.
- Reverified `/admin/data-sync` on 12 October 2026 in desktop and mobile
  Chromium after adding provider coverage and quota diagnostics. The focused
  Playwright run passed all three applicable assertions and axe-core reported
  zero violations. Metrics remain native `dl` content and all sync actions use
  labeled native buttons.

Manual VoiceOver interaction and formal all-criteria WCAG 2.2 conformance were
not run, so this report claims only the checks above.

31 October 2026 Resolution Center: desktop/mobile Chromium checks cover all six
sections, axe, labeled filters, native disclosures, heading focus after inspection,
opener focus on close, 320px reflow, local keyboard table scrolling, reduced-motion
and forced-colors presence. A separate browser journey uses the real Go/Python
backend in a disposable database. No manual screen-reader claim is made.

Phase 4 real desktop browser batch review passed axe with zero violations before approval. Native labeled selection checkboxes and per-case preview disclosures remain keyboard accessible. Cross-page selection and qualified/blocked result announcements are covered by component tests.
