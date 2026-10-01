# Admin data-sync accessibility report

Scope: `/admin/data-sync`, desktop Chrome and mobile Chromium projects, default, loading, ready, queued, success-history, and API-error states.

Implemented checks:

- one page heading and ordered section headings;
- labeled date and advanced filter inputs;
- native buttons, details, summary, table, caption, and row headers;
- `role=status`/`aria-live=polite` for run state;
- `role=alert` for actionable request errors;
- all start controls disabled during queued, running, or submitting state;
- visible focus inherited from the app shell;
- four-item mobile navigation without horizontal clipping;
- forced-color borders for state regions and buttons;
- reduced-motion rule inherited from the app stylesheet;
- axe scan in desktop and mobile Playwright projects.

Manual assistive-technology testing is not claimed. Final automated, keyboard, 320 CSS-pixel reflow, and build results are recorded in the delivery report.
