# F5 — Open API (read-only, for external apps)

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · needs: [F2](../02-places-search/plan.md)

## Scope

- Read-only API for city apps, transport systems, NGOs. Pitch point: "data is open, not locked in our app".
- Same use cases as F2 (`search_places`, `get_place`, `get_accessibility`, `check_place`) — new inbound adapter only, zero domain changes.
- Auth: `X-Api-Key` header, keys from `PUBLIC_API_KEYS` (comma list; default `demo-key` for demo).
- Rate limit: fixed window, `PUBLIC_RATE_LIMIT_PER_MIN` (default 60) per key → 429 `RATE_LIMITED`. In-memory, per process.
- Mounted at **`/public/v1`** (root, not under `/api/v1`).

## Flat accessibility format

```json
{
  "place": { "id": "plc_mnk", "name": "Muzeum Narodowe w Krakowie" },
  "accessibility": {
    "step_free_entrance": { "value": true, "temporary": false, "confidence": 0.5, "last_verified": "2026-08-04" },
    "elevator": { "value": false, "temporary": true, "confidence": 0.9, "last_verified": "2026-10-03" }
  }
}
```

- `yes → true`, `no → false`, `unknown` → omitted.
- `last_verified` = date only.

## Tasks

| Id | What | Output / acceptance |
|---|---|---|
| F5.1 | 🔴 `tests/api/test_public_api.py` | no key / wrong key → 401; flat format for `plc_mnk` + `plc_camelot` (unknown omitted); search with features; check; limit 3/min → 4th = 429; demo state change visible in public API |
| F5.2 | Config + key/limit dependency | `PUBLIC_API_KEYS`, `PUBLIC_RATE_LIMIT_PER_MIN`; `RateLimited` → 429 |
| F5.3 | `routers/public.py` + flat schema | per [openapi.yaml](openapi.yaml); contract test covers 5 specs |
| F5.4 | `requests/demo.http` section | public calls + 401 case |

## DoD

- F5.1 green, contract test green (5 specs), demo.http section works.
- STATUS.md + commit.

> Diff vs full contract: full `openapi.yaml` lists `/public/v1/*` under server `/api/v1` (→ `/api/v1/public/v1/...`). MVP mounts at `/public/v1` — shorter, versioned separately from the internal API. Align full contract on merge.
