# F49 — Full place catalogue (Accessly main branch) in Rampa

Overview: [../../README.md](../../README.md) · extends F8 (OSM import)

## Why
- Accessly's main branch had ~6,500 clickable places on the map (its own catalogue, OSM); Rampa had only the seed.
- With Rampa as the only backend, the map must show the same catalogue: place → card → details → route.

## What
- `scripts/catalog_from_accessly.py` → `data/krakow_catalog.json`: every named place with category (Rampa key,
  round-trips to the UI category), address, phone, website and OSM accessibility facts (Rampa feature keys).
- `POST /api/v1/admin/imports {"source": "catalog"}` (admin) loads `CATALOG_FILE`: creates every named place, also
  without facts (shown like on main: at high zoom); facts → open-data observations; idempotent (same external id,
  or same name ≤ 50 m). Missing / invalid file → 400.

## Acceptance
- tests/application/test_catalog_import.py, tests/api/test_catalog_import_api.py
- e2e `requests/demo.http` F49
