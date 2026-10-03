# F31 — Needs profile on the server + sort best_match

Overview: [../../PLAN-GAPS.md](../../PLAN-GAPS.md) · contract: [openapi.yaml](openapi.yaml)

- `GET / PUT / DELETE /me/profile {needs: [NeedsProfile], features: [FeatureKey]}` — needs only, no diagnoses (GDPR); max 10 each; works for anonymous device accounts too. Stored in `users.needs`, `users.pref_features` (SQL, auto-added columns).
- `GET /places?sort=best_match[&profile=wheelchair,blind]` — profile from the parameter, else the logged-in user's stored needs; none → 400. Order: `check` answer yes > partial > unknown > no, ties by distance / name. Items get `match`.
- `POST /ai/recommend` merges the stored needs + features of a logged-in user.
