# Frontend stack (recommendation, to be built against the mock API)

- **React + TypeScript + Vite** for the app.
- **Tailwind CSS** for styling (large touch targets, high contrast, readable type).
- **vite-plugin-pwa** (Workbox) for installability and offline: cache the app shell and
  the last viewed checklists so a citizen can still read them without a signal.
- **Framer Motion** (package `motion`), used sparingly for small transitions (message
  entrance, expanding a section). Respect `prefers-reduced-motion`.
- **Skip GSAP**: timeline animation is not needed for a chat UI and adds weight.
- Extras: `react-i18next` for the EN/FIL toggle, `@tanstack/react-query` for API calls.

Design principles: plain short sentences, numbered lists, big buttons for clarify options,
one clear next action, works on low-end Android phones, no heavy animation, fully usable
with the mock API from `docs/api_contract.md`.

Scaffold (when starting): `npm create vite@latest frontend -- --template react-ts`
