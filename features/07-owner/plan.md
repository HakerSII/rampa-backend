# F7 — Owner role + verified_owner observations

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · needs: [F3](../03-observations-trust/plan.md), [F4](../04-admin-queue/plan.md)

## Scope

- Role `owner`; source `verified_owner` (trust weight **0.85**, between community 0.5 and admin 1.0).
- `Place.owner_id`. Seed: `ewa` (Ewa Nowak, owner) owns `plc_mnk`, `plc_camelot`.
- Owner **never overwrites** state or user reports — adds observations like everyone else, just with higher weight.
- Source by author: admin → `admin`; owner of this place → `verified_owner` (also via generic `POST /places/{id}/observations`); else `community`.
- Endpoints:
  - `GET /owner/places` — my places (owner only)
  - `POST /owner/places/{id}/observations {observations: [...]}` — batch update ("Zaktualizuj dane"), 1..10 items, must own place
  - `GET /owner/reports` — user reports on my places, newest first
  - `POST /admin/places/{id}/owner {user_id}` — admin assigns owner; `user` → promoted to `owner`

## Scenario (owner variant, demo.http section F7)

1. reset → anna: elevator broken + photo (0.6) → jan/ola/piotr 👍 (0.9)
2. ewa (owner): "elevator repaired" → `verified_owner`, 0.85 → conflict (owner vs users), state stays `no` (0.9 > 0.85)
3. admin confirms ewa → `yes`, 1.0

## Tasks

| Id | What | Output / acceptance |
|---|---|---|
| F7.1 | 🔴 tests | trust weight 0.85; owner places/obs/reports; non-owner 403; anna on `/owner/*` 403; owner vs users → queue; generic endpoint by owner → `verified_owner`; admin assign → role owner; batch validation |
| F7.2 | Domain + seed | `Role.OWNER`, `ObservationSource.VERIFIED_OWNER`, weight, `Place.owner_id`, seed `ewa` |
| F7.3 | Use cases + HTTP | `list_owner_places`, `add_owner_observations`, `list_owner_reports`, `assign_owner`; `routers/owner.py` |
| F7.4 | e2e | demo.http "F7 owner" section + 403 cases |

## DoD

Tests green, contract test 7 specs, e2e verified, STATUS.md + commit.

> Diff vs full plan: no `ownership-requests` flow (owner asks → admin verifies). MVP: admin assigns directly. Owner panel stats, reminders, suggestions, CSV import — later.
