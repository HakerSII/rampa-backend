# F8 — OSM import + MCP client

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · needs: [F3](../03-observations-trust/plan.md), [F5](../05-open-api/plan.md)

## Scope

### OSM import (offline file)

- Port `OsmSource.fetch() -> list[OsmPoint]`; adapter `FileOsmSource` reads `data/osm_krakow_tauron.json` (snapshot made by `get_from_api.py`: `{name, wheelchair, toilet, category, lat, lon}`).
- Source `open_data`, trust weight **0.6** (community 0.5 < open data 0.6 < owner 0.85 < admin 1.0). Author: system user `usr_osm` ("OpenStreetMap").
- Mapping (pure, `domain/osm.py`):
  - `wheelchair`: `yes` → `step_free_entrance=yes`, `no` → `no`, `limited` → skipped (no `partial` in MVP)
  - `toilet` (`toilets:wheelchair`): `yes`/`no` → `accessible_toilet`; `brak danych` → nothing
  - `category`: OSM value; `inne` → `other`
- Places:
  - match: same `external_id` (`osm:<lat>,<lon>`) or same name (case-insensitive) within **50 m** → update existing
  - else create `plc_osm_N` (only if it has mappable data)
  - unnamed (`Brak nazwy`) → skipped (not a listable place)
- Idempotent: identical non-rejected `open_data` observation (place + feature + value) → not added again.
- `POST /api/v1/admin/imports {"source": "osm_file"}` (admin) → counts.

### MCP client (`clients/`)

- MCP server = **client of the Open API** (`/public/v1`, `X-Api-Key`), not in-process: separate process would have its own in-memory data.
- Tools: `check_accessibility(place_name, profile="wheelchair")`, `search_accessible_places(features)`.
- Logic in `clients/rampa_tools.py` (httpx, testable via ASGI), FastMCP wrapper in `clients/mcp_server.py` (optional extra `mcp`).
- Env: `RAMPA_API_URL` (default `http://localhost:8000`), `RAMPA_API_KEY` (default `demo-key`). Backend down → `{"error": ...}`, no crash.

## Tasks

| Id | What | Output / acceptance |
|---|---|---|
| F8.1 | 🔴 tests | `unit/test_osm.py` (mapping), `application/test_import.py` (create, idempotent, match MNK within 50 m, skip unnamed/limited, 403), `api/test_mcp_tools.py` (tools vs app via ASGI, backend down) |
| F8.2 | Domain + port + adapter | `OPEN_DATA`, `Place.external_id`, `domain/geo.py`, `domain/osm.py`, `OsmSource`, `FileOsmSource` |
| F8.3 | Use case + HTTP | `import_osm`, `POST /admin/imports` |
| F8.4 | MCP | `clients/rampa_tools.py`, `clients/mcp_server.py`, extra `mcp`, `.mcp.json` entry `rampa`; stdio smoke (initialize + tools/list) |
| F8.5 | e2e | demo.http: import → search tauron → check; 403 |

## DoD

Tests green, contract 8 specs, e2e verified, MCP lists tools, STATUS.md + commit.

> Cut: live Overpass adapter (timed out from corp network) — port ready, add `HttpxOsmSource` later.
