# Citizen Graph

Dual-core neuro-symbolic assistant for LGU frontline services (thesis project):
a Text-to-Cypher pre-screening assistant (Core 1) and an autonomous SLA-monitoring
agent (Core 2), running fully local on modest hardware.

Start with `CLAUDE.md` (rules and architecture), then `docs/`.

## Quick start (backend)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
uvicorn citizengraph.api.main:app --reload
```

Open http://127.0.0.1:8000/docs to try the mock API. `/chat` currently returns
**mock data** so the frontend can be built before the real pipeline exists.

Neo4j (optional for now): copy `.env.example` to `.env`, set a password, then
`docker compose up -d`.

## Layout

See `CLAUDE.md`. Key folders: `data/raw` (source charters), `docs`, `config`, `graph`,
`src/citizengraph`, `training`, `eval`, `benchmarks`, `tests`, `frontend`.

## Status

Skeleton only. Implemented: mock API, `FakeLLM`, fail-closed guardrail placeholder, tests, CI.
Next: guardrail, loader and curated seed data, gateway, Core 1, Core 2, composer, eval harness.
See `docs/charter_data.md` for open data questions.

## Safety notes

- The system is read-only by design; never add write paths to the official graph.
- Never commit real citizen data, model weights, or `.env`.
- `eval/heldout/` holds the 150 real test inquiries and must never be used for training.
