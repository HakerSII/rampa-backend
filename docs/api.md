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
| `/api/v1` (users) | `Authorization: Bearer <token>` | `POST /auth/demo` (demo mode: token = `demo-<username>`), `POST /auth/google` or `POST /auth/anonymous` (device identity, any mode) |
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
| Feature (35) | entrance: `step_free_entrance`, `ramp`, `elevator_entrance`, `wide_doors`, `automatic_doors`, `call_bell` · inside: `elevator`, `escalator`, `spacious_interior`, `high_contrast_info`, `tactile_info` · toilet: `accessible_toilet`, `adult_changing_table`, `turning_space`, `extra_accessible_toilets` · hearing: `induction_loop`, `sign_language_interpreter`, `video_captions`, `fm_system` · vision: `braille`, `tactile_paths`, `good_lighting`, `high_contrast_markings`, `accessible_digital_materials`, `audio_description` · mobility: `lowered_curb`, `platform_elevator`, `crutches_friendly` · parking: `disabled_parking`, `marked_parking`, `level_surface`, `more_than_n_spots`, `drop_off_zone` · other: `assistance_dog_allowed`, `pets_allowed` |
| Feature group | `entrance`, `inside`, `toilet`, `hearing`, `vision`, `mobility`, `parking`, `other` |
| Needs profile (`check`) | `wheelchair`, `stroller`, `crutches`, `blind`, `low_vision`, `deaf`, `assistance_dog` |
| State | `yes`, `partial`, `no`, `unknown` |
| Observation value | `yes`, `partial`, `no` (+ optional `valid_until` for temporary issues) |
| Source | `community` (0.5), `open_data` (0.6), `verified_owner` (0.85), `admin` (1.0) |
| Validation | `VALID`, `CONFLICT`, `REJECTED`, `FLAGGED` |
| Place type | `venue`, `shop`, `public_transport_stop`, `platform`, `parking`, `office`, `street_segment`, `other` |
| Check answer | `yes`, `partial`, `no`, `unknown` |
| Report `current_state` / `severity` / `nature` | `works·partially_works·not_working` / `critical·obstacle·minor` / `permanent·temporary·unknown` |
| Role | `guest`, `user`, `owner`, `admin` |

## 2. Endpoint overview

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/auth/demo` | — | Demo login (demo mode) |
| POST | `/api/v1/auth/google` | — | Google Sign-In login (google mode) |
| POST | `/api/v1/auth/anonymous` | — | Device identity without an account (map front end) |
| POST | `/api/v1/auth/logout` | user | End session |
| GET | `/api/v1/me` | user | Current user |
| GET | `/api/v1/places` | — | Search places |
| POST | `/api/v1/places/resolve` | user | Map pin + name → place (matched or created) |
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
| PATCH | `/api/v1/reports/{id}` | author | Edit a draft |
| POST | `/api/v1/reports/{id}/submit` | author | Submit a draft → observation |
| POST | `/api/v1/ai/parse-text` | user | Free text → suggested observations |
| GET | `/api/v1/places/{id}/similar` | — | Similar places nearby |
| GET | `/api/v1/routes/accessible` | — | A→B route for a profile (heuristic) |
| GET | `/api/v1/admin/places/{id}/confidence` | admin | Confidence widget |
| POST | `/api/v1/admin/queue/{id}/comments` | admin | Moderator comment |
| POST | `/api/v1/admin/observations/{id}/flag` | admin | Flag abuse/spam |
| POST | `/api/v1/admin/places/{id}/merge` | admin | Merge duplicate place |
| POST | `/api/v1/admin/revalidate` | admin | Recompute all states |
| POST | `/api/v1/owner/ownership-requests` | user | Apply for ownership |
| GET | `/api/v1/admin/ownership-requests` | admin | Ownership requests |
| POST | `/api/v1/admin/ownership-requests/{id}/verify` | admin | Approve / reject ownership |
| GET/PATCH | `/api/v1/owner/me` | owner | Owner profile |
| GET | `/api/v1/owner/stats` | owner | Owner tiles |
| PATCH | `/api/v1/owner/places/{id}` | owner of place | Edit basic info + contact |
| PUT | `/api/v1/owner/places/{id}/opening-hours` | owner of place | Opening hours |
| POST/DELETE | `/api/v1/owner/places/{id}/photos[/{photoId}]` | owner of place | Presentation photos |
| GET | `/api/v1/owner/places/{id}/stats` | owner of place | Place stats |
| POST | `/api/v1/owner/reports/{id}/reply` | owner of place | Reply to a report |
| POST | `/api/v1/owner/reports/{id}/approve` | owner of place | Confirm a report |
| GET | `/api/v1/owner/reminders` | owner | Reminders |
| GET | `/api/v1/owner/suggestions` | owner | Improvement suggestions |
| POST | `/api/v1/owner/observations/batch` | owner | Batch update (all-or-nothing) |
| GET | `/api/v1/owner/places/import/template` | owner | CSV template |
| POST | `/api/v1/owner/places/import` | owner | CSV import |
| GET | `/api/v1/observations` | — | Map layer: observations across places (one request) |
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

### `POST /api/v1/auth/anonymous`
Identity per **device** for the map front end, which has no accounts: every call creates a new `user` and
returns a token valid for `ANONYMOUS_TTL_DAYS` (365). The front end stores the token and reuses it, so votes
stay one per device and a device cannot confirm its own report. Works in every `AUTH_MODE`;
`ANONYMOUS_AUTH=false` → 404. Body is optional: `{ "display_name": "Gość" }` (≤ 60 characters, default "Anonim").

```json
// 201
{ "token": "…", "user": { "id": "usr_42", "display_name": "Anonim", "email": null, "role": "user" } }
```

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

### `POST /api/v1/places/resolve` (user)
Turns a map pin into a place to report on. The front end sends the name it already has (nearest city stop,
reverse geocoding) with the coordinates. The same name (case-insensitive) within **50 m** is the same place
(the OSM import rule) → `200`; otherwise a new place is created → `201`. Name 1–120 characters,
`category` defaults to `other`, `address` is optional.

```json
// request
{ "name": "Rondo Mogilskie", "lat": 50.0656, "lon": 19.9585 }
// 201
{ "created": true,
  "place": { "id": "plc_1", "name": "Rondo Mogilskie", "category": { "key": "other", "label": "Inne" },
             "location": { "lat": 50.0656, "lon": 19.9585 }, "place_type": "venue", "distance_m": null,
             "accessibility_summary": [],
             "verification": { "status": "unverified", "label": "Brak danych", "last_verified": null,
                               "confidence": 0.0, "confidence_level": "low", "sources": [] },
             "short_description": "", "address": "", "opening_hours": [], "contact": {} } }
```

### `GET /api/v1/places/{id}/accessibility`
All 35 features in 8 groups; features without data come back as `unknown`.

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
| `place_type` | CSV of place types (`office,public_transport_stop`); unknown type → 400 |
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

## 4b. Similar places and accessible route

### `GET /api/v1/places/{id}/similar?limit=5`
`{ items: [PlaceSummary + distance_m] }`: other places within 3 km, same category first, then nearest. `limit` is 1–20.

### `GET /api/v1/routes/accessible?from=plc_mnk&to=plc_urzad&profile=wheelchair`
`from` and `to` are a place id or `lat,lon`. **This is a heuristic, not a routing engine** (`note` says so):
- the route is a straight line, with `distance_m` and `duration_min` at 50 m/min;
- it collects the street-level features relevant to the profile from places within 100 m of the line: wheelchair/stroller/crutches → `lowered_curb`, `platform_elevator`; blind → `tactile_paths`, `lowered_curb`; low vision → `good_lighting`;
- `no` → `barriers`, `yes` → `helpers`;
- `feasible`: barriers → `partial`, data without barriers → `yes`, no data → `unknown`.

```json
{ "feasible": "yes", "profile": "wheelchair", "distance_m": 1601, "duration_min": 33,
  "geometry": { "type": "LineString", "coordinates": [[19.9238, 50.0603], [19.945, 50.065]] },
  "barriers": [],
  "helpers": [ { "place_id": "plc_urzad", "name": "Urząd Dzielnicy I", "feature": "lowered_curb",
                 "label": "Obniżony krawężnik", "location": { "lat": 50.065, "lon": 19.945 } } ],
  "note": "heuristic: straight line between the points; …" }
```

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
Quick observation without the report form: `{ "feature": "elevator", "value": "yes|partial|no", "temporary": false, "comment": "", "photo_ids": [], "valid_until": "2026-10-05T18:00:00+02:00" }` → 201 `Observation`. `valid_until` (optional, future, else 400) marks a temporary issue that stops counting after that time. The source follows the author: admin → `admin`, owner of this place → `verified_owner`, otherwise `community`.

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

## 5a. Report drafts (Zapisz szkic)

- `POST /reports` with `"draft": true` creates a draft. Only `place_id` is required; the other fields are optional but validated if given. **No observation is created and the state doesn't change.**
- `PATCH /reports/{id}` is a partial update by the author: 403 for anyone else, 409 if the report isn't a draft.
- `POST /reports/{id}/submit` runs full validation (a 400 message lists missing fields), creates the observation and recomputes the state. Submitting again → 409.
- Without `draft` (the default) the report is submitted immediately, as in §5.
- Drafts appear in `GET /me/reports` and are hidden from owner reports and admin stats.

## 5b. AI from text

`POST /api/v1/ai/parse-text {"text": "Winda od dwóch tygodni nie działa, ale podjazd jest odśnieżony"}` →

```json
{ "suggestions": [
    { "feature": "elevator", "label": "Winda", "value": "no", "temporary": true, "confidence": 0.8 },
    { "feature": "ramp", "label": "Podjazd", "value": "yes", "temporary": false, "confidence": 0.8 } ],
  "model": "rules" }
```
- Keyword rules in PL and EN, run offline. The text is split into clauses (`. , ; ! ?`, "ale", "but").
- Each clause gets features and a polarity: negation ("nie działa", "brak", "zepsuta", "zastawiony" …) → `no`; confirmation ("działa", "naprawiona", "jest" …) → `yes`.
- "Bez schodów" → step-free entrance `yes`; stairs mentioned → `no` (confidence 0.6).
- "od …", "remont", "dziś" → `temporary`.
- It's a **suggestion only** and pre-fills the report form. Text must be 1–1000 characters.

## 5c. Map layer of observations

`GET /api/v1/observations?active=true&bbox=19.93,50.055,19.95,50.07&value=no&current=true&since=…&limit=200`: observations across all places, **newest first**. Each item is a full `Observation` plus:

```json
{ "place": { "id": "plc_camelot", "name": "Cafe Camelot", "location": { "lat": 50.0628, "lon": 19.9383 } },
  "severity": "obstacle" }
```
- `active` (default `true`) leaves out REJECTED, FLAGGED and expired observations.
- `bbox` filters on the place location.
- `current=true` returns only observations that currently decide their feature's state.
- `severity` comes from the report the observation came from (`null` for quick observations, imports and seed data).
- `limit` is 1–500.

One request replaces per-place `GET /places/{id}/observations` loops in the map front end.

## 6. Owner (role `owner`)

| Endpoint | Body / response |
|---|---|
| `GET /owner/places` | `{ items: [PlaceSummary] }`, only places where `owner_id` = me |
| `POST /owner/places/{id}/observations` | `{ "observations": [ { feature, value, temporary?, comment?, photo_ids? } ] }` (1–10) → 201 `{ items: [Observation] }` with source `verified_owner` (0.85). Everything is validated before anything is written. Not my place → 403 |
| `GET /owner/reports` | `{ items: [Report] }` on my places, newest first |

Owners **never overwrite** data. A contradiction with users goes to moderation.

## 6a. Owner panel extras

Everything requires role `owner`; place-level endpoints also require ownership of the place (otherwise 403).

| Endpoint | Behaviour |
|---|---|
| `GET /owner/me` · `PATCH /owner/me {display_name?, email?}` | `{ id, display_name, email, role, verified, places }` |
| `GET /owner/stats` | `{ managed_places, avg_confidence, reports_30d, updates_30d, open_conflicts }` |
| `PATCH /owner/places/{id}` | `name`, `short_description`, `address`, `category`, `contact {phone, website, email}` → `Place` (now with `opening_hours`, `contact`) |
| `PUT /owner/places/{id}/opening-hours` | `[{days, open, close} \| {days, closed: true}]`, HH:MM with open < close, max 14 entries |
| `POST /owner/places/{id}/photos {photo_id}` · `DELETE …/photos/{photoId}` | presentation photos; the gallery shows them first with `kind: owner` |
| `GET /owner/places/{id}/stats` | `{ observations, by_source, votes_up, votes_down, open_conflicts, last_verified, confidence }` |
| `POST /owner/reports/{id}/reply {text}` | 201 report with `replies[]` (visible to the author) |
| `POST /owner/reports/{id}/approve` | owner confirms → **verified_owner observation with the report's value**; `owner_status: approved`; second time → 409 |
| `GET /owner/reminders` | `{ items: [{ place_id, kind, text, priority, feature }] }`: `missing_data` (unknown core features), `stale_data`, `conflict` and `unanswered_report` (high priority first) |
| `GET /owner/suggestions` | features that are `no` on my places → "Rozważ: …" |
| `POST /owner/observations/batch [{place_id, feature, value, …}]` | 1–50 items across own places; all validated before writing (one foreign place → 403, nothing written) |
| `GET /owner/places/import/template` | `text/csv`: `place_id,feature,value,temporary,comment` |
| `POST /owner/places/import` (multipart `file`) | `{ imported, errors: [{ row, message }] }`: valid rows imported, `row` is the file line number |

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
{ "source": "osm_file", "points": 18, "places_created": 11, "places_matched": 0,
  "observations": 11, "skipped_unnamed": 7, "skipped_no_data": 0 }
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

## 7b. Admin extras

| Endpoint | Behaviour |
|---|---|
| `GET /admin/places/{id}/confidence` | `{ overall, by_group: { entrance: 0.5, … }, note }`: means over known features; `note` warns about conflicts |
| `POST /admin/queue/{id}/comments {text}` | 201 → all comments of the item; comments also appear in the queue detail |
| `POST /admin/observations/{id}/flag {reason}` | abuse/spam → `validation.status: FLAGGED`, `validation.reason`; excluded from trust and conflicts (like REJECTED), state recomputed, history kept; dashboard tile `abuse_flags` |
| `POST /admin/places/{id}/merge {into_place_id}` | duplicate → target: moves observations, reports, queue items, favourites and ownership requests; deletes the duplicate; recomputes the target |
| `POST /admin/revalidate` | recomputes every state → `{ places, features }` |
| `POST /owner/ownership-requests {place_id, justification}` | any user, 201 `status: pending` |
| `GET /admin/ownership-requests?status=pending` | `{ items: [ { id, place_id, user, justification, status, created_at, decided_at } ] }` |
| `POST /admin/ownership-requests/{id}/verify {approved}` | approved → the user becomes the owner (promoted to `owner`); a second decision → 409 |

## 8. Open API (`/public/v1`, header `X-Api-Key`)

Read-only, the same data as the internal API, rate-limited per key.

| Endpoint | Response |
|---|---|
| `GET /places?features=&category=&q=` | `{ items: [ { id, name, category, address, location, accessibility_summary } ], total }` |
| `GET /places/{id}` | `PublicPlace` |
| `GET /places/{id}/accessibility` | **flat format**, below |
| `GET /places/{id}/check?profile=wheelchair` | `{ place_id, profile, answer, confidence, advice }` |

Flat format: `yes` → `true`, `no` → `false`, `partial` → `"partial"`, `unknown` → omitted, and `last_verified` is a date.

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
