# F22 — Owner panel extras (mockup "Panel właściciela")

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · needs: F7

| Endpoint | Behaviour |
|---|---|
| `GET/PATCH /owner/me` | profile `{id, display_name, email, role, verified, places}`; PATCH name/e-mail |
| `GET /owner/stats` | `managed_places`, `avg_confidence`, `reports_30d` (submitted on my places), `updates_30d` (my verified_owner observations), `open_conflicts` |
| `PATCH /owner/places/{id}` | name, short_description, address, category, contact `{phone, website, email}` |
| `PUT /owner/places/{id}/opening-hours` | `[{days, open, close, closed}]` (HH:MM, open < close) |
| `POST /owner/places/{id}/photos {photo_id}` · `DELETE …/photos/{photoId}` | owner photos in the place gallery (`kind: owner`) |
| `GET /owner/places/{id}/stats` | observations by source, votes up/down, open conflicts, last_verified, confidence |
| `POST /owner/reports/{id}/reply {text}` | reply visible on the report (`replies`) |
| `POST /owner/reports/{id}/approve` | owner confirms → `verified_owner` observation with the report's value; `owner_status: approved` |
| `GET /owner/reminders` | missing features (unknown), stale (>90 days), open conflicts, reports without reply |
| `GET /owner/suggestions` | features that are `no` on my places → "Rozważ: …" |
| `POST /owner/observations/batch` | `[{place_id, feature, value, …}]` (1..50) across own places; all-or-nothing |
| `GET /owner/places/import/template` | CSV header `place_id,feature,value,temporary,comment` |
| `POST /owner/places/import` (multipart CSV) | valid rows imported (verified_owner), `errors: [{row, message}]` |

All owner endpoints: role owner + owner of the place (else 403). New fields (`Place.opening_hours/contact/photo_ids`, `Report.replies/owner_status`) persisted, auto-migrated.
