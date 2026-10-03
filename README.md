# rampa-backend — Kraków bez barier (backend)

> **Documentation:** [docs/](docs/README.md) — [architecture](docs/architecture.md) · [API reference](docs/api.md) · [configuration](docs/configuration.md) · [operations](docs/operations.md) · [pitch](docs/PITCH.md) · [demo script](docs/DEMO.md) · [openapi.json](docs/openapi.json)

Full contract: [../openapi.yaml](../openapi.yaml) · full plan: [../plan_fastapi.md](../plan_fastapi.md) · API notes: [../api.md](../api.md) · status: [STATUS.md](STATUS.md)

- Status: **full plan implemented** (F0–F23): 63/64 operations of the full contract (`/auth/login` replaced by `/auth/demo` + `/auth/google`), 69 HTTP operations, 389 tests.
- Per feature: `plan.md` (scope, model, tasks, DoD) + `openapi.yaml`.
- Each `openapi.yaml` = valid **subset** of full contract: same paths (`/api/v1/...`), schema names, enum values. Merge back = copy, no renames.
- Rules from full plan apply: **TDD** for domain + use cases ([§1a](../plan_fastapi.md)), **save status between steps + local commit** ([§1b](../plan_fastapi.md)).
- Task ids `F<feature>.<n>`. Track them in [STATUS.md](STATUS.md) instead of full-plan T* ids.

## Run

```
uv sync                                                        # once, online
uv run pytest                                                  # 92 tests, ~2 s, offline
uv run python main.py                                          # http://localhost:8000/docs
```

- E2E by hand: open `requests/demo.http` (VS Code REST Client) → "Send Request" top → bottom.
- AI: `POST /api/v1/ai/image-tags {"photo_ids": [...]}` — `AI_MODE=mock` (default) | `onnx` (`uv sync --extra ai`, model in `models/`) | `gemini` (`GEMINI_API_KEY` in `.env`, `GEMINI_MODEL`); any failure → mock.
- OSM import: `POST /api/v1/admin/imports {"source": "osm_file"}` (admin) → Tauron Arena stops etc.
- MCP (Claude): backend running → `.mcp.json` server `rampa` (`uv run --extra mcp python -m clients.mcp_server`); tools `check_accessibility`, `search_accessible_places`.
- Open API: `GET /public/v1/places` with header `X-Api-Key: demo-key`.
- Storage: `REPO_MODE=sql|memory`, `DB_ENGINE=sqlite|postgres` (+ `POSTGRES_*`); config in `.env` (see `.env.example`).
- Docker: `docker compose up -d --build` → Postgres + API on :8000 (`API_PORT=8001` if taken).
- **Deploy: Render**, automatic after every merge to `master` (Docker service `rampa-backend` + Render Postgres); see [docs/operations.md](docs/operations.md#render-production-deploy).
- Demo login: `POST /api/v1/auth/demo {"username": "anna"}` → use `Authorization: Bearer demo-anna`.
- Reset: `POST /api/v1/admin/demo/reset` with `Bearer demo-admin`.
- Google mode: `.env` → `AUTH_MODE=google`, `GOOGLE_CLIENT_ID=…`, `ADMIN_EMAILS=…` (see `.env.example`).
- Fixed time on stage: `DEMO_NOW=2026-10-03T12:00:00+02:00`.

## Offline / deterministic demo

- Data, trust, queue: in-memory, **no network**. AI, OSM, geocoding: cut (not mocked).
- Auth: `AUTH_MODE=google|demo`.
  - `google`: real Google Sign-In, needs internet.
  - `demo`: **default for demo + tests**. `POST /api/v1/auth/demo` with seeded account, offline.
- Why demo mode: scenario needs 6 distinct users (reporter, 3 voters, 2nd user, admin). Live Google account switching = slow + fragile. Details: [features/01-auth/plan.md](features/01-auth/plan.md).

## Order

| # | Feature | Plan | Contract | Time |
|---|---|---|---|---|
| 0 | Skeleton (model, repo, app, seed, reset, demo test `xfail`) | [plan](features/00-skeleton/plan.md) | — | 45–60 min |
| 1 | Auth (demo + Google Sign-In) | [plan](features/01-auth/plan.md) | [openapi](features/01-auth/openapi.yaml) | 45–75 min |
| 2 | Places + search + check | [plan](features/02-places-search/plan.md) | [openapi](features/02-places-search/openapi.yaml) | 60–90 min |
| 3 | Observations, votes, trust (core) | [plan](features/03-observations-trust/plan.md) | [openapi](features/03-observations-trust/openapi.yaml) | 90–120 min |
| 4 | Moderation queue (admin) | [plan](features/04-admin-queue/plan.md) | [openapi](features/04-admin-queue/openapi.yaml) | 45–60 min |
| 5 | Open API (`/public/v1`, X-Api-Key, rate limit) | [plan](features/05-open-api/plan.md) | [openapi](features/05-open-api/openapi.yaml) | 45 min |
| 6 | AI photo suggestions (mock / Phi-3.5 ONNX + fallback) | [plan](features/06-ai-image-tags/plan.md) | [openapi](features/06-ai-image-tags/openapi.yaml) | 60 min |
| 7 | Owner role + verified_owner observations | [plan](features/07-owner/plan.md) | [openapi](features/07-owner/openapi.yaml) | 60 min |
| 8 | OSM import (offline snapshot) + MCP client of Open API | [plan](features/08-osm-mcp/plan.md) | [openapi](features/08-osm-mcp/openapi.yaml) | 75 min |
| 9 | Persistence: SQLite + SQLAlchemy (`REPO_MODE`, `DATABASE_URL`) | [plan](features/09-sqlite/plan.md) | — | 90 min |
| 10 | Gemini vision (`AI_MODE=gemini`, `GEMINI_*` config) | [plan](features/10-gemini-vision/plan.md) | F6 | 45 min |
| 11 | Postgres + docker-compose (`DB_ENGINE`, `POSTGRES_*`) | [plan](features/11-postgres-docker/plan.md) | — | 60 min |
| 12 | Place screen: activity feed, photos, verification badge | [plan](features/12-place-screen/plan.md) | [openapi](features/12-place-screen/openapi.yaml) | 60 min |
| 13 | Admin panel: stats tiles + audit history | [plan](features/13-admin-panel/plan.md) | [openapi](features/13-admin-panel/openapi.yaml) | 60 min |
| 14 | +8 features, +6 needs profiles (generic check rules) | [plan](features/14-profiles/plan.md) | F2 specs updated | 60 min |
| 16 | Me: favourites + my reports | [plan](features/16-me/plan.md) | [openapi](features/16-me/openapi.yaml) | 30 min |
| 17 | Geo search (near/radius/bbox/sort/pages/map), categories, geocode | [plan](features/17-geo-search/plan.md) | [openapi](features/17-geo-search/openapi.yaml) | 60 min |
| 18 | Report drafts (draft → PATCH → submit) | [plan](features/18-report-drafts/plan.md) | [openapi](features/18-report-drafts/openapi.yaml) | 45 min |
| 19 | AI parse-text (rules, PL + EN) | [plan](features/19-parse-text/plan.md) | [openapi](features/19-parse-text/openapi.yaml) | 30 min |
| 20 | Similar places + accessible route A→B (heuristic) | [plan](features/20-similar-routes/plan.md) | [openapi](features/20-similar-routes/openapi.yaml) | 60 min |
| 21 | Admin extras: confidence, comments, flag abuse, merge, revalidate, ownership requests | [plan](features/21-admin-extras/plan.md) | [openapi](features/21-admin-extras/openapi.yaml) | 90 min |
| 22 | Owner panel extras: profile, stats, edit, hours, photos, reply/approve, reminders, suggestions, batch, CSV | [plan](features/22-owner-extras/plan.md) | [openapi](features/22-owner-extras/openapi.yaml) | 120 min |
| 24 | Map layer: `GET /observations?active&bbox&value&current` (front-end request) | [plan](features/24-map-observations/plan.md) | [openapi](features/24-map-observations/openapi.yaml) | 45 min |
| 25 | Full feature model: 35 features (+ `escalator`), group `parking` | [plan](features/25-features-full/plan.md) | specs updated | 30 min |
| 26 | Escalate + user abuse reports (typed moderation queue) | [plan](features/26-escalate-abuse/plan.md) | [openapi](features/26-escalate-abuse/openapi.yaml) | 45 min |
| 27 | Live OSM: Nominatim geocoder (`GEOCODER=nominatim`), Overpass import `{"source":"overpass"}`; fallback to local / snapshot | [plan](features/27-live-geo/plan.md) | endpoints unchanged | 45 min |
| 28 | Walking route from OSRM (`ROUTER=osrm`), barriers along the real path; fallback straight line | [plan](features/28-osrm-route/plan.md) | `engine` field added | 45 min |
| 29 | Multi-worker consistency: `meta.data_version`, reload when stale, 409 on concurrent write | [plan](features/29-multi-worker/plan.md) | 409 on any write | 45 min |
| 30 | AI recommendations `POST /ai/recommend` (rules / Claude tool call; facts only from DB) | [plan](features/30-ai-recommend/plan.md) | [openapi](features/30-ai-recommend/openapi.yaml) | 2 h |
| 31 | Needs profile on the server `/me/profile` + `GET /places?sort=best_match` | [plan](features/31-needs-profile/plan.md) | [openapi](features/31-needs-profile/openapi.yaml) | 1.5 h |
| 32 | Value `not_applicable` + `baby_changing_table`, `stroller_space`, `rest_areas`, `luggage_storage`; OSM `changing_table`, `dog` | [plan](features/32-not-applicable/plan.md) | specs updated | 1 h |
| 33 | Passwordless e-mail login `/auth/email/request` + `/verify` (console / SMTP mailer) | [plan](features/33-email-login/plan.md) | [openapi](features/33-email-login/openapi.yaml) | 1.5 h |
| 12b | Front-end bridge: `POST /auth/anonymous`, `POST /places/resolve` | [plan](features/12-frontend-bridge/plan.md) | [openapi](features/12-frontend-bridge/openapi.yaml) | 45 min |

- F0 blocks all.
- After F0: **F1, F2, F3 in parallel** (demo auth stub ships in F0, Google added in F1).
- F4 needs F3.

---

## 1. Demo scenario (trimmed, end-to-end)

Seeded accounts (`demo` mode): `anna` (reporter), `jan`, `ola`, `piotr` (voters), `marek` (2nd user), `ewa` (owner of `plc_mnk`, `plc_camelot`), `admin`.
Place `plc_mnk` (National Museum), feature `elevator`, seeded `yes` (observation 60 days old).

1. Search step-free places → `GET /places?features=step_free_entrance` (F2)
2. Open details → `GET /places/plc_mnk`, `GET /places/plc_mnk/accessibility` (F2)
3. "Can I get in by wheelchair?" → `GET /places/plc_mnk/check?profile=wheelchair` → `yes` (F2)
4. `anna`: "elevator broken" + photo → `POST /uploads`, `POST /reports` → `elevator: no`, `temporary` (F3)
5. `jan`, `ola`, `piotr` confirm → `POST /observations/{id}/votes` ×3 → confidence 0.9; `check` → `partial` (F3)
6. `marek`: "elevator works" → `POST /places/plc_mnk/observations` → conflict → `GET /admin/queue?filter=conflict` (F3 → F4)
7. `admin` confirms marek's observation → `POST /admin/queue/{id}/decision` → `elevator: yes`, confidence 1.0, `check` → `yes` (F4)

- Reset to pre-step-1: `POST /admin/demo/reset` (F0).
- = core of [api.md §10](../api.md); 2nd user replaces owner.

---

## 2. Differences from the full plan (still deliberate)

Everything from the full contract is implemented except the items below, which are deliberately simplified:

| Item | Status / replacement |
|---|---|
| `POST /auth/login` (username + password) | replaced by `POST /auth/demo` (demo mode) + `POST /auth/google` (Google Sign-In) |
| Live Overpass import, Nominatim geocoding | done (F27), opt-in: `GEOCODER=nominatim`, import `{"source":"overpass"}`; default offline (snapshot, local index) with fallback |
| Routing engine | OSRM walking path with `ROUTER=osrm` (F28); default straight-line heuristic (offline), also the fallback; `engine` + `note` say which |
| Abuse reports by users | done (F26): `POST /observations/{id}/abuse` → queue type `abuse` |
| `action=escalate` | done (F26): `status: escalated`, decidable later |
| Persistence | write-behind cache over SQLite/Postgres (F9/F11); several workers via data version + reload + 409 on a write race (F29). Not for high write throughput |
| DDD aggregate + domain events + UoW | light hexagon: logic in pure domain functions + use cases; conflicts create queue items directly |
| Features | 39 (full model + `escalator` + 4 from the Accessly description, F32), value `not_applicable`; `partially_inaccessible_exhibition` left out (inverted meaning) |
| Media storage | local `media/` folder (S3 later) |
| Frontend | not in this repo (mockups in the hackathon PDF) |

---

## 3. Architecture

Full description: **[docs/architecture.md](docs/architecture.md)**. In short:

```
app/
  domain/          pure rules: model, enums, trust, validation, check, suggestions, text_parse, osm, geo,
                   verification, history, stats, route, errors
  application/     ports.py (Repo, Clock, IdGenerator, FileStorage, IdentityVerifier, VisionAnalyzer, OsmSource, Geocoder, WalkingRouter)
                   use_cases.py (all use cases)
  adapters/
    inbound/http/  FastAPI app, middleware (commit), auth deps, errors, schemas, rate limit,
                   routers: auth, me, places, observations, ai, owner, admin, public
    outbound/      memory, sql (SQLite/Postgres), files, google_auth, vision_mock/onnx/gemini, osm_file, osm_live (Nominatim/Overpass), osrm
  bootstrap.py     composition root (config → adapters)
clients/           MCP server (client of the Open API)
tests/             unit · application · adapters · api (contract, demo flow, docs)
```

Dependency rule: `domain` imports only the standard library; frameworks live only in adapters and `bootstrap.py`.

---

## 4. Data model

See **[docs/architecture.md §4](docs/architecture.md#4-domain-model)**. Key rule: everything is an **observation** (source, author, time, evidence, votes, validation, optional `valid_until`); the feature state (`yes/partial/no/unknown` + confidence) is **always computed**, never written by hand.

---

## 5. Definition of Done (whole MVP)

- `test_demo_flow.py` green: scenario §1 end-to-end (`AUTH_MODE=demo`, `FixedClock`).
- `test_trust.py`, `test_validation.py`, `test_check.py` green. Cover: no-conflict observation, two contradicting values, old observation outside window, votes → confidence, 4 `check` answers.
- `POST /admin/demo/reset` (or restart) → demo repeatable, identical numbers.
- **Fully offline** with defaults (`AUTH_MODE=demo`, `AI_MODE=mock`, `GEOCODER=local`, `ROUTER=straight`). Network code is opt-in and falls back: Google Sign-In (F1), Gemini (F10), Nominatim/Overpass (F27), OSRM (F28). Overpass import runs only on explicit admin request.
- Every `features/*/openapi.yaml` passes `openapi-spec-validator`.
- **Every feature adds e2e calls to `requests/demo.http`** (happy path + error statuses in titles), verified by running the file top → bottom.
- [STATUS.md](STATUS.md) current; local commit per task.

## 6. Next

1. Frontend from the mockups (map, place card, report form, owner and admin panels) against this API.
2. Google OAuth client (F1.0) → real logins; fresh Gemini quota or a paid key before the demo.
3. Fully SQL-backed repository (per-row writes instead of whole-cache reload) for high write load; PostGIS for geo search.
4. City open data (BIP, ZTP) as further `open_data` sources; caching for Nominatim/OSRM answers.
5. Accessibility rules for the 22 informational features (today only some take part in `check`).
