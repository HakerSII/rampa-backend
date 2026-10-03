# F27 — Live geocoding (Nominatim) + live OSM import (Overpass)

Overview: [../../README.md](../../README.md) · extends F8 (import) / F17 (geocode)

- `GEOCODER=local|nominatim` (default local). `GET /geocode`: local places first (they have accessibility data), then Nominatim hits limited to the Kraków viewbox (`place_id: null`); hits within 50 m of a local place dropped. Nominatim error / timeout → local only.
- `POST /admin/imports {"source": "overpass"}`: live Overpass query (named POIs with `wheelchair` / `toilets:wheelchair` around `OSM_CENTER_LAT/LON`, `OSM_RADIUS_M`). Error or empty → offline snapshot; `source` in the result says which one was used (`overpass` | `osm_file (fallback)`). `osm_file` unchanged.
- Adapters: `app/adapters/outbound/osm_live.py` (httpx, `User-Agent` per OSM usage policy, `EXTERNAL_TIMEOUT_S`). Tests use `httpx.MockTransport` — no network.
