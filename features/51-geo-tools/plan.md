# F51 — Find a location and what is within 500 m (Open API + MCP tools + chat)

Overview: [../../README.md](../../README.md) · extends F5 (Open API), F8/F41 (MCP), F27 (geocoder), F46 (chat)

## Why
- The UI's search box finds any address (Nominatim); the assistant could only look places up by name.
- "Czy do X wjadę?" for a place missing from the database ended with "nie znaleziono"; it should show what is around.

## What
- Open API (X-Api-Key): `GET /public/v1/geocode?q=` → `{items: [{label, lat, lon, place_id}]}` (places of the database
  first, then the geocoder — `GEOCODER=nominatim`, bounded to the city like the UI);
  `GET /public/v1/places/nearby?lat&lon&radius_m=500&features=` → places within the radius (50–2000 m), nearest first,
  with `distance_m`, address and accessibility summary.
- MCP tools (server + chat): `find_location(query)`, `places_nearby(lat, lon, radius_m=500)`.
- Chat: after `find_location` the assistant itself calls `places_nearby` for the first location (500 m);
  "co jest w pobliżu / koło / blisko X" goes that way; a place not found by name → its location + surroundings.

## Acceptance
- tests/api/test_geo_tools.py, tests/application/test_chat.py (F51 cases); e2e `requests/demo.http` F51
