# F12 — Front-end bridge: anonymous identity + pin → place

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · needs: [F1](../01-auth/plan.md), [F3](../03-observations-trust/plan.md), [F8](../08-osm-mcp/plan.md)

## Why

The map front end (repo `Yannie-draft-acihy`, "Bez Przeszkód Kraków") is barrier-centric: a user drops a pin
anywhere, no account, and votes are deduplicated per device. This API is place-centric and every write needs a
user. Two gaps block a connection:

1. **No `place_id` for a pin on the street.** The front end already derives a place name (nearest city stop
   within 40 m, else Nominatim reverse geocoding), so it can ask for a place by name + coordinates.
2. **No identity without Google.** One shared demo account would break votes (one vote per user, no vote on
   own observation). A device needs its own `user`.

## Scope

- `POST /auth/anonymous {display_name?}` → `201 {token, user}`: a fresh `user` ("Anonim" by default) with a
  session of `ANONYMOUS_TTL_DAYS` (365). Works in every `AUTH_MODE`; `ANONYMOUS_AUTH=false` → 404.
  One call = one user; the front end stores the token (`localStorage`) and sends it as `Bearer`.
- `POST /places/resolve {name, lat, lon, category?, address?}` (user) → `{place, created}`:
  the same name (case-insensitive) within **50 m** (`domain.osm.MATCH_RADIUS_M`, the OSM import rule) is the
  same place → 200; otherwise a new `plc_N` → 201. Name 1..120 chars, coordinates validated by `GeoPoint`.
- Refactor: `_match_place(OsmPoint)` → `_find_place(name, location, external_id=None)` shared with the import.

## Not in scope (next steps of the bridge)

- Front-end types with no feature here (`escalator`, `tactile`, `sign`, `other`) → new `FeatureKey`s or drop.
- Bounding-box search (`GET /places?bbox=`) once places outnumber a single map load.
- Public data layers (`/api/layers`) — port `layers.py` from the front-end repo.
- TTL / expiry of reports (front end has it, this API relies on `temporary` + moderation).

## Tasks

| Id | What | Output / acceptance |
|---|---|---|
| F12.1 | 🔴 tests | `application/test_auth.py` (anonymous: role, distinct users, 365 d TTL, google mode, disabled), `application/test_places.py` (resolve: create, match ≤50 m case-insensitive, far → new, validation, guest 401, report on resolved place), `api/test_frontend_bridge.py` (two devices: resolve → report → vote, guest reads) |
| F12.2 | Use cases + config | `login_anonymous`, `resolve_place`, `_find_place`; `ANONYMOUS_AUTH`, `ANONYMOUS_TTL_DAYS` |
| F12.3 | HTTP | `routers/auth.py`, `routers/places.py`, schemas; category label `other` → "Inne" |
| F12.4 | Contract + docs | this `openapi.yaml` (contract test → 9 specs), `docs/openapi.json`, `docs/api.md`, `docs/configuration.md`, `.env.example`, `demo.http` section |

## DoD

Tests green in both repo modes, contract test 9 specs, STATUS.md + commit.
