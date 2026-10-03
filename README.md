# Mini MVP — trimmed plan, split by feature

Full contract: [../openapi.yaml](../openapi.yaml) · full plan: [../plan_fastapi.md](../plan_fastapi.md) · API notes: [../api.md](../api.md) · status: [STATUS.md](STATUS.md)

- Effort: ~5.5–7 h solo, ~3–3.5 h for 2–3 devs in parallel after F0.
- Per feature: `plan.md` (scope, model, tasks, DoD) + `openapi.yaml`.
- Each `openapi.yaml` = valid **subset** of full contract: same paths (`/api/v1/...`), schema names, enum values. Merge back = copy, no renames.
- Rules from full plan apply: **TDD** for domain + use cases ([§1a](../plan_fastapi.md)), **save status between steps + local commit** ([§1b](../plan_fastapi.md)).
- Task ids `F<feature>.<n>`. Track them in [STATUS.md](STATUS.md) instead of full-plan T* ids.

## Run

```
uv sync                                                        # once, online
uv run pytest                                                  # 92 tests, ~2 s, offline
uv run uvicorn app.adapters.inbound.http.main:app --port 8000  # http://localhost:8000/docs
```

- Demo login: `POST /api/v1/auth/demo {"username": "anna"}` → use `Authorization: Bearer demo-anna`.
- Reset: `POST /api/v1/admin/demo/reset` with `Bearer demo-admin`.
- Google mode: `.env` → `AUTH_MODE=google`, `GOOGLE_CLIENT_ID=…`, `ADMIN_EMAILS=…` (see `.env.example`).
- Fixed time on stage: `DEMO_NOW=2026-10-03T12:00:00+02:00`.

## Offline / deterministic demo

- Data, trust, queue: in-memory, **no network**. AI, OSM, geocoding: cut (not mocked).
- Auth: `AUTH_MODE=google|demo`.
  - `google`: real Google Sign-In, needs internet.
  - `demo`: **default for demo + tests**. `POST /api/v1/auth/demo` with seeded account, offline.
- Why demo mode: scenario needs 6 distinct users (reporter, 3 voters, 2nd user, admin). Live Google account switching = slow + fragile. Details: [features/01-auth/plan.md](features/01-auth/plan.md).

## Order

| # | Feature | Plan | Contract | Time |
|---|---|---|---|---|
| 0 | Skeleton (model, repo, app, seed, reset, demo test `xfail`) | [plan](features/00-skeleton/plan.md) | — | 45–60 min |
| 1 | Auth (demo + Google Sign-In) | [plan](features/01-auth/plan.md) | [openapi](features/01-auth/openapi.yaml) | 45–75 min |
| 2 | Places + search + check | [plan](features/02-places-search/plan.md) | [openapi](features/02-places-search/openapi.yaml) | 60–90 min |
| 3 | Observations, votes, trust (core) | [plan](features/03-observations-trust/plan.md) | [openapi](features/03-observations-trust/openapi.yaml) | 90–120 min |
| 4 | Moderation queue (admin) | [plan](features/04-admin-queue/plan.md) | [openapi](features/04-admin-queue/openapi.yaml) | 45–60 min |

- F0 blocks all.
- After F0: **F1, F2, F3 in parallel** (demo auth stub ships in F0, Google added in F1).
- F4 needs F3.

---

## 1. Demo scenario (trimmed, end-to-end)

Seeded accounts (`demo` mode): `anna` (reporter), `jan`, `ola`, `piotr` (voters), `marek` (2nd user), `admin`.
Place `plc_mnk` (National Museum), feature `elevator`, seeded `yes` (observation 60 days old).

1. Search step-free places → `GET /places?features=step_free_entrance` (F2)
2. Open details → `GET /places/plc_mnk`, `GET /places/plc_mnk/accessibility` (F2)
3. "Can I get in by wheelchair?" → `GET /places/plc_mnk/check?profile=wheelchair` → `yes` (F2)
4. `anna`: "elevator broken" + photo → `POST /uploads`, `POST /reports` → `elevator: no`, `temporary` (F3)
5. `jan`, `ola`, `piotr` confirm → `POST /observations/{id}/votes` ×3 → confidence 0.9; `check` → `partial` (F3)
6. `marek`: "elevator works" → `POST /places/plc_mnk/observations` → conflict → `GET /admin/queue?filter=conflict` (F3 → F4)
7. `admin` confirms marek's observation → `POST /admin/queue/{id}/decision` → `elevator: yes`, confidence 1.0, `check` → `yes` (F4)

- Reset to pre-step-1: `POST /admin/demo/reset` (F0).
- = core of [api.md §10](../api.md); 2nd user replaces owner.

---

## 2. Cut vs full plan (deliberate)

| Cut | Why / replacement |
|---|---|
| Owner panel (`/owner/*`), roles `owner`, `api_client` | conflict by 2nd `user`; roles left: `guest`, `user`, `admin` |
| AI (`/ai/image-tags`, `/ai/parse-text`) | photo = evidence only |
| OSM import, `/geocode` | places from seed only |
| Open API (`/public/v1/*`) | later, same use cases |
| MCP server | `mcp_server.py` untouched |
| Route A→B | not in mockups |
| Report drafts (`PATCH /reports/{id}`, `/submit`) | `POST /reports` → `status=submitted` immediately |
| `action=escalate` | `confirm` / `reject` only |
| Feature state `partial`, `current_state=partially_works` | states `yes/no/unknown`. **`check` answer may still be `partial`** (full-enum value) |
| Favorites, history/audit, admin stats, merge, flagging, gallery, activity | not on demo path |
| SQLAlchemy / persistent DB | in-memory only; seed on startup + reset endpoint |
| Trust age decay | simplified formula (F3); 30-day conflict window kept |
| Domain events + dispatcher | use case creates `QueueItem` directly on conflict |

If time left: Open API → AI mock → owner → OSM import (see §6).

---

## 3. Architecture (light hexagon, shared)

```
app/
  domain/
    model.py         # dataclasses from §4
    enums.py         # FeatureKey (5), StateValue, ObservationSource, ValidationStatus, NeedsProfile, Role, …
    trust.py         # F3
    validation.py    # F3
    check.py         # F2
    errors.py        # DomainError: NotFound, Forbidden, ValidationFailed, ConflictError, Unauthorized
  application/
    ports.py         # Protocols: Repo, Clock, IdGenerator, FileStorage, IdentityVerifier
    use_cases.py     # all use cases, one file
  adapters/
    inbound/http/    # main.py (create_app + lifespan), deps.py, errors.py, schemas.py, routers.py
    outbound/
      memory.py      # InMemoryRepo, SystemClock/FixedClock, SeqIdGenerator
      files.py       # LocalFileStorage (./media, offline)
      google_auth.py # GoogleIdentityVerifier (F1) + FakeIdentityVerifier (tests)
  bootstrap.py       # Settings → adapters → Container
  config.py          # AUTH_MODE, GOOGLE_CLIENT_ID, ADMIN_EMAILS, MEDIA_DIR, DEMO_NOW
  seed.py            # load_seed(repo, clock): places, observations, demo accounts
tests/
  unit/        test_trust.py, test_validation.py, test_check.py
  application/ test_use_cases.py   # InMemoryRepo + FixedClock
  api/         test_demo_flow.py   # scenario §1 via httpx (AUTH_MODE=demo)
```

- Dependency rule kept: `domain` imports no fastapi/pydantic/google. No `test_architecture.py`; enforced in review (small codebase).
- **One repo** (`InMemoryRepo`), no UoW.
- Each write = one sync block, no `await` inside → atomic on asyncio loop.

---

## 4. Data model (shared, minimal)

```python
User(id, display_name, role: Literal["user", "admin"], email=None, google_sub=None)  # guest = no user
Session(token, user_id, expires_at)
Place(id, name, category, location: GeoPoint(lat, lon), short_description, address="")
Observation(id, place_id, feature, value: Literal["yes", "no"], source, author_id, created_at,
            temporary=False, comment="", evidence_ids: list[str], votes: dict[user_id, 1 | -1],
            validation="VALID", confidence=0.0, report_id=None)
FeatureStateRecord(place_id, feature, state: Literal["yes", "no", "unknown"], confidence,
                   temporary, last_verified, sources_count, validation, active_observation_id)
Report(id, place_id, author_id, element: FeatureKey, current_state: Literal["works", "not_working"],
       severity, nature, description, photo_ids, status="submitted", created_at, observation_ids)
QueueItem(id, place_id, feature, observation_ids, type="conflict", status: open | resolved, created_at)
Photo(id, path, url)
```

- `FeatureStateRecord` **always computed** from observations (`trust.compute_feature_state`). Never written by hand, seed included.
- MVP `FeatureKey`: `step_free_entrance`, `ramp`, `elevator`, `accessible_toilet`, `induction_loop`. All in full enum (35) → no renames on merge.

---

## 5. Definition of Done (whole MVP)

- `test_demo_flow.py` green: scenario §1 end-to-end (`AUTH_MODE=demo`, `FixedClock`).
- `test_trust.py`, `test_validation.py`, `test_check.py` green. Cover: no-conflict observation, two contradicting values, old observation outside window, votes → confidence, 4 `check` answers.
- `POST /admin/demo/reset` (or restart) → demo repeatable, identical numbers.
- **Fully offline** in `AUTH_MODE=demo`. Only network code: `GoogleIdentityVerifier` (F1), used in `AUTH_MODE=google` only.
- Every `features/*/openapi.yaml` passes `openapi-spec-validator`.
- [STATUS.md](STATUS.md) current; local commit per task.

## 6. Next (beyond MVP, by value)

1. Open API (`/public/v1/*`): same use cases, separate router.
2. `POST /ai/image-tags` with mock: demo wow factor.
3. `owner` role + `verified_owner` observations: conflict as in original scenario.
4. OSM import / MCP integration: see [../plan_fastapi.md](../plan_fastapi.md) (phases 4–5).
5. SQLAlchemy instead of in-memory: `Repo` port stays, add adapter (full plan T0.6).
