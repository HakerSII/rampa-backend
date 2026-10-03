# Pitch — Kraków bez barier

> Speaker notes for a 90-second pitch plus a ~3-minute live demo. Facts below are taken from the implemented system; nothing is claimed that is not in the repo. The stage script is in [DEMO.md](DEMO.md).

## One-sentence opening

**A wheelchair user in Kraków can't tell whether today they will actually get in.** A map from last year said "accessible", but today the elevator is broken. *Kraków bez barier* is a "Yanosik for accessibility": people, owners and the city report what is true **now**, and the app answers *"Can I get in?"* with a confidence score.

## 90-second structure

1. **Problem (15 s).** Accessibility information is static and goes stale. A ramp that is blocked or snowed in, or an elevator that is out of order, makes a "wheelchair-accessible" label wrong *today*. The questions people actually ask: *Can I get in with a wheelchair? With crutches? With an assistance dog? Does the platform have a lift? Is it well lit?*
2. **Gap (10 s).** Existing maps store a yes/no flag with no source, no date and no way to say "it's broken right now". Nobody can tell how far to trust them.
3. **Solution (20 s).** We never store a flag. Every input is an **observation** with a source, date and photo:
   - users report;
   - neighbours confirm with 👍/👎;
   - the owner adds verified updates;
   - OpenStreetMap is imported.

   A **trust engine** computes the current state and its confidence. **Conflicts** (owner says "repaired", users say "broken") go to a moderator, and nothing is overwritten.
4. **Live demo (≈3 min, separate).** See [DEMO.md](DEMO.md).
5. **Why it's different (15 s).**
   - Answers for **7 needs profiles**, not one icon.
   - **AI suggestions from a photo** (Gemini / local Phi-3.5, offline fallback), which fill the report in seconds.
   - **Open API** for city apps and transport.
   - An **AI assistant (MCP)** that answers "can I get in?" from our live data, locally or as a public remote MCP server that Claude, Gemini or Grok can connect to.
6. **Next (10 s).** Real users in one district, the city's open data, the frontend from the mock-ups, a live OSM import, and more features from the full model (35).

## Evidence (only what exists)

| Claim | Evidence in the repo |
|---|---|
| End-to-end flow works | `requests/demo.http`: 129 requests, verified top to bottom (status per step); `tests/api/test_demo_flow.py` |
| Robust, tested | 389 automated tests (domain, use cases, adapters, HTTP, contract vs 23 feature specs, docs), run offline in ~10 s |
| Real AI on a real photo | Gemini on `main_image_wozek.jpg` → "stairs without ramp", affected *wheelchair, mobility*, confidence 0.98 → suggestion *step-free entrance / not working / critical* |
| Real open data | OSM snapshot (18 points around Tauron Arena) → 11 places imported (`wheelchair=limited` → partial); the MCP assistant answers "Tauron Arena stops: yes" |
| Production path | `docker compose up` → Postgres + API; the full demo flow verified on Postgres |
| API surface | 69 HTTP operations (65 internal + 4 public); 63 of 64 operations of the full contract (login replaced by demo + Google) |

**Not validated yet:** no user research or usage metrics. The data is demo seed plus an OSM snapshot. Say this openly if asked.

## Architecture slide (one diagram)

```
 People · Owners · City/OSM ─► Observation ─► Validation ─► Trust ─► State + confidence
                                  (photo, votes)   (conflicts → moderator)      │
                                                                                ├─► App (map, "Can I get in?")
                                                                                ├─► Open API (city, transport)
                                                                                └─► AI assistant (MCP)
```

Tech, only where it supports the value:
- FastAPI;
- a hexagonal core, so every external service has an offline twin and the demo never breaks;
- SQLite or Postgres;
- Gemini / Phi-3.5 for photos.

## Closing sentence

**"We don't publish another static map. We give Kraków a living, verifiable answer to *can I get in today?*, with a source, a date and a confidence level for every piece of information, open to every city app."**

## Q&A preparation

| Question | Answer |
|---|---|
| Why this problem? | Static data goes stale; a broken lift turns "accessible" into a wasted trip. The brief's own user questions (crutches, dog, platform lift, kerb, lighting) map 1:1 to our profiles. |
| Why this architecture? | Observations, then a computed state, give history, trust and conflicts for free. The hexagon gives every external service an offline twin (mock AI, OSM snapshot, demo login, SQLite), so the demo is deterministic. |
| What is actually implemented? | The whole backend of the plan: location search and map, check for 7 profiles, reports with photos and drafts, votes, trust with ageing, conflicts, moderation (decide, comment, flag, merge), the full owner panel (incl. CSV), ownership requests, OSM import, AI from photos (mock/Gemini/Phi) and from text, route heuristic, Open API, MCP, stats and audit, SQLite/Postgres, Docker. 389 tests. |
| What is mocked or simplified? | `AI_MODE=mock` (deterministic answers by file name), demo accounts instead of Google login (Google Sign-In is implemented, but no OAuth client is configured yet), OSM, geocoding and routing are offline by default (snapshot, local index, straight line); live Nominatim, Overpass and OSRM are opt-in by config and fall back automatically (Overpass is blocked on the corporate network, so the import falls back to the snapshot there). The frontend from the mock-ups is not built yet. |
| How would it scale? | The data model is small and per-place. Today SQLite/Postgres with a write-behind cache; several workers already share one database (data version + reload, 409 on a write race). Next: a fully SQL-backed repository behind the same port and PostGIS for geo search. |
| Data / privacy / security? | Public names are shortened ("Anna K."). Secrets live only in `.env` (gitignored, never in the Docker image). The Gemini key is sent in a header. The Open API is read-only with keys and a rate limit. Photos are checked by magic bytes and capped at 10 MB. AI never changes data; it only suggests. Moderation keeps a full audit trail. |
| Can people spam or lie? | One vote per user per observation, no voting on your own observation, a 30-day conflict window → moderator, an owner's word weighs more but never deletes users' reports, and the history is never deleted. |
| What next? | The frontend from the mock-ups, real OAuth, live OSM/city data, more features and the `partial` state, data ageing in the trust score, a "can I get from A to B" route. |
