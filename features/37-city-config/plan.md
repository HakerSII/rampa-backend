# F37 — City configuration (no Kraków in code)

Overview: [../../PLAN-GAPS.md](../../PLAN-GAPS.md) · contract: [openapi.yaml](openapi.yaml)

- `CITY_CONFIG` = JSON file (default `data/cities/krakow.json`): `name`, `viewbox [lon1, lat1, lon2, lat2]`, `center {lat, lon}`, `osm_radius_m`, `areas {key: {lat, lon, radius_m, words[]}}`, `category_groups {key: {categories[], words[]}}`. Validated at start (invalid → error, app does not start).
- Used by: Nominatim viewbox (F27), Overpass centre / radius (unless `OSM_CENTER_*` / `OSM_RADIUS_M` set), recommendation interpreter + areas (F30, rules and Claude tool enums).
- `GET /city` (public) → name, centre, viewbox, areas, category groups — the front end configures its map from it.
- Needs profiles stay an enum (they drive `check` rules); seed data stays Kraków demo data.
