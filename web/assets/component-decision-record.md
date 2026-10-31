# Component decisions

- Create locally: repository had no production frontend.
- Share only repeated primitives: probability bar, status badge, app shell.
- Share one typed inline-SVG icon primitive across shell and fixture consumers;
  remote icon-font loading is not reliable enough for interface controls.
- Do not promote tabs, score matrix, or tables into a generic design system;
  their content and accessibility contracts remain feature-specific.
- Keep all new APIs additive. No existing frontend consumers exist.
- Native controls own keyboard behavior: buttons, links, date input, selects,
  tables, and disclosure buttons.
- Keep the supplied external-prediction composition route-local. Reuse
  `Icon`, `Logo`, `useResource`, and API contracts; do not promote mock-only
  cards, audit rows, or badges into shared APIs. `AppShell` yields the complete
  route shell on `/predictions` so the route can match the supplied fixed header
  and footer without changing other pages.
- Keep `BackToTop` route-local to `AppShell`. Reuse the existing chevron icon,
  colors, focus treatment, and native button behavior; do not add a shared
  floating-action API for one consumer.
- Keep performance paging controls local to `PerformancePage`. The backend owns
  slicing and totals; the route owns page and page-size state. No Figma source
  was supplied, so existing MatchForge tokens and responsive rules remain the
  design source.

31 October 2026: reuse the Admin shell, status resources, TableScroll and existing
CSS variables. Share AdminNavigation across its two current consumers. Keep case
review and evidence presentation local; no generic schema-driven form or shared
component API is needed for the read-only workflow.

Phase 3 keeps the single-case decision form local to Resolution Center. Native
selects expose only retained candidates and contradiction contexts. Backend
qualification is mandatory even when a candidate is visible. Owner credentials
stay in form memory and never enter URLs, storage, audit details or Python stdin.
