# F26 — Escalate + abuse reports from users

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · extends F4/F21

- `decision.action = escalate` → item `status: escalated` (handed to a coordinator), data unchanged, can still be decided; a new contradicting observation extends the escalated item.
- `POST /observations/{id}/abuse {reason}` — any user (not the author, once per user) → queue item `type: abuse` (reasons kept as comments). Admin `confirm` → observation FLAGGED (reason = reports); `reject` → dismissed.
- Queue: `filter=all|conflict|abuse`, `status=open|escalated|resolved|all`; counts per type. Conflict lookups, dashboard conflicts, owner stats and reminders count only `type: conflict`.
