# F20 — Similar places + accessible route A→B (heuristic)

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml)

## `GET /places/{id}/similar?limit=5`
"Podobne miejsca w okolicy": other places within 3 km, same category first, then nearest; `PlaceSummary` + `distance_m`; limit 1..20.

## `GET /routes/accessible?from=&to=&profile=wheelchair`
- `from`/`to`: `lat,lon` or a place id. **Heuristic, not a routing engine** (stated in `note`):
  - geometry = straight line; `distance_m` haversine; `duration_min` = ceil(distance / 50 m/min)
  - street-level features relevant to the profile, from places within **100 m** of the line:
    wheelchair/stroller/crutches → `lowered_curb`, `platform_elevator`; blind → `tactile_paths`, `lowered_curb`; low_vision → `good_lighting`; deaf/assistance_dog → none
  - state `no` → **barrier**, `yes` → **helper**
  - `feasible`: barriers → `partial`; data without barriers → `yes`; no data → `unknown`
- Pure `domain/route.py` (+ `geo.distance_to_segment_m`).
