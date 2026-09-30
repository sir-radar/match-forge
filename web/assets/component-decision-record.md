# Component decisions

- Create locally: repository had no production frontend.
- Share only repeated primitives: probability bar, status badge, app shell.
- Do not promote tabs, score matrix, or tables into a generic design system;
  their content and accessibility contracts remain feature-specific.
- Keep all new APIs additive. No existing frontend consumers exist.
- Native controls own keyboard behavior: buttons, links, date input, selects,
  tables, and disclosure buttons.
