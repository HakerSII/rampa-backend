# F35 — In-app notifications

Overview: [../../PLAN-GAPS.md](../../PLAN-GAPS.md) · contract: [openapi.yaml](openapi.yaml)

- Created inside use cases (the actor is never notified): `question_answered`, `report_reply`, `report_approved`, `observation_confirmed` / `observation_rejected` (conflict decision, per author), `ownership_decided`, `abuse_decided` (to reporters).
- `GET /me/notifications?unread=true` → `{items (newest first), unread}`; `POST /me/notifications/{id}/read` (204); `POST /me/notifications/read-all` → `{marked}`.
- Stored in `notifications` (SQL). Push / e-mail later (port ready: Mailer from F33).
