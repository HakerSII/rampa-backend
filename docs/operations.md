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
| Data differs between two servers | SQLite mode is single-process (write-behind cache); run one uvicorn worker |
| `VIRTUAL_ENV … does not match` warning | another venv is active (e.g. the outer project's); `deactivate` or ignore |
