# F18 — Report drafts ("Zapisz szkic")

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · extends F3

- `POST /reports` + `"draft": true` → `status: draft`; only `place_id` required, other fields optional (validated if given); **no observation, state unchanged**.
- `PATCH /reports/{id}` — author only (else 403), draft only (else 409); partial update, each field validated.
- `POST /reports/{id}/submit` — author only, draft only (409); full validation (400 lists missing fields) → observation + recompute (same as F3).
- Without `draft` → unchanged F3 behaviour (submitted immediately; demo flow untouched).
- Drafts: visible in `GET /me/reports` (author); excluded from owner reports and admin stats.
- Report fields nullable in model + SQL (drafts).
