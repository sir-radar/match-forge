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
