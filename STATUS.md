# STATUS — rampa-backend MVP

> **Read first.** After every step (🔴 red / 🟢 green / 🔵 refactor / task done): update this file + local commit. Push when online.
> Plan: [README.md](README.md) · features: [features/](features/)

## Current

- **Task:** F12 front-end bridge — done, pushed (`85a358e`); front end `api.js` in progress in `Yannie-draft-acihy`
- **Who:** Claude
- **State:** done
- **Next step:** verify Render picked up `85a358e` (`POST /api/v1/auth/anonymous` must stop returning 404). Then, for the map front end: `GET /observations?active=true&bbox=` with place location + report severity (one request instead of per-place reads); `FeatureKey`s for `escalator`, `tactile`, `sign` or drop them from the front end. Still open from F11: docker compose up + PG tests + F11 docs
- **Last pytest:** `uv run pytest` → 230 passed, 7 skipped (PG); bridge tests also green with `REPO_MODE=sql`
- **Branch:** `master`

## Run

```
uv sync
uv run pytest
uv run python main.py   # http://localhost:8000/docs
```

## Blockers / decisions

- F1.0 needs a human: Google Cloud OAuth "Web" client + `GOOGLE_CLIENT_ID` in `.env`. Demo mode works without it.

## Tasks

States: `todo` · `red` · `green` · `done` · `blocked`

| Task | What | Who | State | Notes |
|---|---|---|---|---|
| F0.1–F0.8 | Skeleton | Claude | done | `2c032f2` |
| F1.0 | Google Cloud OAuth client (human, online) | | todo | |
| F1.1–F1.4 | Auth: tests, use cases, Google adapter, HTTP | Claude | done | real Google token untested (needs F1.0) |
| F1.5 | Front button | frontend | todo | |
| F2.1–F2.5 | Places, search, check; demo steps 1–3 | Claude | done | steps 1–3 green |
| F3.1–F3.8 | Trust, validation, reports, uploads, votes; steps 4–6 | Claude | done | steps 4–5 green; step 6 needs F4 endpoint |
| F4.1–F4.4 | Queue, decision; step 7 → full flow green | Claude | done | full demo flow green |
| F5.1–F5.4 | Open API: key, rate limit, flat format | Claude | done | e2e P1–P5 + 2×401 in demo.http |
| F6.1–F6.5 | AI image tags: mock + ONNX Phi-3.5 + fallback | Claude | done | real ONNX inference untested here (manual: uv sync --extra ai) |
| F7.1–F7.4 | Owner role + verified_owner observations | Claude | done | e2e owner scenario O0–O11 + 3×403 + 400 |
| F8.1–F8.5 | OSM import (file) + MCP client of Open API | Claude | done | MCP stdio smoke OK (tools/list + call Tauron → yes) |
| F9.1–F9.5 | Persistence: SQLite + SQLAlchemy (write-behind SqlRepo) | Claude | done | demo flow also green on SQL; live restart keeps data |
| F10.1–F10.4 | Gemini vision adapter (AI_MODE=gemini, config-driven) | Claude | done | live Gemini OK (gemini-3.8-flash): stairs → critical; 503s retried |
| F11.1–F11.5 | Postgres + docker-compose, DB choice via env/config | Claude | green | Postgres runtime NOT verified (docker up not run); docs for F11 pending |
| F12.1–F12.4 | Front-end bridge: `POST /auth/anonymous`, `POST /places/resolve` | Claude | done | `85a358e`; 24 tests (use cases + HTTP two-device flow); contract 9 specs; docs + demo.http B1–B7 |

## Log (newest first)

- 2026-10-03 · F12 · done · committed + pushed `85a358e` (master); front end: `static/api.js` adapter (local SQLite | Rampa via `GET /api/config`), type/severity mapping, `bp.token`, resolve → report, votes on `observation_ids[0]`
- 2026-10-03 · F12 · live · two-device flow verified over HTTP (uvicorn :8002); fix: Starlette 400 (undecodable body) mapped to NOT_A_REAL_PLACE instead of VALIDATION_ERROR; 230 passed
- 2026-10-03 · F12 · green · login_anonymous (ANONYMOUS_AUTH, ANONYMOUS_TTL_DAYS=365), resolve_place (name ≤50 m = same place, shared _find_place with OSM import), routers, contract, docs, demo.http; 229 passed
- 2026-10-03 · F12 · red · tests: anonymous identity, resolve, two-device HTTP flow
- 2026-10-03 · F11 · green · DB_ENGINE/POSTGRES_* config, db_url, SqlRepo retry, Dockerfile, .dockerignore, compose; compose config valid; PG run pending
- 2026-10-03 · F11 · red · config/compose/PG-parametrized repo tests
- 2026-10-03 · DOCS · docs/ (README, architecture, api, configuration, operations, openapi.json) + export script + docs tests; 198 passed
- 2026-10-03 · F10 · live · key in .env (gitignored), model gemini-3.8-flash, retry 429/5xx, prompt vocab, physical/mobility → critical; 192 passed
- 2026-10-03 · F10 · done · Gemini REST adapter (httpx, key in header), config GEMINI_*, fallback to mock; 188 passed
- 2026-10-03 · F10 · red · Gemini adapter tests (MockTransport)
- 2026-10-03 · F9 · done · SQLite + SQLAlchemy write-behind SqlRepo, commit middleware, REPO_MODE/DATABASE_URL, .env.example synced with config.py; 179 passed
- 2026-10-03 · F9 · red · plan, SqlRepo + persistence tests
- 2026-10-03 · F8 · done · OSM import (file, idempotent, 50 m match), open_data 0.6, MCP client tools via Open API; 170 passed
- 2026-10-03 · F8 · red · plan, contract, OSM mapping/import/MCP tool tests
- 2026-10-03 · F7 · done · owner role, verified_owner 0.85, owner panel endpoints, admin assigns owner; fixed seed shared-state bug; 150 passed
- 2026-10-03 · F7 · red · plan, contract, owner tests
- 2026-10-03 · F6 · done · AI image tags: mock + Phi-3.5 ONNX adapter + fallback, e2e AI step + 2×400; 126 passed
- 2026-10-03 · F6 · red · plan, contract, tests (suggestions, onnx parsing, use case, fallback)
- 2026-10-03 · F5 · done · Open API /public/v1 (X-Api-Key, 60/min, flat format), e2e in demo.http; 106 passed
- 2026-10-03 · F5 · red · plan, contract, tests for Open API
- 2026-10-03 · MVP · done · contract test (20 ops × 4 specs), live uvicorn smoke OK; 92 passed
- 2026-10-03 · F1 · done · Google Sign-In (verifier port + adapter), logout, /me, demo/google mode switch; 67 passed
- 2026-10-03 · F4 · done · queue, detail, decision confirm/reject; test_demo_flow fully green; 58 passed
- 2026-10-03 · F3 · done · trust, validation, reports, uploads, observations, votes; 48 passed, 2 xfail
- 2026-10-03 · F2 · done · check rules, search/details/accessibility/check endpoints; 16 passed, 4 xfail
- 2026-10-03 · F0 · done · skeleton, seed, demo auth, reset; 1 passed, 7 xfail · `2c032f2`
