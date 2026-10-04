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

Manual VoiceOver interaction and formal all-criteria WCAG 2.2 conformance were
not run, so this report claims only the checks above.
