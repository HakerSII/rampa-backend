# F54 + F55 — Account settings and reviews (as on the Accessly main branch)

Overview: [../../README.md](../../README.md)

## Why
The app's main branch has "Ustawienia konta" (name, delete account) and an "Opinie" tab (stars + text) on the
place card; with Rampa as the only backend these need Rampa endpoints.

## What
- F54 `PATCH /api/v1/me` `{display_name}` (1–60 chars, plain text) → user; `DELETE /api/v1/me` → 204: every session
  ends, favourites / needs profile / reviews are deleted, e-mail and Google id are forgotten; observations, reports
  and questions stay, shown as "Usunięty użytkownik".
- F55 `GET /api/v1/places/{id}/reviews` (guest) → `{items, count, average, mine}`; `PUT /api/v1/places/{id}/reviews/me`
  `{rating 1–5, text ≤ 500}` (an account: e-mail / Google / demo — this device's anonymous identity → 403);
  `DELETE …/reviews/me`. One review per account and place (PUT replaces). `rating: {avg, count} | null` on the place
  and in the place list.

## Acceptance
- tests/api/test_account_reviews_api.py; e2e `requests/demo.http` F54–F55
