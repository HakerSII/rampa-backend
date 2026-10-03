# Configuration

All settings live in `app/config.py` (`Settings`, pydantic-settings). They are read from **environment variables** or a **`.env`** file in the repo root (case-insensitive). The template is [`../.env.example`](../.env.example); copy it to `.env`. `.env` is gitignored, so **secrets go only there**.

## Settings

| Variable | Default | Values / meaning |
|---|---|---|
| **Storage** | | |
| `REPO_MODE` | `sql` | `sql` = SQLite via SQLAlchemy, survives restart · `memory` = in-process, lost on restart (tests use this) |
| `DATABASE_URL` | `sqlite:///data/rampa.db` | SQLAlchemy URL; the SQLite file and its folder are created automatically |
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
| `OSM_FILE` | `data/osm_krakow_tauron.json` | snapshot used by `POST /admin/imports {"source":"osm_file"}` |
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

Check the active modes with `GET /health` (`auth_mode`, `ai_mode`, `storage`).

## Optional dependency groups

| Extra | Installs | Needed for |
|---|---|---|
| `ai` | `onnxruntime-genai` | `AI_MODE=onnx` |
| `mcp` | `fastmcp` | `clients/mcp_server.py` |

Usage: `uv sync --extra ai`, or `uv run --extra mcp …`. A plain `uv run` syncs the default set and **removes** extras, so keep `--extra` on commands that need them.
