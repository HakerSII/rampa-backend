# Operations: run, test, demo, integrate

## 1. Run

```bash
uv sync                        # once (needs internet); creates .venv
cp .env.example .env           # optional; defaults work offline
uv run python main.py          # http://127.0.0.1:8000  (/ → /docs)
# or with reload while developing:
uv run uvicorn main:app --reload
```

- **First start:** the empty SQLite DB (`data/rampa.db`) is created and seeded with 4 places and 7 demo accounts.
- **Later starts:** the data is loaded and kept.
- **Back to the seed:** `POST /api/v1/admin/demo/reset` as `demo-admin`, or delete `data/rampa.db`.

### Docker (Postgres + API)

```bash
docker compose up -d --build          # db (postgres:17) + api → http://localhost:8000/docs + mcp → http://localhost:8080/mcp
API_PORT=8001 docker compose up -d    # if 8000 is taken (e.g. local main.py running)
docker compose logs -f api            # logs (AI fallbacks, DB retries)
docker compose down                   # stop (data kept in volume pgdata)
docker compose down -v                # stop + wipe Postgres data and media
```

- The API waits for a healthy Postgres, retries the connection, then seeds an empty database.
- Settings come from `.env` in this folder through compose interpolation (`AUTH_MODE`, `AI_MODE`, `GEMINI_*`, `POSTGRES_*`, …). `.env` is **not** copied into the image (`.dockerignore`).
- Only Postgres in Docker, app locally: `docker compose up -d db`, then in `.env` set `DB_ENGINE=postgres` and run `uv run --extra postgres python main.py`.
- The image has no ONNX model or GPU: use `AI_MODE=mock` or `gemini`.
- Several uvicorn workers can share one database since F29 (see [architecture.md §6](architecture.md#6-persistence-repo_mode)).

### Render (production deploy)

The backend is **deployed on Render** and **deploys automatically after every merge to `master`**.

| Render resource | What it is |
|---|---|
| `rampa-backend` | Web service, runtime **Docker** (this `Dockerfile`), region Ohio |
| `rampa-backend-postgres` | Render Postgres, connected through `DATABASE_URL` |
| `rampa-mcp` (F41, to be created) | Web service, runtime **Docker** (`Dockerfile.mcp`): public remote MCP at `/mcp`, health `/health`. Env: its own `.mcpenv` (template `.mcpenv.example`). Setup: [mcp.md §4](mcp.md#4-deploy-on-render-separate-service) |

- **Release flow:** feature branch → PR → merge into `master` → Render builds the image and deploys it, no manual step. Do not push unfinished work to `master`.
- **Configuration:** environment variables in the Render dashboard (service → Environment), same names as `.env.example`. Secrets (`GEMINI_API_KEY`, `DATABASE_URL`, `GOOGLE_CLIENT_ID`) live there only, never in git.
- **Database migrations:** automatic at start. New tables are created and missing columns added; the log shows `schema: added column …`. An empty database is seeded once.
- **After a deploy:** open `/health` on the service URL (shown in the Render dashboard). It should return `"storage": "sql", "database": "postgresql"`. Then run `requests/demo.http` against it with `@base` set to the service URL.
- **Rate limits on Render:** set `TRUSTED_PROXY_HOPS=1`, so limits count the real client IP rather than Render's proxy.
- **Live OSM on Render:** set `GEOCODER=nominatim` and `ROUTER=osrm` to use Nominatim and OSRM. The Overpass import (`{"source":"overpass"}`) runs only on admin request; every live service falls back to offline data.
- **Locally, never use the Render internal DB URL** (`dpg-…`): it only resolves inside Render, so a local start hangs on connection retries. Use `REPO_MODE=memory`, local SQLite or Docker.

## 2. Test

```bash
uv run pytest                  # whole suite, offline, ~5 s
uv run pytest tests/unit       # domain only, < 1 s
```

| Folder | What |
|---|---|
| `tests/unit` | pure domain: trust, validation, check, suggestions, OSM mapping, ONNX JSON parsing |
| `tests/application` | use cases on in-memory fakes (auth, places, observations, admin, owner, AI, import) |
| `tests/adapters` | `SqlRepo` round-trips on a temp SQLite file; Gemini adapter against `httpx.MockTransport` |
| `tests/api` | HTTP: full demo flow, Open API, persistence across restart, MCP tools via ASGI, **contract test** (every operation in `features/*/openapi.yaml` exists, specs valid), `docs/openapi.json` up to date |

SqlRepo tests on Postgres (they **drop the tables** of the target database, so use a separate DB):

```bash
docker compose exec -T db psql -U rampa -d rampa -c "CREATE DATABASE rampa_test"
TEST_POSTGRES_URL=postgresql+psycopg://rampa:rampa@localhost:5432/rampa_test uv run --extra postgres pytest tests/adapters
```

Tests force `REPO_MODE=memory` (set in `tests/conftest.py`) and never touch the network. Google, Gemini and Overpass are faked.

Workflow used in this repo:
- TDD per feature: a 🔴 commit with tests, then a 🟢 commit with the implementation.
- `STATUS.md` is updated after every step.
- Every feature adds requests to `requests/demo.http`.

## 3. Demo script (≈ 3 min)

Open [`../requests/demo.http`](../requests/demo.http) in VS Code (REST Client extension) and click **Send Request** from top to bottom:

| Step | What the audience sees |
|---|---|
| 0 | Reset |
| 1–3 | Search step-free places, details, "can I get in?" → **yes** |
| 4a → 4a-AI | Upload a photo; AI suggests "elevator / not working / critical" |
| 4b | Anna reports it → elevator **no**, temporary, confidence 0.6 |
| 5 | Three neighbours confirm 👍 → 0.9, check → **partial** |
| 6 | Marek contradicts → **conflict**, moderation queue |
| 7 | Admin confirms → elevator **yes**, confidence 1.0, history kept |
| O0–O9 | Same story with the **owner** (Ewa) instead of Marek |
| I1–I6 | OpenStreetMap import → Tauron Arena stops appear |
| P1–P5 | The same data through the **Open API** |

For the same timestamps on every run, set `DEMO_NOW` in `.env`.

## 4. AI models

| Mode | Setup | Notes |
|---|---|---|
| `mock` | nothing | deterministic by file name (`winda*` elevator, `schody*` stairs, `screenshot*` not a real place) |
| `gemini` | `.env`: `AI_MODE=gemini`, `GEMINI_API_KEY=…` | internet; ~3–10 s; retries 429/5xx ("high demand") 2× with 2 s/4 s backoff, then mock |
| `onnx` | `uv sync --extra ai`, model in `models/gpu/gpu-int4-rtn-block-32` (≈2.5 GB, gitignored), `AI_MODE=onnx` | local Phi-3.5 Vision; GPU recommended; first call loads the model |

The response field `model` tells you which model answered. If it says `mock` while you expected another model, the reason is in the server log (`vision model failed (…) → mock`).

## 5. MCP in Claude

1. Start the backend: `uv run python main.py`.
2. Make sure `.mcp.json` (in the workspace root) has the server:
   ```json
   "rampa": {
     "type": "stdio", "command": "uv",
     "args": ["run", "--directory", "<path>/sourcedoc/mvp", "--extra", "mcp", "python", "-m", "clients.mcp_server"],
     "env": { "RAMPA_API_URL": "http://localhost:8000", "RAMPA_API_KEY": "demo-key" }
   }
   ```
3. Restart Claude Code (or `/mcp`) and approve `rampa`.
4. Ask: *"Czy wjadę na wózku do Tauron Areny?"* (run the OSM import first, step I2).

Manual smoke test without Claude: send `initialize`, `tools/list` and `tools/call` JSON-RPC lines to `uv run --extra mcp python -m clients.mcp_server` on stdin.

**Remote MCP (F41):** `MCP_TRANSPORT=http PORT=8080 uv run --extra mcp python -m clients.mcp_server` → `http://localhost:8080/mcp`. Run [`requests/mcp.http`](../requests/mcp.http) against it. The Render deploy and the client setup for Claude Code, claude.ai, Gemini CLI and Grok are in [mcp.md](mcp.md).

## 6. Google Sign-In (production login)

1. Google Cloud Console → APIs & Services → Credentials → **OAuth client ID** → *Web application*.
2. Authorized JavaScript origins: the front-end origin (e.g. `http://localhost:5173`) and `http://localhost:8000`.
3. In `.env`: `AUTH_MODE=google`, `GOOGLE_CLIENT_ID=…`, `ADMIN_EMAILS=…`.
4. Front end: Google Identity Services "Sign in with Google" → send the `credential` (ID token) to `POST /api/v1/auth/google` → use the returned `token` as Bearer.

## 7. Export the OpenAPI spec

```bash
uv run python scripts/export_openapi.py     # writes docs/openapi.json
```
A test fails if `docs/openapi.json` is stale, so re-export after changing endpoints or schemas.

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `unknown demo user: daniel` | only seeded usernames work in demo mode (see [api.md](api.md#authentication)) |
| 404 on `/auth/demo` | `AUTH_MODE=google` is set |
| AI always returns `model: mock` | check the log: missing `GEMINI_API_KEY`, Gemini 503 "high demand" (retry later), wrong `GEMINI_MODEL`, ONNX extra not installed |
| Gemini 404 "no longer available" | change `GEMINI_MODEL` to the name the error message suggests |
| 429 on `/public/v1` | per-key limit; wait `Retry-After` s or raise `PUBLIC_RATE_LIMIT_PER_MIN` |
| Demo shows old data | SQLite keeps data: `POST /admin/demo/reset` or delete `data/rampa.db` |
| MCP tool says `API niedostępne` | the backend isn't running, or `RAMPA_API_URL`/`RAMPA_API_KEY` is wrong |
| MCP: `fastmcp` not found | run with `--extra mcp` (a plain `uv run` removes extras) |
| API container exits on start | `docker compose logs api` — wrong `POSTGRES_*`, or a bad value in `.env` |
| `port is already allocated` / wrong server answers on 8000 | another process uses 8000 → `API_PORT=8001 docker compose up -d` |
| Gemini 429 "exceeded your current quota" | the key's free quota is used up; fallback serves mock; wait or use another key/plan |
| Data differs between two servers | Both must use the same database (`DATABASE_URL`); since F29 each request reloads when another worker committed. Separate SQLite files per container never sync |
| `429 RATE_LIMITED` on `/ai/*` or login | Wait `Retry-After` seconds, or raise `AI_RATE_LIMIT_*` / `AUTH_RATE_LIMIT_PER_MIN` (`0` = off). Behind Render set `TRUSTED_PROXY_HOPS=1`, otherwise all users share the proxy's IP |
| `409 CONFLICT` "concurrent update by another worker" | Two workers wrote at the same moment; the later write was dropped. Retry the request |
| `VIRTUAL_ENV … does not match` warning | another venv is active (e.g. the outer project's); `deactivate` or ignore |
