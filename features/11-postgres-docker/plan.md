# F11 — Postgres + docker-compose, DB choice via env/config

Overview: [../../README.md](../../README.md) · needs: [F9](../09-sqlite/plan.md) · no new endpoints

## Scope

- DB choice in `app/config.py` / env:
  - `REPO_MODE=sql|memory`
  - `DB_ENGINE=sqlite|postgres` (default `sqlite`)
  - `SQLITE_PATH` (default `data/rampa.db`)
  - `POSTGRES_HOST|PORT|USER|PASSWORD|DB` (defaults `localhost`, `5432`, `rampa`, `rampa`, `rampa`)
  - `DATABASE_URL` — optional override, any SQLAlchemy URL (wins over the above)
  - effective URL = `Settings.db_url` (password URL-escaped)
- Same `SqlRepo` (SQLAlchemy Core) on Postgres via `psycopg` (optional extra `postgres`); connect retries on start (DB may still boot); `pool_pre_ping`.
- `/health` adds `database: sqlite|postgresql` (no credentials).
- Docker:
  - `Dockerfile`: python 3.13-slim + uv, `uv sync --frozen --no-dev --extra postgres`, `uvicorn main:app` (1 worker — write-behind cache is single-process)
  - `.dockerignore`: **`.env` never in image**, no `.venv`, `models/`, `media/`, `data/*.db`
  - `docker-compose.yml`: `db` (postgres:17-alpine, healthcheck, volume `pgdata`) + `api` (depends on healthy db, `DB_ENGINE=postgres`, AI/auth settings passed from `.env` by interpolation, volume `media`)

## Tasks

| Id | What | Acceptance |
|---|---|---|
| F11.1 | 🔴 tests | `unit/test_config.py` (URL building, escaping, override); `adapters/test_sql_repo.py` parametrized sqlite + postgres (`TEST_POSTGRES_URL`, else skip); `api/test_docker.py` (compose structure, .dockerignore has .env) |
| F11.2 | config, bootstrap, SqlRepo retry, extra `postgres`, health | green |
| F11.3 | Dockerfile, .dockerignore, docker-compose.yml | `docker compose config` valid |
| F11.4 | docs + e2e (health shows database) | docs/configuration, operations, architecture |
| F11.5 | **manual (needs Docker Desktop)** | `docker compose up -d --build` → demo.http green on Postgres; `TEST_POSTGRES_URL=… uv run --extra postgres pytest tests/adapters` |
