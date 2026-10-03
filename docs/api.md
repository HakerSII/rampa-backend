# API reference

- **Interactive:** `http://localhost:8000/docs` (Swagger UI) and `/redoc`.
- **Machine-readable:** [openapi.json](openapi.json), or `GET /openapi.json` at runtime.
- **Clickable end-to-end requests:** [`../requests/demo.http`](../requests/demo.http).

All examples below are real responses from the app with demo data and a fixed clock (`2026-10-03T12:00Z`).

## 1. Conventions

| Item | Value |
|---|---|
| Internal API | `http://localhost:8000/api/v1` — the app's front end, owners, admins |
| Open API | `http://localhost:8000/public/v1` — external apps, read-only |
| Format | JSON, UTF-8; datetimes ISO 8601 with time zone |
| Lists in query | comma-separated: `?features=step_free_entrance,elevator` (AND) |
| Photos | `GET /media/{file}` (static) |
| Health | `GET /health` → `{"status":"ok","auth_mode":"demo","ai_mode":"mock","storage":"sql"}` |
| `/` | redirects to `/docs` |

### Authentication

| Area | Header | How to get it |
|---|---|---|
| `/api/v1` (users) | `Authorization: Bearer <token>` | `POST /auth/demo` (demo mode: token = `demo-<username>`) or `POST /auth/google` |
| `/public/v1` | `X-Api-Key: <key>` | keys in `PUBLIC_API_KEYS` (default `demo-key`) |

Read endpoints for places (`/places*`, `/accessibility/features`, `GET /places/{id}/observations`) work without a token (guest). Writes need a user; owner and admin endpoints need that role.

**Demo accounts:**

| username | role | notes |
|---|---|---|
| `anna` | user | reporter in the demo |
| `jan`, `ola`, `piotr` | user | voters |
| `marek` | user | contradicts → conflict |
| `ewa` | owner | owns `plc_mnk`, `plc_camelot` |
| `admin` | admin | moderation, imports, reset |

### Errors

Every error has the same shape:

```json
{ "error": { "code": "NOT_FOUND", "message": "place not found: nope" } }
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | bad body/query, unknown enum value, wrong photo ids, voting on own observation … (`details.errors` for schema errors) |
| 400 | `NOT_A_REAL_PLACE` | AI: no uploaded photo shows a real place |
| 401 | `UNAUTHORIZED` | no/invalid token or API key, bad Google token |
| 403 | `FORBIDDEN` | role missing (owner/admin), not the owner of this place, not the author of a report |
| 404 | `NOT_FOUND` | unknown place/observation/report/queue item; demo or Google login disabled in the current mode |
| 409 | `CONFLICT` | queue item already resolved |
| 413 | `FILE_TOO_LARGE` | photo > 10 MB |
| 429 | `RATE_LIMITED` | Open API limit exceeded; `Retry-After` header |

### Enums

| Name | Values |
|---|---|
| Feature | `step_free_entrance`, `ramp` · `elevator` · `accessible_toilet` · `induction_loop`, `sign_language_interpreter` · `braille`, `tactile_paths`, `good_lighting` · `lowered_curb`, `platform_elevator`, `crutches_friendly` · `assistance_dog_allowed` (13) |
| Feature group | `entrance`, `inside`, `toilet`, `hearing`, `vision`, `mobility`, `other` |
| Needs profile (`check`) | `wheelchair`, `stroller`, `crutches`, `blind`, `low_vision`, `deaf`, `assistance_dog` |
| State | `yes`, `no`, `unknown` |
| Observation value | `yes`, `no` |
| Source | `community` (0.5), `open_data` (0.6), `verified_owner` (0.85), `admin` (1.0) |
| Validation | `VALID`, `CONFLICT`, `REJECTED` |
| Check answer | `yes`, `partial`, `no`, `unknown` |
| Report `current_state` / `severity` / `nature` | `works·not_working` / `critical·obstacle·minor` / `permanent·temporary·unknown` |
| Role | `guest`, `user`, `owner`, `admin` |

## 2. Endpoint overview

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/auth/demo` | — | Demo login (demo mode) |
| POST | `/api/v1/auth/google` | — | Google Sign-In login (google mode) |
| POST | `/api/v1/auth/logout` | user | End session |
| GET | `/api/v1/me` | user | Current user |
| GET | `/api/v1/places` | — | Search places |
| GET | `/api/v1/places/{id}` | — | Place details |
| GET | `/api/v1/places/{id}/accessibility` | — | Computed accessibility, grouped |
| GET | `/api/v1/places/{id}/check` | — | "Can I get in?" |
| GET | `/api/v1/places/{id}/activity` | — | Feed: recent reports, confirmations, decisions |
| GET | `/api/v1/places/{id}/photos` | — | Photo gallery (evidence) |
| GET | `/api/v1/accessibility/features` | — | Feature dictionary (filters) |
| POST | `/api/v1/uploads` | user | Upload photo |
| POST | `/api/v1/ai/image-tags` | user | AI suggestions from photos |
| POST | `/api/v1/reports` | user | Report a change (→ observation) |
| GET | `/api/v1/reports/{id}` | author/admin | Report |
| GET | `/api/v1/places/{id}/observations` | — | Observations (alerts, history) |
| POST | `/api/v1/places/{id}/observations` | user | Quick observation |
| POST | `/api/v1/observations/{id}/votes` | user | Vote 👍/👎 |
| DELETE | `/api/v1/observations/{id}/votes/me` | user | Remove own vote |
| GET | `/api/v1/owner/places` | owner | My places |
| POST | `/api/v1/owner/places/{id}/observations` | owner of place | Batch update (verified owner) |
| GET | `/api/v1/owner/reports` | owner | Reports on my places |
| GET | `/api/v1/admin/queue` | admin | Moderation queue |
| GET | `/api/v1/admin/queue/{id}` | admin | Conflict detail |
| POST | `/api/v1/admin/queue/{id}/decision` | admin | Confirm / reject |
| POST | `/api/v1/admin/places/{id}/owner` | admin | Assign owner |
| GET | `/api/v1/admin/stats` | admin | Dashboard tiles |
| GET | `/api/v1/places/{id}/history` | admin / owner of place | Audit trail |
| POST | `/api/v1/admin/imports` | admin | OSM import |
| POST | `/api/v1/admin/demo/reset` | admin | Reset data to seed |
| GET | `/public/v1/places` | API key | Open API search |
| GET | `/public/v1/places/{id}` | API key | Open API place |
| GET | `/public/v1/places/{id}/accessibility` | API key | Open API flat accessibility |
| GET | `/public/v1/places/{id}/check` | API key | Open API "can I get in?" |
| GET | `/api/v1/me/favorites` | user | My favourite places |
| PUT | `/api/v1/me/favorites/{id}` | user | Add favourite (idempotent) |
| DELETE | `/api/v1/me/favorites/{id}` | user | Remove favourite (idempotent) |
| GET | `/api/v1/me/reports` | user | My reports, newest first |
| GET | `/api/v1/categories` | — | Categories with counts |
| GET | `/api/v1/geocode?q=` | — | Search-box suggestions (local index) |
| GET | `/health` | — | Status and active modes |

## 3. Auth

### `POST /api/v1/auth/demo`
Only in `AUTH_MODE=demo` (otherwise 404). Unknown username → 401.

```json
// request
{ "username": "anna" }
// 200
{ "token": "demo-anna",
  "user": { "id": "usr_anna", "display_name": "Anna Kowalska", "email": null, "role": "user" } }
```

### `POST /api/v1/auth/google`
Only in `AUTH_MODE=google` (otherwise 404). Body `{ "id_token": "<Google ID token JWT>" }` → `200 { token, user }`. The token is opaque, valid for `SESSION_TTL_HOURS`. Invalid token or unverified e-mail → 401. The first login creates the user; e-mails in `ADMIN_EMAILS` get the `admin` role.

### `POST /api/v1/auth/logout` → 204 · `GET /api/v1/me` → `User` (401 without a valid token)

## 4. Places (read, guest allowed)

### `GET /api/v1/places`
Query: `features` (CSV, AND, state must be `yes`), `category`, `q` (substring of the name, case-insensitive).

```json
// GET /api/v1/places?features=step_free_entrance   → 200 (first item shown)
{ "items": [ {
    "id": "plc_mnk", "name": "Muzeum Narodowe w Krakowie",
    "category": { "key": "museum", "label": "Muzeum" },
    "location": { "lat": 50.0603, "lon": 19.9238 },
    "accessibility_summary": ["step_free_entrance", "ramp", "elevator", "accessible_toilet", "induction_loop",
                              "braille", "tactile_paths", "good_lighting", "assistance_dog_allowed"],
    "verification": { "...": "see below" } } ],
  "page": 1, "page_size": 2, "total": 2 }
```
Unknown feature → 400.

### `GET /api/v1/places/{id}`
`PlaceSummary` + `short_description`, `address`. Unknown id → 404.

Every `PlaceSummary` (list, details, owner places) carries a **`verification`** block, the "Potwierdzone dzisiaj" badge from the mock-ups:

```json
"verification": { "status": "confirmed", "label": "Potwierdzone dzisiaj",
                  "last_verified": "2026-10-03T12:00:00+00:00", "confidence": 0.6,
                  "confidence_level": "medium", "sources": ["admin", "community"] }
```
- `status`: `conflict` · `confirmed` (today) · `verified_recently` (≤ 30 days) · `verified` (≤ 90 days) · `needs_update` (> 90 days) · `unverified`.
- `label`: "Sprzeczne zgłoszenia", "Zweryfikowane N dni temu", "Wymaga aktualizacji", "Brak danych".
- `confidence`: the mean over known features; levels are high ≥ 0.8, medium ≥ 0.5, otherwise low.

### `GET /api/v1/places/{id}/activity?limit=20`
The "Ostatnie zgłoszenia i potwierdzenia" feed, newest first, with the full history (rejected items included). There is one item per observation:

```json
{ "items": [ { "type": "admin_decision", "label": "Decyzja moderatora", "observation_id": "obs_22",
               "feature": "elevator", "value": "yes", "source": "admin",
               "author": { "id": "usr_admin", "display_name": "Administrator" },
               "comment": "Potwierdzone przez moderatora", "photo_url": null, "votes_up": 0,
               "validation": "VALID", "created_at": "2026-10-03T12:00:00+00:00" } ] }
```
`type`: `issue_reported` · `confirmation` · `owner_update` · `admin_decision` · `open_data_import` · `initial_data`. `limit` is 1–100 (otherwise 400).

### `GET /api/v1/places/{id}/photos`
`{ "items": [ { id, url, author, feature, observation_id, created_at } ], "total": n }`: evidence photos, newest first.

### `GET /api/v1/places/{id}/accessibility`
All 13 features in 7 groups; features without data come back as `unknown`.

```json
{ "place_id": "plc_mnk",
  "groups": [ { "key": "inside", "label": "Wewnątrz", "features": [ {
      "key": "elevator", "label": "Winda", "state": "yes", "temporary": false,
      "confidence": 0.5, "last_verified": "2026-08-04T12:00:00+00:00",
      "sources_count": 1, "validation": "VALID", "active_observation_id": "obs_3" } ] } ] }
```

### `GET /api/v1/places/{id}/check?profile=wheelchair`
`profile`: `wheelchair` · `stroller` · `crutches` · `blind` · `low_vision` · `deaf` · `assistance_dog` (unknown → 400). Rules: [architecture.md §5.3](architecture.md#53-can-i-get-in-domaincheckpy). Example answers on seed data: `plc_mnk` + `blind` → `yes` ("Są ścieżki prowadzące lub oznaczenia w alfabecie Braille'a."), `plc_urzad` + `low_vision` → `no` ("Słabe oświetlenie — zapytaj obsługę o pomoc."), `plc_mnk` + `assistance_dog` → `yes`.

```json
{ "place_id": "plc_mnk", "profile": "wheelchair", "answer": "yes", "confidence": 0.5,
  "reasons": [ { "feature": "step_free_entrance", "state": "yes" },
               { "feature": "ramp", "state": "yes" },
               { "feature": "elevator", "state": "yes" } ],
  "active_issues": [],
  "advice": "Wejście bez barier potwierdzone." }
```

### `GET /api/v1/accessibility/features`
`[ { key, label, features: [ { key, label } ] } ]` with Polish labels, for building filters.

## 4a. Location search, map, categories, geocode

`GET /api/v1/places` also accepts these parameters (all optional; old calls behave the same):

| Param | Meaning |
|---|---|
| `lat`, `lon` | together; adds `distance_m` to items; default sort `nearest`; filters by `radius_m` (default 2000) |
| `bbox` | `minLon,minLat,maxLon,maxLat`, the map viewport |
| `sort` | `nearest` (needs lat/lon) · `name` · `recently_verified` |
| `page`, `page_size` | 1-based, size 1–100 (default 20); `total` counts all matches |
| `view=map` | returns `{ total, items: [ { id, name, location, category, marker } ] }`, all matches without paging; `marker` = wheelchair answer → `accessible` · `partial` · `inaccessible` · `unknown` |

```json
// GET /api/v1/places?lat=50.0617&lon=19.9373&page_size=2   (from Rynek Główny)
{ "items": [ { "id": "plc_camelot", "distance_m": 142, "...": "..." },
             { "id": "plc_urzad", "distance_m": 661, "...": "..." } ],
  "page": 1, "page_size": 2, "total": 4 }
```

- `GET /categories` → `[ { "key": "museum", "label": "Muzeum", "count": 1 }, … ]`.
- `GET /geocode?q=muz` → `[ { "label": "Muzeum Narodowe w Krakowie, al. 3 Maja 1, 30-062 Kraków", "place_id": "plc_mnk", "location": {…} } ]`. It matches place names and addresses (at least 2 characters, max 10 results), works offline and doesn't use Nominatim.

## 5. Reporting and observations

### `POST /api/v1/uploads` (multipart, field `file`)
PNG or JPG (checked by magic bytes), ≤ 10 MB.

```json
// 201
{ "id": "ph_1", "url": "/media/ph_1.png" }
```
Other format → 400, too large → 413.

### `POST /api/v1/ai/image-tags`
Body `{ "photo_ids": ["ph_1"], "place_id": "plc_mnk" }` (1–5 photos). A **suggestion only**; it never changes data. The model depends on `AI_MODE`; any failure falls back to `mock`.

```json
{ "analysis": { "real_place": true, "barrier_detected": true, "barrier_type": "elevator out of order",
                "affected_disabilities": ["wheelchair", "mobility"],
                "description": "Elevator door with an 'out of order' notice; stairs next to the entrance.",
                "confidence": 0.82 },
  "tags": [ { "label": "winda", "feature": "elevator", "confidence": 0.82 },
            { "label": "wejście bez schodów", "feature": "step_free_entrance", "confidence": 0.82 },
            { "label": "awaria", "feature": null, "confidence": 0.82 },
            { "label": "tablica informacyjna", "feature": null, "confidence": 0.82 } ],
  "detected": "Elevator door with an 'out of order' notice; stairs next to the entrance.",
  "suggested": { "element": "elevator", "current_state": "not_working", "severity": "critical" },
  "model": "mock" }
```
`model` is `mock`, `phi-3.5-vision-onnx` or `gemini`. Only screenshots or graphics → 400 `NOT_A_REAL_PLACE`.

### `POST /api/v1/reports`
Creates the report **and** one observation (`works` → `yes`, `not_working` → `no`; `nature=temporary` → `temporary: true`). Photos become evidence. The state is recomputed immediately.

```json
// request
{ "place_id": "plc_mnk", "element": "elevator", "current_state": "not_working",
  "severity": "critical", "nature": "temporary",
  "description": "Winda nieczynna.", "photo_ids": ["ph_1"] }
// 201
{ ...request fields..., "id": "rep_1", "status": "submitted",
  "author": { "id": "usr_anna", "display_name": "Anna K." },
  "created_at": "2026-10-03T12:00:00+00:00", "observation_ids": ["obs_20"] }
```
Validation: description 1–1000 characters, ≤ 5 known photos, valid enums, existing place.

### `GET /api/v1/reports/{id}` — author or admin (else 403)

### `GET /api/v1/places/{id}/observations?feature=&active=true`
`{ "items": [Observation] }`. `active=true` hides `REJECTED`; `active=false` returns the full history.

### `POST /api/v1/places/{id}/observations`
Quick observation without the report form: `{ "feature": "elevator", "value": "yes", "temporary": false, "comment": "", "photo_ids": [] }` → 201 `Observation`. The source follows the author: admin → `admin`, owner of this place → `verified_owner`, otherwise `community`.

### `POST /api/v1/observations/{id}/votes`
Body `{ "value": 1 }` or `{ "value": -1 }`. Voting again replaces the previous vote; voting on your own observation → 400. The response includes the recomputed state:

```json
{ "observation": { "id": "obs_20", "feature": "elevator", "value": "no", "temporary": true,
                   "source": "community", "author": { "id": "usr_anna", "display_name": "Anna K." },
                   "evidence": [ { "id": "ph_1", "url": "/media/ph_1.png" } ],
                   "votes": { "up": 1, "down": 0, "my_vote": 1 },
                   "validation": { "status": "VALID", "reason": "" }, "confidence": 0.7, "...": "..." },
  "feature_state": { "key": "elevator", "state": "no", "temporary": true, "confidence": 0.7,
                     "sources_count": 2, "validation": "VALID", "active_observation_id": "obs_20", "...": "..." } }
```

### `DELETE /api/v1/observations/{id}/votes/me` → 204

## 6. Owner (role `owner`)

| Endpoint | Body / response |
|---|---|
| `GET /owner/places` | `{ items: [PlaceSummary] }`, only places where `owner_id` = me |
| `POST /owner/places/{id}/observations` | `{ "observations": [ { feature, value, temporary?, comment?, photo_ids? } ] }` (1–10) → 201 `{ items: [Observation] }` with source `verified_owner` (0.85). Everything is validated before anything is written. Not my place → 403 |
| `GET /owner/reports` | `{ items: [Report] }` on my places, newest first |

Owners **never overwrite** data. A contradiction with users goes to moderation.

## 7. Admin (role `admin`)

### `GET /api/v1/admin/queue?filter=all|conflict&status=open|resolved|all`

```json
{ "items": [ { "id": "q_1", "type": "conflict", "status": "open", "label": "Konflikt danych",
               "place": { "id": "plc_mnk", "name": "Muzeum Narodowe w Krakowie" },
               "feature": "elevator", "observation_count": 2,
               "created_at": "2026-10-03T12:00:00+00:00" } ],
  "total": 1, "counts": { "all": 1, "conflict": 1 } }
```

### `GET /api/v1/admin/queue/{id}`
`QueueItem` + `summary`, `observations` (full, with votes, evidence and source) and the current `feature_state`.

### `POST /api/v1/admin/queue/{id}/decision`
`{ "action": "confirm", "winning_observation_id": "obs_21", "comment": "…" }` or `{ "action": "reject" }`. Semantics: [architecture.md §5.2](architecture.md#52-conflicts-domainvalidationpy).

```json
{ "id": "q_1", "status": "approved",
  "feature_state": { "key": "elevator", "state": "yes", "confidence": 1.0, "validation": "VALID",
                     "sources_count": 3, "active_observation_id": "obs_22", "...": "..." } }
```
Already resolved → 409. `confirm` without a winner from this item → 400.

### `GET /api/v1/admin/stats`
Dashboard tiles from the mock-up. `change_pct` is today vs yesterday in %, and `null` when yesterday was 0 or the tile has no comparison.

```json
{ "new_reports_today":  { "value": 1, "change_pct": null },
  "data_conflicts":     { "value": 1, "change_pct": null },
  "low_confidence":     { "value": 0, "change_pct": null },
  "observations_today": { "value": 2, "change_pct": null },
  "places":             { "value": 4, "change_pct": null },
  "updated_at": "2026-10-03T12:00:00+00:00" }
```
- `data_conflicts`: the value is the number of open items; the change counts items opened today vs yesterday.
- `low_confidence`: known features with confidence < 0.5.
- There is no "abuse reports" tile, because the MVP has no flagging.

### `GET /api/v1/places/{id}/history`
The audit trail ("Historia i audyt"), newest first, for **admins and the owner of the place** (otherwise 403). Events: `observation_added` (every observation, including rejected ones, with final validation and votes), `conflict_detected`, and `conflict_resolved` (with the decision and the time it was made).

```json
{ "items": [ { "event": "conflict_resolved", "description": "Rozstrzygnięto: elevator → approved",
               "created_at": "2026-10-03T12:00:00+00:00", "actor": null, "observation_id": null, "queue_id": "q_1" },
             { "event": "observation_added",
               "description": "community: elevator = no (tymczasowo) · REJECTED · 👍3 👎0",
               "created_at": "2026-10-03T12:00:00+00:00",
               "actor": { "id": "usr_anna", "display_name": "Anna K." }, "observation_id": "obs_20", "queue_id": null } ] }
```

### `POST /api/v1/admin/places/{id}/owner`
`{ "user_id": "usr_marek" }` → `{ place_id, owner: User }`. A `user` is promoted to `owner`.

### `POST /api/v1/admin/imports`
`{ "source": "osm_file" }` (the only source in the MVP). Idempotent; rules in [architecture.md §5.5](architecture.md#55-osm-import-domainosmpy).

```json
{ "source": "osm_file", "points": 18, "places_created": 10, "places_matched": 0,
  "observations": 10, "skipped_unnamed": 7, "skipped_no_data": 1 }
```

### `POST /api/v1/admin/demo/reset` → 204
Clears all data (including the SQLite DB) and loads the seed again.

## 7a. Me (logged-in user)

| Endpoint | Body / response |
|---|---|
| `GET /me/favorites` | `{ items: [PlaceSummary] }` (with `verification`), in the order they were added |
| `PUT /me/favorites/{placeId}` | 204; adding again is a no-op; unknown place → 404 |
| `DELETE /me/favorites/{placeId}` | 204; idempotent |
| `GET /me/reports` | `{ items: [Report] }`, mine only, newest first |

Favourites are stored per user (`users.favorites`, JSON) and survive restarts in SQL mode.

## 8. Open API (`/public/v1`, header `X-Api-Key`)

Read-only, the same data as the internal API, rate-limited per key.

| Endpoint | Response |
|---|---|
| `GET /places?features=&category=&q=` | `{ items: [ { id, name, category, address, location, accessibility_summary } ], total }` |
| `GET /places/{id}` | `PublicPlace` |
| `GET /places/{id}/accessibility` | **flat format**, below |
| `GET /places/{id}/check?profile=wheelchair` | `{ place_id, profile, answer, confidence, advice }` |

Flat format: `yes` → `true`, `no` → `false`, `unknown` → omitted, and `last_verified` is a date.

```json
{ "place": { "id": "plc_mnk", "name": "Muzeum Narodowe w Krakowie" },
  "accessibility": {
    "step_free_entrance": { "value": true, "temporary": false, "confidence": 0.5, "last_verified": "2026-08-04" },
    "elevator":           { "value": true, "temporary": false, "confidence": 1.0, "last_verified": "2026-10-03" } } }
```
No or wrong key → 401. Over the limit → 429 + `Retry-After`. An app Bearer token is **not** an API key.

## 9. MCP tools (for AI assistants)

Served by `clients/mcp_server.py` over stdio; it calls the Open API. Setup: [operations.md §5](operations.md#5-mcp-in-claude).

| Tool | Input | Output |
|---|---|---|
| `check_accessibility` | `place_name`, `profile="wheelchair"` | `{ query, profile, matches: [ { place, answer, confidence, advice, accessibility } ], total_found }`, or `{ matches: [], message }`, or `{ error }` |
| `search_accessible_places` | `features: [..]` | `{ features, places: [ { id, name, address, accessibility_summary } ], total }` or `{ error }` |
