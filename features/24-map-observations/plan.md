# F24 — Map observations in one request (front-end request)

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml)

`GET /api/v1/observations` (guest allowed) — observations across places, newest first, each with `place {id, name, location}` and `severity` (from the report it came from, else `null`).

| Param | Meaning |
|---|---|
| `active` (default `true`) | exclude REJECTED / FLAGGED / expired (`valid_until` passed) |
| `bbox` | `minLon,minLat,maxLon,maxLat` on the place location |
| `feature`, `value` | filter (`value=no` = problems) |
| `current=true` | only observations that currently decide their feature state (`active_observation_id`) |
| `since` | ISO date-time |
| `limit` | 1..500 (default 200) |

Replaces per-place `GET /places/{id}/observations` loops in the map front end.
