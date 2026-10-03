# F0 — Skeleton (shared by all features)

Overview: [../../README.md](../../README.md) · blocks: F1–F4

## Scope

Everything needed for parallel work: domain model, ports, in-memory repo, FastAPI app + error handling, seed on startup, demo reset, demo-login stub, demo-flow test skeleton (TDD: `xfail`, removed step by step).

## Tasks

| Id | What | Files | Output / acceptance |
|---|---|---|---|
| F0.1 | Deps + config | `pyproject.toml`, `app/config.py`, `.env.example` | `uv add fastapi httpx`; `uv add --dev pytest pytest-asyncio openapi-spec-validator` (while online). `Settings(auth_mode="demo", google_client_id="", admin_emails=[], media_dir="media", demo_now=None)` |
| F0.2 | Enums + model + errors | `domain/enums.py`, `domain/model.py`, `domain/errors.py` | dataclasses from [README §4](../../README.md); enum values = subset of full `openapi.yaml`; `DomainError(code, message)` |
| F0.3 | Ports | `application/ports.py` | `Repo` (get/add/list for Place, Observation, Report, QueueItem, Photo, User, Session; `states_for(place_id)`, `save_state`), `Clock.now()`, `IdGenerator.new(prefix)`, `FileStorage.save(stream, ext) -> Photo`, `IdentityVerifier.verify(id_token) -> GoogleIdentity` |
| F0.4 | In-memory adapters | `adapters/outbound/memory.py`, `adapters/outbound/files.py` | `InMemoryRepo`, `SystemClock`, `FixedClock(dt)`, `SeqIdGenerator` (`obs_1`, `obs_2`… deterministic), `LocalFileStorage(media_dir)` |
| F0.5 | Seed | `app/seed.py` | `load_seed(repo, clock)`: 4 places (`plc_mnk`, `plc_camelot`, `plc_ice`, `plc_urzad`); initial observations with `created_at = now − 60 days` (outside conflict window); demo accounts `anna, jan, ola, piotr, marek` (`user`) + `admin` (`admin`). States via `recompute` (until F3: stub, state = latest observation value) |
| F0.6 | App + errors + reset | `adapters/inbound/http/{main,errors,deps}.py`, `bootstrap.py` | `create_app(settings)`: lifespan builds container, calls `load_seed`. `DomainError → {"error": {code, message}}`, map 400/401/403/404/409. Routes under `/api/v1`. `GET /health`. `POST /api/v1/admin/demo/reset` (admin): clear repo, reload seed |
| F0.7 | Demo auth stub | `deps.py`, `auth` router | `POST /api/v1/auth/demo {"username"}` → `{token, user}` (token `demo-<username>`; only if `AUTH_MODE=demo`, else 404). `current_user` (optional), `require_user`, `require_admin`. Full contract in F1 |
| F0.8 | Scenario test (TDD) | `tests/api/test_demo_flow.py`, `tests/conftest.py` | 7 steps of [README §1](../../README.md) as separate tests, `@pytest.mark.xfail(strict=True)`, `httpx.AsyncClient(ASGITransport)` + `FixedClock(2026-10-03T12:00)`. `pytest` green (all xfail) |

## Rules

- After F0.2 + F0.3 (~30 min): **freeze model + ports**. Later changes by F0 owner only.
- `DEMO_NOW` → `FixedClock` on live demo too: "2 h ago" always the same.

## DoD

- `uv run uvicorn app.adapters.inbound.http.main:app` → `/docs`, `/health` OK; `GET /api/v1/places` still 404 (F2).
- `POST /api/v1/auth/demo {"username":"admin"}` + `POST /api/v1/admin/demo/reset` → 204.
- `pytest` green (xfail), STATUS.md updated, commit.
