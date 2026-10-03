# F28 — Walking route from a routing engine (OSRM), fallback straight line

Overview: [../../README.md](../../README.md) · extends F20 (accessible route)

- `ROUTER=straight|osrm` (default straight). `GET /route`: with `osrm`, geometry / distance / duration come from an OSRM `foot` server (`OSRM_URL`, default FOSSGIS `routing.openstreetmap.de/routed-foot`).
- Barriers / helpers = street-level features of places within 100 m of **any segment of the real path** (not the straight line). New field `engine: osrm | straight_line`.
- OSRM error, timeout or `NoRoute` → straight-line heuristic (same answer as before, `engine: straight_line`).
