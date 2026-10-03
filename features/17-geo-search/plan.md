# F17 — Location search, map markers, categories, geocode

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · extends F2 `GET /places`

## Scope

- `GET /places` new params (all optional, old calls unchanged):
  - `lat`, `lon` (together) → `distance_m` on items; `radius_m` (default 2000 when lat/lon given)
  - `bbox=minLon,minLat,maxLon,maxLat` (map viewport)
  - `sort=nearest|name|recently_verified` (default: `nearest` with lat/lon, else seed/insertion order); `nearest` without lat/lon → 400
  - `page` (≥1), `page_size` (1..100, default 20) → `total` = all matches
  - `view=map` → `{ total, items: [ { id, name, location, category, marker } ] }`, marker from wheelchair check: `accessible|partial|inaccessible|unknown`
- `GET /categories` → `[ { key, label, count } ]` (labels PL, OSM keys fall back to key)
- `GET /geocode?q=` (≥2 chars) → `[ { label, place_id, location } ]`, max 10 — **local index** (place names + addresses), no Nominatim (offline demo)
- Domain: `geo.parse_bbox`, `geo.in_bbox`.
