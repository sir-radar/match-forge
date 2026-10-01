# Accessibility verification

- axe-core 4.10.2: zero violations across fixtures, performance, predictions,
  and admin journeys in the configured desktop and mobile Chromium projects.
- Native links, buttons, inputs, selects, disclosures, tabs, and tables.
- Skip link, main/primary/mobile landmarks, complementary rail, grouped fixture
  sections, tablist, and tabpanel.
- DOM order matches task order; all actions are keyboard operable; visible focus
  uses a 2px cyan outline.
- Dedicated 390px mobile composition; wide tabs/matrix/tables scroll locally.
  Overflowing data tables are keyboard-focusable.
- Reduced-motion and forced-colors rules; labels accompany color/status values.

Manual VoiceOver interaction and formal all-criteria WCAG 2.2 conformance were
not run, so this report claims only the checks above.
