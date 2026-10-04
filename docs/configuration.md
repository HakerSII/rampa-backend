# Configuration

All settings live in `app/config.py` (`Settings`, pydantic-settings). They are read from **environment variables** or a **`.env`** file in the repo root (case-insensitive). The template is [`../.env.example`](../.env.example); copy it to `.env`. `.env` is gitignored, so **secrets go only there**.

## Settings

| Variable | Default | Values / meaning |
|---|---|---|
| **Storage** | | |
| `REPO_MODE` | `sql` | `sql` = database via SQLAlchemy, survives restart · `memory` = in-process, lost on restart (tests use this) |
| `DB_ENGINE` | `sqlite` | `sqlite` (file, zero setup) · `postgres` (server, e.g. docker compose) |
| `SQLITE_PATH` | `data/rampa.db` | SQLite file; it and its folder are created automatically |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `localhost` / `5432` | Postgres server (`db` inside docker compose) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `rampa` / `rampa` / `rampa` | credentials (password is URL-escaped); **set a real password in `.env`** outside local dev |
| `DATABASE_URL` | — | optional override: any SQLAlchemy URL, e.g. `postgresql+psycopg://u:p@h:5432/db`; wins over the settings above |
| **Auth** | | |
| `AUTH_MODE` | `demo` | `demo` = seeded accounts, `POST /auth/demo`, offline · `google` = Google Sign-In (`POST /auth/google`) |
| `GOOGLE_CLIENT_ID` | — | OAuth "Web" client id from Google Cloud Console (required for `google`) |
| `ADMIN_EMAILS` | — | comma list; these Google accounts get `admin` |
| `SESSION_TTL_HOURS` | `24` | Google session lifetime (demo tokens don't expire) |
| `ANONYMOUS_AUTH` | `true` | enables `POST /auth/anonymous` (identity per device for the map front end, any auth mode) |
| `ANONYMOUS_TTL_DAYS` | `365` | anonymous session lifetime; the device keeps its votes and reports this long |
| **Demo and files** | | |
| `MEDIA_DIR` | `media` | where uploaded photos are stored (served at `/media`) |
| `DEMO_NOW` | — | fixed "now" (ISO, e.g. `2026-10-03T12:00:00+02:00`) → deterministic times on stage |
| **Open API** | | |
| `PUBLIC_API_KEYS` | `demo-key` | comma list of valid `X-Api-Key` values |
| `PUBLIC_RATE_LIMIT_PER_MIN` | `60` | requests per minute per key (fixed window, in memory) |
| **Rate limits (F43)** | | 60 s window, in memory, per process; `0` = off; exceeded → `429` + `Retry-After` |
| `AI_RATE_LIMIT_PER_MIN` | `10` | `/api/v1/ai/*` per user (Bearer token; guests per IP) |
| `AI_RATE_LIMIT_PER_IP_PER_MIN` | `30` | `/api/v1/ai/*` per IP (caps many anonymous accounts from one machine) |
| `AUTH_RATE_LIMIT_PER_MIN` | `20` | login endpoints (`POST /auth/*` except logout) per IP |
| `TRUSTED_PROXY_HOPS` | `0` | `0` = socket IP (X-Forwarded-For ignored, cannot be spoofed) · **Render: `1`** = the address Render's proxy appended to X-Forwarded-For |
| **OSM** | | |
| `OSM_FILE` | `data/osm_krakow_tauron.json` | snapshot used by `POST /admin/imports {"source":"osm_file"}` and as the Overpass fallback |
| `GEOCODER` | `local` | `local` = place index only (offline, deterministic) · `nominatim` = local places first, then Nominatim hits in Kraków; failure → local |
| `NOMINATIM_URL` | `https://nominatim.openstreetmap.org/search` | Nominatim search endpoint |
| `OVERPASS_URL` | `https://overpass-api.de/api/interpreter` | used by `POST /admin/imports {"source":"overpass"}`; failure / empty → `OSM_FILE` |
| `CITY_CONFIG` | `data/cities/krakow.json` | city JSON (F37): name, `viewbox`, `center`, `osm_radius_m`, named `areas` with keywords, `category_groups` with categories + keywords. Invalid file → the app does not start |
| `OSM_CENTER_LAT`, `OSM_CENTER_LON`, `OSM_RADIUS_M` | from the city file | override the Overpass search area |
| `EMAIL_LOGIN` | `true` | `POST /auth/email/request` + `/verify` (any `AUTH_MODE`) |
| `MAILER` | `console` | `console` = mail written to the log (with `AUTH_MODE=demo` the code is also returned as `dev_token`) · `smtp` = real e-mail |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | —, `587`, —, — | SMTP server (STARTTLS); **password is a secret** |
| `MAIL_FROM` | `noreply@rampa.local` | sender address |
| `EMAIL_LINK_URL` | — | front-end page taking `?token=`; empty → the mail contains only the code |
| `AI_RECOMMENDER` | `rules` | `POST /ai/recommend` interpreter: `rules` (offline, PL+EN keywords) · `claude` (Claude API) · `gemini` (Gemini API, uses `GEMINI_API_KEY` / `GEMINI_MODEL`, shares the free quota with photos) · `onnx` (local Phi-3.5 from `AI_MODEL_PATH`, F47; schema values in the prompt; slow on CPU, waits up to `AI_TIMEOUT_S`). Claude/Gemini: forced tool call with one shared schema; facts never come from the model. Failure → rules |
| `ANTHROPIC_API_KEY` | — | **secret**; needed for `AI_RECOMMENDER=claude` |
| `CLAUDE_MODEL` | `claude-sonnet-5-5` | model for the recommender (compare with `claude-opus-5-5` on the test queries) |
| `ROUTER` | `straight` | `GET /routes/accessible` path: `straight` = straight-line heuristic (offline) · `osrm` = walking path from OSRM; failure → straight |
| `OSRM_URL` | `https://routing.openstreetmap.de/routed-foot` | OSRM server with a `foot` profile (FOSSGIS) |
| `EXTERNAL_TIMEOUT_S` | `10` | timeout for Nominatim (Overpass: at least 25 s) |
| `HTTP_USER_AGENT` | `RampaKrakowBezBarier/0.1 (HackYeah 2026)` | identifies the app to OSM services (usage policy) |
| **AI** | | |
| `AI_MODE` | `mock` | `mock` = deterministic, offline · `onnx` = Phi-3.5 Vision locally · `gemini` = Google Gemini API. Any failure → mock |
| `AI_TIMEOUT_S` | `60` | max time per model call before falling back to mock |
| `AI_MODEL_PATH` | `models/gpu/gpu-int4-rtn-block-32` | ONNX model folder (`onnx`); needs `uv sync --extra ai` |
| `AI_VISION_FALLBACK` | `mock` | `gemini` failed → `onnx` = try the local model (`AI_MODEL_PATH`) before mock; skipped with a warning when onnxruntime-genai or the model folder is missing |
| `AI_ONNX_TIMEOUT_S` | `180` | max time for the local fallback model (slow on CPU) |
| `AI_MODEL_DOWNLOAD` | `true` | F48: a setting uses the local model (`AI_MODE=onnx`, `AI_VISION_FALLBACK=onnx`, `CHAT_MODE=onnx`, `AI_RECOMMENDER=onnx`) and `AI_MODEL_PATH` is missing → downloaded at start from Hugging Face (~2.6 GB, resumable), then loaded; state in `GET /health` → `local_model` |
| `AI_MODEL_REPO` | `microsoft/Phi-3.5-vision-instruct-onnx` | Hugging Face repo of the model |
| `AI_MODEL_SUBFOLDER` | `gpu/gpu-int4-rtn-block-32` | folder in the repo; `AI_MODEL_PATH` must end with it |
| `AI_MODEL_MIN_RAM_MB` | `3500` | not loaded with less free memory (container limit or MemAvailable): state `error`, fallbacks answer — an out-of-memory kill would take the whole server down. `0` = no check |
| `CHAT_MODE` | `rules` | F46 chat: `rules` (keyword rules + template, no model) · `onnx` (local Phi-3.5) · `off` (503) |
| `CHAT_MODEL_PATH` | — | model folder for the chat; empty = `AI_MODEL_PATH` (one copy in memory, shared with photos and recommendations) |
| `CHAT_PRELOAD` | `false` | start loading the local model in the background when the server starts (chat and `AI_RECOMMENDER=onnx`) |
| `CHAT_TIMEOUT_S` | `120` | max time per chat model call → rules answer |
| `CHAT_MAX_NEW_TOKENS` | `160` | length limit of a chat answer |
| `GEMINI_API_KEY` | — | **secret**; from https://aistudio.google.com/apikey, sent as the `x-goog-api-key` header |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model name (Google retired `gemini-2.5-flash` for new users) |
| `GEMINI_API_URL` | `https://generativelanguage.googleapis.com/v1beta` | API base URL |

**MCP server** (`clients/mcp_server.py`, separate process with **its own env file `.mcpenv`** (template `.mcpenv.example`, gitignored); real env vars win: `.mcp.json`, compose, the Render service `rampa-mcp`; see [mcp.md](mcp.md)):

| Variable | Default | Meaning |
|---|---|---|
| `RAMPA_API_URL` | `http://localhost:8000` | backend base URL |
| `RAMPA_API_KEY` | `demo-key` | one of `PUBLIC_API_KEYS` (use a dedicated key in production) |
| `MCP_TRANSPORT` | `stdio` (`http` in `Dockerfile.mcp`) | `stdio` = local child process · `http` = Streamable HTTP at `/mcp` (F41) |
| `PORT` | `8080` | HTTP port (Render sets it) |
| `MCP_AUTH_TOKEN` | — | **secret**; when set, `/mcp` needs `Authorization: Bearer <token>`; empty for claude.ai connectors |

## Typical profiles

```ini
# Local Postgres (docker compose up -d db)
REPO_MODE=sql
DB_ENGINE=postgres
POSTGRES_HOST=localhost

# Stage demo (offline, repeatable)
REPO_MODE=sql
AUTH_MODE=demo
AI_MODE=mock          # or gemini if Wi-Fi is reliable
DEMO_NOW=2026-10-03T12:00:00+02:00

# Real AI on stage
AI_MODE=gemini
GEMINI_API_KEY=...    # only in .env
GEMINI_MODEL=gemini-3.8-flash

# Real users
AUTH_MODE=google
GOOGLE_CLIENT_ID=....apps.googleusercontent.com
ADMIN_EMAILS=lead@team.pl
```

Check the active modes with `GET /health` (`auth_mode`, `ai_mode`, `storage`, `database`). Empty values such as `DEMO_NOW=` mean "not set".

## Optional dependency groups

| Extra | Installs | Needed for |
|---|---|---|
| `ai` | `onnxruntime-genai` | `AI_MODE=onnx` |
| `mcp` | `fastmcp` | `clients/mcp_server.py` |
| `postgres` | `psycopg[binary]` | `DB_ENGINE=postgres` when running locally (the Docker image installs it) |

Usage: `uv sync --extra ai`, or `uv run --extra mcp …`. A plain `uv run` syncs the default set and **removes** extras, so keep `--extra` on commands that need them.
