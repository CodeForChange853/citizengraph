# Frontend (citizen PWA mock)

Mobile-first (360px) app for citizens: what to bring, what it costs, where to go. English and Filipino.
No login. Runs on **mock data** only. Not an official government app.

Stack: Vite, React, TypeScript, Tailwind v4, react-router, react-i18next, TanStack Query, Motion, Vitest.
Needs Node 20+ (tested on 22).

## Run

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Useful routes: `/design` (every token and component).

**Without Python:** `npm run dev` works on its own. If the API is unreachable the app uses local fixtures
(`src/api/fixtures.json`). Force it with `VITE_USE_FIXTURES=1`:

- PowerShell: `$env:VITE_USE_FIXTURES = "1"; npm run dev`
- macOS/Linux: `VITE_USE_FIXTURES=1 npm run dev`

**With the Python mock API** (from the repo root, in a second terminal):

```
pip install -e ".[dev]"
uvicorn citizengraph.api.main:app --port 8000
```

The dev server proxies `/api/*` to `http://127.0.0.1:8000`.

## Try it as an installed, offline app

```
npm run build
npm run preview        # http://localhost:4173, the service worker only runs in a build
```

Open it once, then stop the server or turn on airplane mode and reload: the app shell, saved lists and your
last answers still open. Icons are rendered with `npm run icons` from `public/icon.svg`.

## Checks

```
npm run check      # tokens + lint + typecheck + tests + contrast
npm run contrast   # WCAG AA check of every colour pair we use, both themes
```

Repo root: `ruff check .` and `pytest`.

## Fixtures

The mock data lives in `src/citizengraph/api/main.py` (from `graph/seed/*.yaml`). After changing it:

```
python frontend/scripts/export_fixtures.py
```

`tests/test_api.py` fails if `src/api/fixtures.json` drifts from the mock.

## Filipino text

Filipino strings are unverified. `NEEDS-NATIVE-REVIEW.md` lists them all; regenerate it with
`npm run i18n:review` after editing `src/i18n/fil.json` (a test checks it is complete).

Design decisions: `DESIGN.md`. API: `../docs/api_contract.md`.
