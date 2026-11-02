# MatchForge Frontend Engineering Standards

**Scope:** All frontend changes under `./web`. Read alongside the repository's root `AGENTS.md` and applicable contracts. These rules do not authorize new product scope, changes to approved architecture, or bypassing quality gates.

## 1. Authoritative UI Design

- **Use the relevant `./web/ui-designs/*.html` file as the UI source of truth.** Inspect its markup, styling, layout, content, interactions, and responsive behavior before implementing or changing a screen.
- Match the HTML reference's visual structure, spacing, typography, colors, states, and responsiveness. Treat images and screenshots as secondary references, **not** as the source of truth when HTML exists.
- Reproduce the intended design using the approved component system rather than copying static HTML/CSS blindly. Preserve accessibility and app behavior; explicit owner decisions and approved functional/security contracts still take precedence.
- If no corresponding HTML exists, use existing shared design patterns and identify any genuine design ambiguity instead of inventing a conflicting UI.

## 2. UI Framework and Styling

- **Use shadcn/ui and Tailwind CSS as the default and exclusive UI component/styling system.** Prefer existing shadcn/ui components, Tailwind utilities, and shared design tokens over hand-built equivalents.
- Do not introduce another UI framework, component library, CSS-in-JS system, or utility-CSS framework without explicit owner approval. Specialized non-UI libraries may be used under the library-selection rule below.
- Use custom CSS **only when necessary** for a requirement that cannot be expressed cleanly using Tailwind utilities, supported variants, shadcn/ui patterns, or existing design tokens. Keep exceptions minimal, scoped, and documented in code when the reason is not obvious.
- Reuse existing theme variables, component variants, and accessible interaction patterns. Do not hardcode repeated visual values or fork components for minor cosmetic differences.

## 3. Prefer Proven Open-Source Solutions

- Before implementing complex UI behavior or utilities, search the codebase for an existing solution, then evaluate established, actively maintained open-source packages.
- Prefer compatible, accessible, well-tested libraries over reinventing common solutions (for example, forms, validation, date handling, charts, or complex interactions). Check official documentation, maintenance, licensing, bundle cost, security, and compatibility with the project's versions.
- Reuse already-installed dependencies where suitable. Avoid adding a dependency for trivial functionality or introducing packages that duplicate existing capabilities.

## 4. Rendering and Data Fetching

- **Default to server-first rendering wherever the application's existing framework supports it.** In Next.js, keep pages/layouts as Server Components by default; use server-side rendering for request-dependent, SEO-sensitive, or fresh server-data pages when appropriate.
- Prefer static generation/caching for content that can safely be pre-rendered. Choose SSR, static rendering, and revalidation based on actual data freshness, personalization, and caching needs, not a blanket rule that everything must be dynamic.
- Use Client Components only for interactivity, browser-only APIs, or client state. Keep `use client` boundaries as small as practical; do not turn an entire page into a Client Component merely to support one interactive element.
- Fetch and authorize sensitive data on the server where possible. Avoid exposing secrets, duplicating fetches, unnecessary hydration, and client-side waterfalls.
- If the current framework does not support the rendering mode a page requires, report the architectural constraint rather than introducing a new framework or SSR infrastructure without approval.

## 5. Reuse, Quality, and Tests

- Search for existing components, layouts, hooks, utilities, data-fetching logic, and domain rules before creating new ones. Extract shared code when actual duplication warrants it; do not build speculative abstractions.
- Keep a single implementation of shared UI behavior and business logic. Use composition, reusable variants, and existing state/data patterns instead of copied pages or divergent implementations.
- Implement semantic HTML, keyboard and screen-reader accessibility, responsive layouts, and appropriate loading, empty, error, and success states.
- **Do not introduce flaky tests.** Write isolated, deterministic tests with stable fixtures/selectors, controlled time, and reliable mocks or test data. Wait for observable conditions rather than fixed sleeps; do not depend on live external services or test order.
- Investigate and fix intermittent failures at their root. Never silently rerun until green, disable, skip, or weaken tests to make a change pass.

## 6. Verification Before Delivery

- Compare changed screens with the corresponding `./web/ui-designs/*.html` references at relevant viewport sizes and interaction states.
- Run applicable formatting, lint, type checks, component tests, and browser/integration tests according to the root `AGENTS.md` validation policy.
- Check that changes add no unnecessary custom CSS, duplicate UI/logic, avoidable client-side rendering, unused dependencies, or flaky tests. Report any unavoidable design or rendering deviations.
