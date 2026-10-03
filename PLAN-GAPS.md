# Plan — backend gaps vs "Accessly – opis projektu" (2026-10-03)

Source: comparison of the Accessly project description with this backend. Backend only.
Rules unchanged: TDD (red commit → green), hexagon, `STATUS.md` + local commit per step, e2e in `requests/demo.http`, docs + `docs/openapi.json`, external services opt-in with offline fallback.
Order = value / cost. Estimates are rough.

| # | Task | Doc area | Est. | Priority | Status |
|---|---|---|---|---|---|
| F30 | AI recommendations endpoint | I | 2 h | MVP | done |
| F31 | Needs profile on server + sort `best_match` | C, D | 1.5 h | MVP | done |
| F32 | Value `n/a` + missing attributes | A | 1 h | MVP | done |
| F33 | Email magic-link login | D | 1.5 h | MVP | done |
| F34 | Questions to owner + needs stats | F | 2 h | later | done |
| F35 | In-app notifications | D | 1.5 h | later | done |
| F36 | Admin: new-place queue, activity map, trends | H | 2 h | later | done |
| F37 | City config (no Kraków in code) | K | 1 h | later | done |
| F38 | PostGIS radius search + Alembic migrations | decisions | 3 h | later | deferred — see note |
| F39 | City open-data import | A | ? | blocked: dataset choice | blocked |

## F30 — AI recommendations (`POST /api/v1/ai/recommend`)
- **In:** `{query: "restauracja w centrum, wózek dziecięcy i pies", profile?: NeedsProfile, lat?, lon?, limit?: 5}`; logged-in user → stored profile (F31) merged.
- **Out:** `{needs: [...], filters: {category, features, near}, items: [{place, match: yes|partial|unknown, reasons: [{feature, state, source, last_verified}], missing: [feature…]}], note}`.
- **How:** port `QueryInterpreter`; default adapter = rules (PL/EN keywords → profile, category, features; reuse `text_parse` / `suggestions`); optional `AI_RECOMMENDER=claude` → Claude API (model from config, default Sonnet 5.5) with tool use calling our search only. Ranking + reasons + missing computed in the domain from DB data, never from the model. Model failure → rules.
- **Accept:** answers cite only DB attributes; unknown/stale → `missing`; deterministic in mock; test set of ~10 queries.
- **Risk:** hallucination → model only produces filters, never facts. Cost → only on request, timeout.

## F31 — Needs profile on server + `sort=best_match`
- **In:** `GET/PUT /api/v1/me/profile {needs: [wheelchair, stroller, assistance_dog, …], preferences: {features: [...]}}` — needs only, no diagnoses (GDPR); anonymous device account works too.
- **Out:** `GET /places?sort=best_match[&profile=]` → stored or given profile; score from `check` (yes > partial > unknown > no) + data freshness; item gets `match`.
- **Accept:** stored profile survives restart (SQL column); `DELETE /me` removes the profile.

## F32 — `n/a` + missing attributes
- `ObservationValue/StateValue.NOT_APPLICABLE` ("nie dotyczy"): not a barrier, not counted as missing.
- New features: `baby_changing_table`, `stroller_space`, `luggage_storage`, `rest_areas` (+ PL labels, groups, OSM `changing_table` → `baby_changing_table`, `dog` → `pets_allowed`).
- Update specs enum, contract test, `/accessibility/features`.

## F33 — Email magic link
- `POST /auth/email/request {email}` → one-time token (15 min, single use); port `Mailer`: `console` (dev, logs link) | `smtp` (env). `POST /auth/email/verify {token}` → session. Same user as Google login by email.
- **Accept:** expired/used token → 401; rate limit per email.

## F34 — Questions to owner
- `POST /places/{id}/questions {feature?, text}`; owner `GET /owner/questions`, `POST /owner/questions/{id}/answer {text, observation?: {feature, value}}` (answer can set the attribute as owner observation, or mark `planned`).
- Stats: `GET /owner/places/{id}/stats` + admin `GET /admin/needs-stats` (most asked features).

## F35 — Notifications (in-app)
- `GET /me/notifications`, `POST /me/notifications/{id}/read`. Events: report status changed, owner replied, question answered, ownership decided, abuse decided. Push / e-mail later.

## F36 — Admin extras
- Queue type `new_place` (places created by users via `/places/resolve` or reports) → confirm / reject / merge.
- `GET /admin/activity?bbox&days` (observations per grid cell), `GET /admin/trends?days=30` (per-day counts), coverage per category, most missing attributes.

## F37 — City config
- `CITY_NAME`, `CITY_VIEWBOX`, `CITY_CENTER`, categories + profiles from a JSON file (`CITY_CONFIG`); Kraków = default file.

## F38 — PostGIS + Alembic (infra) — DEFERRED (2026-10-03)
Why deferred: the repository is a write-behind cache (all data in memory, F9/F29), so radius / bbox search runs in
memory and PostGIS would not be used until a fully SQL-backed repository exists. Postgres cannot be verified locally
right now (Docker stopped), and replacing the working auto-migration (`_add_missing_columns`, also used on Render)
without a Postgres test is a demo risk. Order when picked up: SQL-backed repo → Alembic baseline → PostGIS queries.

- Postgres only: geography column + GIST index, radius/bbox in SQL; SQLite keeps Python fallback. Alembic baseline from current schema; replace `_add_missing_columns`. Needs PostGIS on Render (check plan).

## F39 — City open data
- Blocked: pick dataset(s) (e.g. city BIP / ZTP stops) and licence. Then adapter like `osm_file` with source `open_data` + source name per value.

## Not backend (out of scope here)
Map, list, card, filters UI, branding, card actions (call / share), WCAG audit — front end.
