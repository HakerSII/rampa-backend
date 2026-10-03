# F9 — Persistence: SQLite + SQLAlchemy

Overview: [../../README.md](../../README.md) · needs: all previous (Repo port unchanged) · no new endpoints (no openapi.yaml)

## Scope

- Data survives backend restart: places, observations (+votes), states, reports, photos meta, queue, users, sessions.
- `REPO_MODE=sql` (default for app) | `memory` (tests, ad-hoc). `DATABASE_URL=sqlite:///data/rampa.db`.
- Demo stays repeatable: `POST /admin/demo/reset` wipes DB back to seed.

## Design (decision)

- `Repo` port stays **sync**; use cases mutate domain objects in place (votes, validation, queue status, owner).
- `SqlRepo(InMemoryRepo)` = **write-behind cache**:
  - startup: `create_all`, load all rows into memory (ordered by `seq` → insertion order kept, tie-breaks unchanged)
  - `commit()`: rows of current state vs snapshot of last commit → insert / update / delete (portable SQLAlchemy Core, no dialect upsert)
  - HTTP middleware commits after every non-GET request (memory = source of truth, so commit even on 4xx)
- Bootstrap: DB empty → seed + commit; else load + `ids.observe()` all ids → new ids never collide.
- Sync SQLAlchemy (stdlib sqlite3): local writes ≈ ms, no async driver needed.
- Datetimes stored as ISO strings (SQLite drops tz on DateTime); lists/dicts as JSON.
- **Limit:** single process (1 uvicorn worker). Multi-worker / Postgres → fully SQL-backed repo later.

## Tasks

| Id | What | Output / acceptance |
|---|---|---|
| F9.1 | 🔴 tests | `adapters/test_sql_repo.py`: seed roundtrip (equal objects), mutations persist (votes, validation, queue, owner), clear → rows deleted, id continuity, types (enums, tz datetimes, JSON); `api/test_persistence.py`: report → restart app (same DB) → state kept; reset wipes |
| F9.2 | `commit()` / `is_empty()` / `all_ids()` on port + InMemory (no-op), `SeqIdGenerator.observe` | |
| F9.3 | `adapters/outbound/sql.py`: tables, converters, `SqlRepo` | F9.1 green |
| F9.4 | bootstrap + config + commit middleware; `/health` shows storage | whole API suite green also with `REPO_MODE=sql` |
| F9.5 | e2e | demo.http: health shows `storage: sql`; README restart note |

## DoD

Tests green in both modes, e2e verified, STATUS.md + commit.
