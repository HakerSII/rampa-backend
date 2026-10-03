# F13 — Admin panel: stats tiles + audit history

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · needs: F4, F7

## Scope

- `GET /admin/stats` (admin) — tiles from the mockup, `{value, change_pct}` (today vs yesterday, `null` if yesterday = 0), pure `domain/stats.py`:
  - `new_reports_today`, `data_conflicts` (value = open items; change = opened today vs yesterday), `low_confidence` (known feature states with confidence < 0.5), `observations_today`, `places` + `updated_at`
  - "Zgłoszenia nadużyć" (abuse) **not included** — no flagging in MVP
- `GET /places/{id}/history` (admin, or owner of the place) — audit trail newest first, pure `domain/history.py`:
  - `observation_added` per observation (incl. rejected, with final validation + votes)
  - `conflict_detected` (queue item created), `conflict_resolved` (decision + `resolved_at`)
- `QueueItem.resolved_at` (set by decision). **Schema evolution**: `SqlRepo` adds missing nullable columns to existing tables on start (SQLite + Postgres DBs already exist).

## Tasks

| Id | What |
|---|---|
| F13.1 | 🔴 `unit/test_stats.py`, `unit/test_history.py`, `application/test_admin_panel.py`, `adapters/test_sql_repo.py::test_adds_missing_columns` |
| F13.2 | domain stats/history, `resolved_at`, SqlRepo column migration, use cases, HTTP, contract, e2e, docs |
