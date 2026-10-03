# Stage demo script (≈ 3 min)

Every click and its expected result. Tool: VS Code + **REST Client** on [`../requests/demo.http`](../requests/demo.http), plus Swagger (`/docs`) as a backup screen.

## Before going on stage (T-15 min)

| Check | Command / action | Expected |
|---|---|---|
| Server running | `uv run python main.py` | `http://localhost:8000/docs` opens |
| Modes | `GET /health` | `auth_mode: demo`, `ai_mode: mock` (safe) or `gemini`, `storage: sql` |
| Clean data | `demo.http` step **0** (reset) | `204` |
| Fixed time (optional) | `.env`: `DEMO_NOW=2026-10-03T12:00:00+02:00`, restart | identical numbers on every run |
| Gemini quota | one call to step 4a-AI | `"model": "gemini"`; if `"mock"` → keep mock (the free tier is about 20 requests/day; a 429 in the log means quota) |
| MCP (optional) | Claude Code → `/mcp` → `rampa` connected (local stdio, or remote: `claude mcp add --transport http rampa https://<rampa-mcp>/mcp`); run step **I2** (OSM import) first | tool `check_accessibility` listed |
| Offline fallback | Wi-Fi off → everything except Gemini/Google still works | `AI_MODE=mock` |

## Script

| # | Say | Click (`demo.http`) | Expected on screen |
|---|---|---|---|
| 1 | "Anna uses a wheelchair and wants to visit the National Museum." | **1** search step-free | `plc_mnk`, `plc_ice` |
| 2 | "Every place shows how fresh and trustworthy its data is." | **2** place details | `verification.label`: "Zweryfikowane 60 dni temu", confidence 0.5 (seed data) |
| 3 | "Can she get in?" | **3** check wheelchair | `answer: yes` |
| 4 | "Not just wheelchairs: blind users, assistance dogs, deaf visitors." | **3b**, **3c**, **3e** | blind `yes`; dog `yes`; office low vision `no` + advice |
| 5 | "Today the elevator is broken. Anna takes a photo." | **4a** upload → **4a-AI** | tags *winda, awaria*; suggestion *elevator / not working / critical* |
| 6 | "One tap and the report is in." | **4b** report | elevator → `no`, temporary, confidence 0.6 |
| 7 | "Three neighbours confirm it." | **5a–5c** votes → **5d** check | confidence 0.9; answer `partial` ("Wejdziesz, ale winda nie działa…") |
| 8 | "Marek says it works. Who is right?" | **6a** → **6c** queue | `CONFLICT`, 1 item in the moderation queue |
| 9 | "A moderator checks and decides. Nothing is deleted." | **7a** decision → **7b** check | elevator `yes`, confidence 1.0; answer `yes` |
| 9b | "And the place card is fresh again." | **7f** place details, **7d** activity | "Potwierdzone dzisiaj"; feed: moderator decision, Marek, Anna's report |
| 10 | "Full history and an admin dashboard." | **7h** history, **7g** stats | events incl. REJECTED report; tiles |
| 11 | "The city and other apps get the same data." | **P3** Open API | flat JSON, `value: true/false` |
| 12 | (optional) "And your AI assistant knows it too." | Claude: *"Czy wjadę na wózku do Tauron Areny?"* | 3 Tauron Arena stops → `yes` (from OSM import) |

The owner variant (Ewa, verified owner says "repaired") is **O0–O9**, if the jury asks about owners.

## Extended demo (if time or the jury asks)

| Topic | Click (`demo.http`) | Expected |
|---|---|---|
| "Near me" + map | **1b**, **1c** | nearest first with `distance_m`; markers accessible / partial / inaccessible |
| Route for a wheelchair / blind person | **1g**, **1h** | `feasible: yes`, helpers (lowered kerb, tactile paths), honest `note` |
| AI from text | **4a-TXT** | "winda od dwóch tygodni nie działa" → elevator / no / temporary |
| Draft report ("Zapisz szkic") | **D1–D3** | draft → completed → submitted (observation created) |
| Favourites | **4b-FAV**, **4b-FAV2** | museum in favourites with its badge |
| Owner panel | **O9a–O9k** | stats, reply, opening hours, reminders, suggestions, batch, CSV import |
| Moderation extras | **7j–7q** | confidence widget, comment, spam flagged, ownership request approved |
| Temporary issue with end date | **1k** | `valid_until` → stops counting automatically |

## If something goes wrong

| Problem | Do |
|---|---|
| Numbers differ from the script | step **0** reset, continue from step 1 |
| `model: mock` instead of Gemini | say "offline fallback: the demo never depends on the network", and continue |
| Server is down | `uv run python main.py` (≈2 s); data is in SQLite, so nothing is lost |
| Port 8000 is taken | `uv run uvicorn main:app --port 8001` and change `@base`/`@public` in `demo.http` |
| Wi-Fi is down | `AI_MODE=mock` (default); the whole script except Gemini and MCP-in-cloud works offline |
| REST Client is not responding | Swagger `/docs`: Authorize `demo-anna` / `demo-admin`, same endpoints |
