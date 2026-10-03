# F21 — Admin extras

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · needs: F4, F7, F13

| Endpoint | Behaviour |
|---|---|
| `GET /admin/places/{id}/confidence` | widget "Pewność danych": `overall` (mean of known features), `by_group` (mean per group), `note` |
| `POST /admin/queue/{id}/comments {text}` | moderator comment (1..1000) → stored on the queue item (`comments`, shown in detail) |
| `POST /admin/observations/{id}/flag {reason}` | abuse/spam → `validation: FLAGGED` + `flag_reason`; excluded from trust and conflicts (like REJECTED); state recomputed; stats tile `abuse_flags` (flagged today) |
| `POST /admin/places/{id}/merge {into_place_id}` | duplicate → target: moves observations, reports, queue items, favourites; deletes the duplicate; recomputes target |
| `POST /admin/revalidate` | recompute all states (validation + trust) → `{places, features}` |
| `POST /owner/ownership-requests {place_id, justification}` (any user) · `GET /admin/ownership-requests?status=` · `POST /admin/ownership-requests/{id}/verify {approved}` | "owner applies → admin verifies"; approved → owner assigned (user promoted); second decision → 409 |

Domain: `ValidationStatus.FLAGGED`, `validation.INACTIVE = {REJECTED, FLAGGED}`; `Observation.flag_reason`; `QueueItem.comments`; `OwnershipRequest`. SQL: new columns auto-migrated, new table `ownership_requests`.
