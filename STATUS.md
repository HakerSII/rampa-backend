# STATUS — rampa-backend MVP

> **Read first.** After every step (🔴 red / 🟢 green / 🔵 refactor / task done): update this file + local commit. Push when online.
> Plan: [README.md](README.md) · features: [features/](features/)

## Current

- **State:** todo
- **Deploy:** `master` is deployed on **Render**; front end (`static/api.js`) in progress on branch `Yannie-draft-acihy`
- **Last pytest:** `uv run pytest` → red: F24
- **e2e:** `requests/demo.http` — all statuses as expected (memory + SQLite)
- **Docs:** `docs/` (architecture, api, configuration, operations, PITCH, DEMO, openapi.json)
- **Branch:** `feat/mvp-backend` (merged with `master`, PR to `master` open)
- **Next for the map front end (from F12b):** `GET /observations?active=true&bbox=` with place location + report severity (one request instead of per-place reads); `FeatureKey`s for `escalator`, `tactile`, `sign` — or drop them from the front end

## Run

```
uv sync
uv run pytest
uv run python main.py                 # http://localhost:8000/docs
docker compose up -d --build          # Postgres + API (API_PORT=8001 if 8000 is taken)
```

## Blockers / open items (need a human or a decision)

- F1.0: Google Cloud OAuth "Web" client + `GOOGLE_CLIENT_ID` in `.env` (demo mode works without it).
- F1.5: frontend (mockups) — not in this repo.
- Gemini key: free tier exhausted during tests on 2026-10-03 (fixed: tests no longer read `.env`); check quota before the demo or keep `AI_MODE=mock`.
- Postgres: migrations of F13–F23 (new columns/table) verified on SQLite and on a copy of the real DB; re-run `docker compose up -d --build` + `TEST_POSTGRES_URL=… uv run --extra postgres pytest tests/adapters` to verify on Postgres.
- Push `feat/mvp-backend` + PR to `master` (on request).

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
| F11.1–F11.5 | Postgres + docker-compose, DB choice via env/config | Claude | done | verified on PG in docker |
| F12.1–F12.3 | Place screen: activity feed, photos, verification label | Claude | done | e2e 7d–7f + 400 |
| F13.1–F13.2 | Admin panel: stats tiles + audit history (+ column migration) | Claude | done | migration verified on SQLite + copy of real rampa.db; PG run pending (containers stopped) |
| F14.1–F14.2 | +8 features, +6 needs profiles (generic check rules) | Claude | done | e2e 3b–3f + 400 |
| F15 | Pitch + stage demo script | Claude | done | docs/PITCH.md, docs/DEMO.md |
| F16 | Me: favourites + my reports | Claude | done | e2e 4b-ME/FAV + 404/401 |
| F17 | Geo search (near/radius/bbox/sort/pages/map), categories, geocode | Claude | done | e2e 1b–1e + 400 |
| F18 | Report drafts (draft → PATCH → submit) | Claude | done | e2e D1–D3 + 409 |
| F19 | AI parse-text (rules) | Claude | done | e2e 4a-TXT + 400 |
| F20 | Similar places + accessible route (heuristic) | Claude | done | e2e 1f–1h + 404 |
| F21 | Admin extras: confidence, comments, flag, merge, revalidate, ownership requests | Claude | done | e2e 7j–7q + 409 |
| F22 | Owner panel extras (profile, stats, edit, hours, photos, reply/approve, reminders, suggestions, batch, CSV) | Claude | done | e2e O9a–O9k + 400 |
| F23 | Domain gaps: partial state, trust ageing, valid_until, place_type | Claude | done | e2e 1i–1k + 2×400; OSM import now 11 places |
| F12b | Front-end bridge: `POST /auth/anonymous`, `POST /places/resolve` (Adrian, on `master`) | Claude | done | `85a358e`; contract + demo.http B1–B7 |
| F24 | Map observations: `GET /observations?active&bbox` (front-end request) | Claude | red | |

## Log (newest first)

- 2026-10-03 · F24 red: map observations tests
- 2026-10-03 · MERGE · `master` (F12b front-end bridge) merged into `feat/mvp-backend`; conflicts resolved keeping both sides
- 2026-10-03 · DOCS · final docs + STATUS pass for F16–F23 (README, architecture, api, PITCH, DEMO, docs index)
- 2026-10-03 · F23 · done · partial state, trust ageing 180 d, valid_until with lazy refresh, place_type filter
- 2026-10-03 · F23 red: domain gaps tests
- 2026-10-03 · F22 · done · owner profile/stats/edit/hours/photos/reply/approve/reminders/suggestions/batch/CSV
- 2026-10-03 · F22 red: owner extras tests
- 2026-10-03 · F21 · done · confidence, comments, FLAGGED + abuse tile, merge, revalidate, ownership requests
- 2026-10-03 · F21 · red · admin extras tests
- 2026-10-03 · F20 · done · similar places, accessible route heuristic (straight line + street-level barriers ≤100 m)
- 2026-10-03 · F20 · red · similar + route heuristic tests
- 2026-10-03 · F19 · done · parse-text rules (PL+EN), endpoint, docs
- 2026-10-03 · F19 · red · parse-text rule tests
- 2026-10-03 · F18 · done · drafts: POST draft, PATCH, submit; nullable report fields in SQL
- 2026-10-03 · F18 · red · drafts tests
- 2026-10-03 · F17 · done · near/radius/bbox/sort/pages/map markers, /categories, /geocode (local)
- 2026-10-03 · F17 · red · geo search tests
- 2026-10-03 · F16 · done · favourites (JSON column, auto-migrated), my reports
- 2026-10-03 · F16 · red · me/favorites/reports tests
- 2026-10-03 · F15 · done · docs/PITCH.md (pitch, evidence, Q&A), docs/DEMO.md (stage script, pre-flight, fallbacks)
- 2026-10-03 · F14 · done · 13 features / 7 groups, 7 needs profiles via rule table, seed extras, AI keywords, specs+docs updated
- 2026-10-03 · F14 · red · profile rule tests, seeded answers, public check
- 2026-10-03 · F13 · done · /admin/stats tiles, /places/{id}/history, QueueItem.resolved_at, SqlRepo adds missing columns
- 2026-10-03 · F13 · red · stats/history/migration tests
- 2026-10-03 · F12 · done · activity feed, gallery, verification badge; FIX: tests no longer read .env (had called real Gemini, burned free quota 20/day)
- 2026-10-03 · F12 · red · verification + activity + photos tests
- 2026-10-03 · F11 · done · Postgres verified in docker (port 8001, local main.py on 8000); Gemini key hit 429 quota → mock fallback OK; docs updated
- 2026-10-03 · F12b · done · committed + pushed `85a358e` (master); front end: `static/api.js` adapter (local SQLite | Rampa via `GET /api/config`), type/severity mapping, `bp.token`, resolve → report, votes on `observation_ids[0]`
- 2026-10-03 · F12b · live · two-device flow verified over HTTP (uvicorn :8002); fix: Starlette 400 (undecodable body) mapped to NOT_A_REAL_PLACE instead of VALIDATION_ERROR; 230 passed
- 2026-10-03 · F12b · green · login_anonymous (ANONYMOUS_AUTH, ANONYMOUS_TTL_DAYS=365), resolve_place (name ≤50 m = same place, shared _find_place with OSM import), routers, contract, docs, demo.http; 229 passed
- 2026-10-03 · F12b · red · tests: anonymous identity, resolve, two-device HTTP flow
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
