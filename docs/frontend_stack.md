# Frontend stack (built against the mock API)

Code is in `frontend/`. Run instructions: `frontend/README.md`. Design decisions: `frontend/DESIGN.md`.

- **React + TypeScript + Vite** for the app.
- **Tailwind CSS v4** for styling. Colours come only from `frontend/src/design/tokens.json` (Tailwind defaults are removed); `npm run contrast` fails below WCAG AA.
- **vite-plugin-pwa** (Workbox) for installability and offline: cache the app shell and
  the last viewed checklists so a citizen can still read them without a signal.
- **Framer Motion** (package `motion`), used sparingly for small transitions (message
  entrance, expanding a section). Respect `prefers-reduced-motion`.
- **Skip GSAP**: timeline animation is not needed for a chat UI and adds weight.
- Extras: `react-i18next` for the EN/FIL toggle, `@tanstack/react-query` for API calls, `react-router`.
- Tests: Vitest + Testing Library. `npm run check` = tokens + lint + typecheck + tests + contrast.
- Fonts are bundled locally (`@fontsource/atkinson-hyperlegible`); no Google Fonts.
- API client: typed, with a real adapter (Vite proxy `/api`) and a fixture adapter used when the API is unreachable or `VITE_USE_FIXTURES=1`.

Design principles: plain short sentences, numbered lists, big buttons for clarify options,
one clear next action, works on low-end Android phones, no heavy animation, fully usable
with the mock API from `docs/api_contract.md`. Intent-first, no login, no government marks.
