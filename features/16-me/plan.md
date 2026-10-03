# F16 — Me: favourites + my reports

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml)

- `User.favorite_place_ids` (persisted as JSON column `users.favorites`; added to existing DBs by the column migration).
- `GET /me/favorites` → `{items: [PlaceSummary]}` (with verification) · `PUT /me/favorites/{placeId}` → 204 (idempotent) · `DELETE /me/favorites/{placeId}` → 204 (idempotent) · unknown place → 404 · no token → 401.
- `GET /me/reports` → `{items: [Report]}` mine, newest first.
- Mockup: "Dodaj do ulubionych" heart on the place screen.
