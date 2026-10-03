# F34 — Questions to the owner + needs statistics

Overview: [../../PLAN-GAPS.md](../../PLAN-GAPS.md) · contract: [openapi.yaml](openapi.yaml)

- `POST /places/{id}/questions {text, feature?}` (user) → open question; `GET /places/{id}/questions` public Q&A (newest first).
- Owner of the place (or admin): `GET /owner/questions?status=open|answered|all`, `POST /owner/questions/{id}/answer {text, value?, planned?}`. `value` → verified_owner observation (state changes through the normal trust flow); `planned` → outcome `planned`, data unchanged; one answer per question.
- `GET /admin/needs-stats` (admin: all places; owner: own places) → most asked features, open / answered, questions without a feature. Owner reminders get `unanswered_question`.
