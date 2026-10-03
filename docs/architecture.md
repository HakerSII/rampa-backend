# Architecture

## 1. Core idea: observations, not flags

The system never stores "this place is accessible: true". It stores **observations**: single statements about a single feature, each with a source, author, time, optional photo evidence and community votes. The visible state is always **computed**:

```mermaid
flowchart LR
    I[User report / owner update / OSM import / admin decision] --> O[Observation]
    O --> V[Validation<br/>conflict detection]
    V --> T[Trust<br/>confidence per observation]
    T --> S[Feature state<br/>yes · no · unknown + confidence]
    S --> R[Search · check · Open API · MCP]
```

This gives every piece of information a **source, a date, a history, evidence and a confidence level**. Nothing is overwritten. An owner's "repaired" statement does not erase users' "broken" reports; it becomes another observation, and conflicts go to a moderator.

## 2. Hexagonal architecture (ports and adapters)

```mermaid
flowchart TB
    subgraph IN[Inbound adapters]
        HTTP[FastAPI routers<br/>/api/v1, /public/v1]
        MCPC[MCP client<br/>clients/ → Open API]
    end
    subgraph CORE[Application + domain]
        UC[application/use_cases.py<br/>UseCases]
        PORTS[application/ports.py<br/>Repo · Clock · IdGenerator · FileStorage<br/>IdentityVerifier · VisionAnalyzer · OsmSource]
        DOM[domain/<br/>model · enums · trust · validation · check<br/>suggestions · osm · geo · errors]
    end
    subgraph OUT[Outbound adapters]
        MEM[memory.py InMemoryRepo]
        SQL[sql.py SqlRepo SQLite]
        FILES[files.py LocalFileStorage]
        GOO[google_auth.py]
        VIS[vision_mock / vision_onnx / vision_gemini]
        OSMF[osm_file.py]
    end
    HTTP --> UC
    MCPC -.HTTP.-> HTTP
    UC --> DOM
    UC --> PORTS
    MEM & SQL & FILES & GOO & VIS & OSMF -.implement.-> PORTS
```

**Dependency rule:**
- `domain` imports only the standard library.
- `application` imports `domain` and its own ports.
- FastAPI, SQLAlchemy, httpx, google-auth and onnxruntime appear **only in adapters** and in `bootstrap.py`, the composition root.

Benefits in practice:
- Every external dependency has an offline or mock twin, chosen by config: `REPO_MODE`, `AUTH_MODE`, `AI_MODE`. The demo never depends on the network.
- Use cases are tested on in-memory fakes in milliseconds.
- The same use cases serve the internal API, the Open API and, through the Open API, the MCP tool.

### Module map

| Path | Role |
|---|---|
| `main.py` | Entry point (`uv run python main.py`) |
| `app/config.py` | `Settings` (pydantic-settings, `.env`) — see [configuration.md](configuration.md) |
| `app/bootstrap.py` | Composition root: picks adapters by config, seeds an empty store |
| `app/seed.py` | Deterministic demo data: 4 places, 7 demo accounts, system authors |
| `app/domain/model.py` | Entities and value objects (dataclasses) |
| `app/domain/enums.py` | `FeatureKey`, `StateValue`, `ObservationSource`, `Role`, … + Polish labels |
| `app/domain/trust.py` | Confidence per observation, winner → feature state |
| `app/domain/validation.py` | Conflict detection (30-day window) |
| `app/domain/check.py` | "Can I get in?" rules per needs profile |
| `app/domain/suggestions.py` | AI analysis → tags and report-form suggestion |
| `app/domain/osm.py`, `geo.py` | OSM tag mapping, haversine distance |
| `app/application/ports.py` | Port protocols |
| `app/application/use_cases.py` | All use cases (`UseCases` class) |
| `app/adapters/inbound/http/` | `main.py` (app factory, middleware), `deps.py` (auth deps), `errors.py`, `schemas.py`, `rate_limit.py`, `routers/*` |
| `app/adapters/outbound/` | `memory.py`, `sql.py`, `files.py`, `google_auth.py`, `vision_*.py`, `osm_file.py` |
| `clients/` | MCP server + tool logic (Open API client) |
| `data/` | OSM snapshot; SQLite DB file (`rampa.db`, gitignored) |
| `media/` | Uploaded photos (gitignored) |
| `features/` | Per-feature plans and OpenAPI contracts |
| `tests/` | `unit/` (domain), `application/` (use cases on fakes), `adapters/` (SQL, Gemini), `api/` (HTTP, contract, demo flow, MCP tools) |

## 3. Request lifecycle

Example: a user reports a broken elevator with a photo.

```mermaid
sequenceDiagram
    participant C as Client
    participant R as Router (inbound)
    participant U as UseCases
    participant D as Domain (trust, validation)
    participant P as Repo (memory / SQLite)
    C->>R: POST /api/v1/reports (Bearer demo-anna)
    R->>R: deps: token → User (401 if missing)
    R->>U: create_report(user, …)
    U->>U: validate enums, description, photo ids
    U->>P: add Report + Observation(source=community)
    U->>U: recompute(place, feature)
    U->>D: conflicting_observations(window 30 d)
    D-->>U: [] or conflicting set → QueueItem
    U->>D: compute_feature_state(observations)
    D-->>U: FeatureStateRecord(state, confidence, …)
    U->>P: save_state
    R-->>C: 201 Report
    Note over R,P: middleware: non-GET → repo.commit() (SQLite write)
```

- **Atomicity:** each use case runs as one synchronous block, with no `await` between reading and writing state, so it is atomic on the asyncio event loop.
- **Errors:** domain exceptions (`NotFound`, `Forbidden`, `ValidationFailed`, …) are mapped to the uniform error JSON in `inbound/http/errors.py`.

## 4. Domain model

| Entity | Key fields | Notes |
|---|---|---|
| `Place` | id, name, category, location (`GeoPoint`), address, `owner_id`, `external_id` | Descriptive data only; accessibility lives in states |
| `Observation` | place, feature, value `yes/no`, source, author, created_at, temporary, comment, evidence (photo ids), votes `{user: ±1}`, validation, confidence | Never deleted, only `validation` changes |
| `FeatureStateRecord` | place, feature, state `yes/no/unknown`, confidence, temporary, last_verified, sources_count, validation, active_observation_id | **Computed**, never written by hand |
| `Report` | element, current_state `works/not_working`, severity, nature, description, photos, observation_ids | The UI form; on submit it creates one observation |
| `QueueItem` | place, feature, observation_ids, status `open/resolved`, decision | One open item per place + feature |
| `User` / `Session` | role `user/owner/admin`; demo username or Google `sub` | Guest = no user |
| `Photo` | path, url, original_name | Stored in `media/` |

**Accessibility features (MVP):** `step_free_entrance`, `ramp` (group *entrance*), `elevator` (*inside*), `accessible_toilet` (*toilet*), `induction_loop` (*hearing*). They are a subset of the 35 features in the full contract (`../openapi.yaml` in the docs repo).

## 5. Rules

### 5.1 Trust (`domain/trust.py`)

Confidence of a single observation:

| Component | Value |
|---|---|
| Source weight | `admin` 1.0 · `verified_owner` 0.85 · `open_data` (OSM) 0.6 · `community` 0.5 |
| Photo evidence | +0.1 |
| Each 👍 | +0.1, capped at +0.3 |
| Each 👎 | −0.1 |
| Clamp, round | [0, 1], 2 decimals |

Feature state:
1. Ignore `REJECTED` observations.
2. The winner is the observation with the highest confidence. Ties go to the newer one, then to the later-inserted one.
3. `state` is the winner's value. `confidence`, `temporary` and `last_verified` also come from the winner.
4. With no observations, the state is `unknown` and confidence is 0.

> Example (demo): seed `yes` 0.5 (60 days old) → Anna `no` + photo 0.6 → +3 👍 = 0.9 → state `no`.

### 5.2 Conflicts (`domain/validation.py`)

- **Window:** non-rejected observations from the last **30 days**.
- **Conflict:** the window has **≥ 2 distinct values** and **≥ 2 distinct authors**.
- **When it happens:** the observations are marked `CONFLICT`, a `QueueItem` is opened (or extended), and the state's `validation` is `CONFLICT`.
- Seed data is 60 days old, so the first fresh report never conflicts with it.
- **Admin `confirm`** (with a winning observation):
  - the winner and observations with the same value become `VALID`;
  - observations with the opposite value become `REJECTED`;
  - a new `admin` observation (weight 1.0) is added;
  - the item is resolved.
- **Admin `reject`:** all observations in the item become `REJECTED`, and the state falls back to older data.

### 5.3 "Can I get in?" (`domain/check.py`, profile `wheelchair`)

| Entrance = `step_free_entrance` OR `ramp` | Elevator | Answer |
|---|---|---|
| any `yes` | not `no` | `yes` |
| any `yes` | `no` (incl. temporary) | `partial` (you get in, upper floors may be unreachable) |
| known and none `yes` | — | `no` |
| no data | — | `unknown` |

Confidence is the minimum of the states used. `active_issues` lists temporary `no` observations that currently win.

### 5.4 AI suggestions (`domain/suggestions.py` + vision adapters)

- `VisionAnalyzer` returns `ImageAnalysis`: `real_place`, `barrier_detected`, `barrier_type`, `affected_disabilities`, `description`, `confidence`. All models share one prompt and schema (`vision_prompt.py`).
- **Keyword mapping** (PL + EN) turns the analysis into feature tags (winda, wejście bez schodów, podjazd, …) plus `awaria` and `tablica informacyjna`.
- **Suggestion** (only when a barrier is detected): element = first feature, state = `not_working`, severity = `critical` if wheelchair, mobility or physical impairment is affected, otherwise `obstacle`.
- **Several photos:** non-real ones are skipped, tags are merged, and the most confident analysis wins. If none is real, the call returns 400 `NOT_A_REAL_PLACE`.
- **AI is a suggestion only.** It fills the report form and never changes feature state.
- **Models:** `mock` (deterministic, offline), `onnx` (Phi-3.5 Vision locally), `gemini` (Google Gemini REST, retries 429/5xx). The real models are wrapped in `FallbackVisionAnalyzer`: any error or timeout returns the mock answer, so the demo never breaks.

### 5.5 OSM import (`domain/osm.py`)

- **Input:** `data/osm_krakow_tauron.json`, a snapshot made by `get_from_api.py` from Overpass.
- **Tag mapping:**
  - `wheelchair` `yes`/`no` → `step_free_entrance`; `limited` is skipped, because the MVP has no `partial` state;
  - `toilets:wheelchair` `yes`/`no` → `accessible_toilet`.
- **Places:** matched by `external_id` (`osm:<lat>,<lon>`) or by the same name within **50 m**; otherwise a new `plc_osm_N` is created. Unnamed points are skipped.
- **Observations:** source `open_data` (0.6), author `usr_osm` "OpenStreetMap". **Idempotent:** an identical observation is not added twice.

### 5.6 Roles and sources

| Role | Can | Observation source |
|---|---|---|
| guest | read places, check, Open API (with key) | — |
| user | report, observe, vote, upload, AI | `community` |
| owner | + owner panel, batch updates of **own** places | `verified_owner` on own places, `community` elsewhere |
| admin | + moderation, imports, owner assignment, demo reset | `admin` |

Public display names are shortened to "Anna K." (privacy rule from the mock-ups).

## 6. Persistence (`REPO_MODE`)

- **`memory`:** `InMemoryRepo`, plain dictionaries. Used by tests and ad-hoc runs; data is lost on restart.
- **`sql`** (default): `SqlRepo`, a **write-behind cache** over **SQLite or Postgres** via SQLAlchemy Core (same code; `DB_ENGINE`, `Settings.db_url`, Postgres via `psycopg`).
  - On start: `create_all` (retried while a Postgres container is still booting), then load every row into memory, ordered by `seq` so insertion order and tie-breaks are preserved.
  - After every non-GET request, middleware calls `repo.commit()`. It diffs the current rows against a snapshot of the last commit and issues the needed `INSERT`, `UPDATE` and `DELETE` statements.
  - Datetimes are stored as ISO strings to keep time zones; lists and dicts are stored as JSON.
  - At bootstrap: an empty DB is seeded. A non-empty DB is loaded, and the id counters continue past the stored ids so new ids never collide.
  - Tables: `users`, `sessions`, `places`, `feature_states`, `observations`, `reports`, `photos`, `queue_items`.
- **Why write-behind:** the `Repo` port is synchronous and the use cases mutate domain objects in place. This adds persistence without touching the domain or use cases.
- **Schema evolution:** on start, `SqlRepo` adds any **missing nullable columns** to existing tables (`ALTER TABLE … ADD COLUMN`), so databases created by older versions keep working (e.g. `queue_items.resolved_at`, F13). It never drops or renames anything.
- **Limit:** a single process only (one uvicorn worker), on both SQLite and Postgres. Multiple workers or replicas would need a fully SQL-backed repository; the port stays the same.
- **Deployment:** `docker-compose.yml` = `postgres:17-alpine` (healthcheck, volume `pgdata`) + the API image (`Dockerfile`, uv, Python 3.13, extra `postgres`). Verified: the full `demo.http` and the SqlRepo test suite pass on Postgres.

## 7. Auth

- **`AUTH_MODE=demo`** (default):
  - `POST /auth/demo {"username"}` returns the token `demo-<username>`;
  - demo tokens are **stateless** (resolved by username), so they survive a demo reset;
  - accounts: `anna`, `jan`, `ola`, `piotr`, `marek` (users), `ewa` (owner of `plc_mnk` and `plc_camelot`), `admin`.
- **`AUTH_MODE=google`:**
  - the front end gets a Google ID token (Google Identity Services);
  - `POST /auth/google` verifies it (signature, audience, expiry, issuer, verified e-mail) via `google-auth`, in a worker thread;
  - the user is upserted by Google `sub`, and e-mails in `ADMIN_EMAILS` get the admin role;
  - the response is an opaque session token (24 h TTL).
- **Open API:** the `X-Api-Key` header (`PUBLIC_API_KEYS`), with a per-key fixed-window rate limit (`PUBLIC_RATE_LIMIT_PER_MIN`, default 60) → 429 with `Retry-After`. App Bearer tokens are not accepted there.

## 8. MCP integration

`clients/mcp_server.py` (FastMCP, optional extra `mcp`) exposes two tools to AI assistants:
- `check_accessibility(place_name, profile="wheelchair")`
- `search_accessible_places(features)`

It is a **client of the Open API**, not part of the backend process. With in-memory data, a separate process would not see the app's live data, and going through the public API proves that external integrations work. If the backend is down, a tool returns `{"error": …}` instead of crashing.

## 9. Design decisions and known limits

| Decision | Why | Cost / limit |
|---|---|---|
| Observations + computed state | Trust, history, conflicts, "Yanosik" model | More logic than a flag; mitigated by pure, tested domain functions |
| Hexagon with mock/offline adapters | Offline, deterministic demo; fast tests | More files; ports only where there are ≥2 implementations |
| Sync `Repo` + write-behind SQLite | Atomic use cases, persistence without a rewrite | Single process |
| MVP feature set: 5 features, `yes/no/unknown` | Scope for the hackathon | `partial` states and the other 30 features are in the full contract only |
| AI = suggestion only + fallback | AI never corrupts data; demo never breaks | Keyword mapping is simple (PL/EN) |
| Open API mounted at `/public/v1` | Separate versioning from the internal API | Differs from the full contract (`/api/v1/public/v1`) |
| OSM from a snapshot | Overpass timed out on the corporate network | No live import (port ready) |
| Admin assigns owners directly | Simplicity | No "owner applies → admin verifies" flow |
