# F36 — Admin: new-place queue, activity, trends, coverage

Overview: [../../PLAN-GAPS.md](../../PLAN-GAPS.md) · contract: [openapi.yaml](openapi.yaml)

- Places created by non-admins (`POST /places/resolve`) → queue item `type: new_place` (`feature: null`). `confirm` → accepted; `reject` → place deleted **only without observations** (else 409 — merge instead, observations are never deleted); `POST /admin/places/{id}/merge` resolves it as `merged`. Filter `filter=new_place`, `counts.new_place`.
- `GET /admin/activity?days=30&cell_deg=0.005[&bbox]` → grid cells `{lat, lon, observations, reports}` (cell centres, busiest first).
- `GET /admin/trends?days=30` → per day `{day, observations, reports, questions, queue_items}` oldest → newest (1..365).
- `GET /admin/coverage` → per category `{places, with_data, avg_known_features}` + `most_missing` (core features unknown in most places).
