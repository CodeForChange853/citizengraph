---
name: done-check
description: Run the project's "done" checks (pytest, ruff, and the frontend checks when frontend/ changed) and report exact results plus an explicit "Not verified" list. Check and report only. Use when the user types /done-check before calling a piece of work done.
disable-model-invocation: true
allowed-tools:
  - Bash(git status --porcelain)
  - Bash(git rev-parse --verify origin/main)
  - Bash(git diff --name-only origin/main...HEAD)
  - Bash(.venv/Scripts/python.exe -m pytest -q)
  - Bash(.venv/Scripts/python.exe -m ruff check .)
  - Bash(.venv/bin/python -m pytest -q)
  - Bash(.venv/bin/python -m ruff check .)
---

# done-check

CLAUDE.md, "How to work": "Done = named tests pass, `ruff` clean, docs updated if a
decision changed." This skill checks that and reports. It is check-and-report only:

- Do not fix failures, edit files, stage, commit or push unless the user asks afterwards.
- Do not edit CLAUDE.md.
- Do not install anything (no `pip install`, no `npm install`).
- Do not read anything under `eval/heldout/`.

Run every command from the repo root. Copy numbers from tool output; never estimate them.

## 1. Python checks

1. Find the project interpreter: `.venv/Scripts/python.exe` on Windows, `.venv/bin/python`
   elsewhere. If neither exists, say so and stop. Never fall back to a global Python.
2. Run `<venv python> -m pytest -q`. `pyproject.toml` sets addopts to `-m "not integration"`,
   so tests marked `integration` (real Neo4j or real model file) are deselected, not run.
3. Run `<venv python> -m ruff check .` (ruff is pinned in the `dev` extra). Run it even if
   pytest failed.

## 2. Changed files and frontend checks

1. Run `git rev-parse --verify origin/main`. If it succeeds, run
   `git diff --name-only origin/main...HEAD`.
2. Run `git status --porcelain` for uncommitted and untracked files.
3. Changed files = the union of both lists. If any path is under `frontend/`, run
   `cd frontend && npm run check && npm run build`. (`check` = tokens, lint, typecheck,
   test, contrast; `build` = tokens, `tsc --noEmit`, `vite build`.) Report each step
   separately; if `check` fails, `build` is "not run".
4. If `origin/main` is missing, say so and treat the frontend as changed-unknown: run both
   frontend checks if `frontend/` exists and `frontend/node_modules` is installed;
   otherwise list them under "Not verified".
5. If `frontend/` changed but `frontend/node_modules` is missing, do not install; list the
   frontend checks under "Not verified".

## 3. Report

Use exactly this format. On any failure, paste the failing output (failing test names with
their assertion or traceback, ruff diagnostics, the failing npm step) under the result line.

```
DONE-CHECK: <PASS | FAIL | INCOMPLETE>
Branch: <branch>   Compared with: <origin/main | origin/main missing>
Changed files: <n> (frontend/: <yes | no | unknown>)

pytest:   <passed> passed, <failed> failed, <skipped> skipped, <deselected> deselected, <errors> errors
ruff:     <n> errors
frontend: check <pass | fail | not run>, build <pass | fail | not run>

Not verified:
- Integration tests (real Neo4j / real model file): <n> deselected, not run
- <each skipped test or step, and why>
- <anything else, see below>

Decisions log: <reminder, see below>
```

- PASS only if every check that applies ran and passed. FAIL if anything failed.
  INCOMPLETE if nothing failed but a check that applies was not run. Never say "done"
  unless the verdict is PASS, and even then point at the "Not verified" list.
- "Not verified" always has the integration-tests line. Add, when relevant to the changed
  files: frontend checks not run; skipped tests with their skip reason; real-hardware
  benchmarks (`benchmarks/`); real-model or real-Neo4j behavior behind `FakeLLM` or the
  in-memory graph; Filipino wording still marked `# NEEDS-NATIVE-REVIEW`; docs not checked
  against the change (`docs/api_contract.md`, `docs/specs.md`).
- Decisions log: check that CLAUDE.md has a "Decisions log" heading. If it does, remind
  the user to add an entry there if this work changed a decision, and to update the
  relevant file in `docs/`. Do not write the entry yourself.
