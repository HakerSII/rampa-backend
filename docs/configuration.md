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
| **OSM** | | |
| `OSM_FILE` | `data/osm_krakow_tauron.json` | snapshot used by `POST /admin/imports {"source":"osm_file"}` and as the Overpass fallback |
| `GEOCODER` | `local` | `local` = place index only (offline, deterministic) · `nominatim` = local places first, then Nominatim hits in Kraków; failure → local |
| `NOMINATIM_URL` | `https://nominatim.openstreetmap.org/search` | Nominatim search endpoint |
| `OVERPASS_URL` | `https://overpass-api.de/api/interpreter` | used by `POST /admin/imports {"source":"overpass"}`; failure / empty → `OSM_FILE` |
| `OSM_CENTER_LAT`, `OSM_CENTER_LON`, `OSM_RADIUS_M` | `50.0647`, `19.945`, `1500` | Overpass search area (Rynek Główny) |
| `EMAIL_LOGIN` | `true` | `POST /auth/email/request` + `/verify` (any `AUTH_MODE`) |
| `MAILER` | `console` | `console` = mail written to the log (with `AUTH_MODE=demo` the code is also returned as `dev_token`) · `smtp` = real e-mail |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | —, `587`, —, — | SMTP server (STARTTLS); **password is a secret** |
| `MAIL_FROM` | `noreply@rampa.local` | sender address |
| `EMAIL_LINK_URL` | — | front-end page taking `?token=`; empty → the mail contains only the code |
| `AI_RECOMMENDER` | `rules` | `POST /ai/recommend` interpreter: `rules` (offline, PL+EN keywords) · `claude` (Claude API, forced tool call; facts never from the model). Failure → rules |
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
| `GEMINI_API_KEY` | — | **secret**; from https://aistudio.google.com/apikey, sent as the `x-goog-api-key` header |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model name (Google retired `gemini-2.5-flash` for new users) |
| `GEMINI_API_URL` | `https://generativelanguage.googleapis.com/v1beta` | API base URL |

**MCP client** (`clients/mcp_server.py`, separate process; its env comes from `.mcp.json`):

| Variable | Default | Meaning |
|---|---|---|
| `RAMPA_API_URL` | `http://localhost:8000` | backend base URL |
| `RAMPA_API_KEY` | `demo-key` | one of `PUBLIC_API_KEYS` |

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
