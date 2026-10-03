# F12 — Place screen (mockup: details page)

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · needs: F3, F7, F8

## Scope (computed from existing data, no new storage)

- **Verification block** on `PlaceSummary` / `Place` (`verification`), pure `domain/verification.py`:
  - from known feature states: `last_verified` = newest, `confidence` = mean, level `high` ≥0.8 · `medium` ≥0.5 · `low`
  - `status`: `conflict` (any state CONFLICT) · `confirmed` (≤1 day) · `verified_recently` (≤30 days) · `needs_update` (>90 days) · `verified` (else) · `unverified` (no data)
  - `label` (PL): "Sprzeczne zgłoszenia" · "Potwierdzone dzisiaj" · "Zweryfikowane N dni temu" · "Wymaga aktualizacji" · "Brak danych"
  - `sources`: distinct sources of active observations
- `GET /places/{id}/activity?limit=20` — feed "Ostatnie zgłoszenia i potwierdzenia", newest first, one item per observation: `type` = `issue_reported` (community no) · `confirmation` (community yes) · `owner_update` · `admin_decision` · `open_data_import` · `initial_data` (seed); + label, feature, value, author ("Anna K."), comment, photo, votes up, validation, created_at
- `GET /places/{id}/photos` — gallery: evidence photos of the place's observations, newest first, with author + feature + date

## Tasks

| Id | What |
|---|---|
| F12.1 | 🔴 `unit/test_verification.py`, `application/test_place_screen.py` |
| F12.2 | domain `verification.py`, `activity_type`; use cases `place_activity`, `place_photos`, `verification_for` |
| F12.3 | HTTP + schemas, contract, e2e (demo.http steps 2 + 7d/7e), docs/api.md |
