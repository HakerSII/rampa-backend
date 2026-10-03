# F2 — Places, search, check

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · needs: [F0](../00-skeleton/plan.md) (not F1 — public endpoints, guest OK)

## Scope

- Place list with feature filter, place details, accessibility state, simple "can I get in" (`check`) for `wheelchair` only.
- No route A→B, no OSM, no geocoding. Data from seed.
- Read-only: states come from F0 seed via `recompute` (F3 replaces stub with real trust; API unchanged).

## Model (from [README §4](../../README.md))

- `Place`, `FeatureStateRecord` (computed, read-only here).
- `FeatureKey` (5): `step_free_entrance`, `ramp` → group `entrance`; `elevator` → `inside`; `accessible_toilet` → `toilet`; `induction_loop` → `hearing`.
- Seed (F0.5): `plc_mnk` (all 5 yes), `plc_camelot` (ramp yes, toilet unknown), `plc_ice` (step-free yes, elevator no), `plc_urzad` (step-free no, ramp no, induction loop yes).

## `check` rules (wheelchair)

| entrance = step_free_entrance OR ramp | elevator | answer |
|---|---|---|
| any `yes` | not `no` | `yes` |
| any `yes` | `no` (incl. temporary) | `partial` (get in, not upstairs) |
| all known `no`, none `yes` | — | `no` |
| no data | — | `unknown` |

- Answer enum = subset of full `CheckResult.answer` (`yes, partial, no, unknown`; no `likely_yes` in MVP).
- `reasons[]` = states used; `active_issues[]` = temporary `no` observations.
- `confidence` = min confidence of states used (0 if unknown).

## Use cases

- `search_places(features: list[FeatureKey] | None, category: str | None, q: str | None) -> list[PlaceSummary]` — `features` AND, state must be `yes`.
- `get_place(place_id) -> Place` — `NotFound` → 404.
- `get_accessibility(place_id) -> Accessibility` — grouped like full contract (`groups[].features[]`); all 5 features listed, missing = `unknown`.
- `check_place(place_id, profile) -> CheckResult` — logic in `domain/check.py` (pure).
- `list_features(lang) -> groups` — static, PL labels.

## Tasks

| Id | What | Output / acceptance |
|---|---|---|
| F2.1 | 🔴 `tests/unit/test_check.py` | 4 cases from table + unknown-only → `unknown` |
| F2.2 | `domain/check.py::check_place(states, profile) -> CheckResult` | F2.1 green |
| F2.3 | 🔴 → 🟢 use cases | `tests/application/test_use_cases.py::test_search_*`: filter `step_free_entrance` → `plc_mnk`, `plc_ice`, not `plc_urzad`; unknown id → `NotFound` |
| F2.4 | HTTP + schemas | `GET /places`, `/places/{id}`, `/places/{id}/accessibility`, `/places/{id}/check`, `/accessibility/features` per [openapi.yaml](openapi.yaml). `features` = CSV query param |
| F2.5 | Demo steps 1–3 | remove `xfail` from steps 1–3 in `test_demo_flow.py` → green |

## DoD

- `GET /places?features=step_free_entrance` → only places with that feature `yes`.
- `GET /places/nope` → 404 `{"error": {"code": "NOT_FOUND"}}`.
- `GET /places/plc_mnk/check?profile=wheelchair` → `yes`, consistent with `/accessibility`.
- Steps 1–3 green, STATUS.md + commit.

> Diff vs full contract: `FeatureStateValue` without `partial`; `NeedsProfile` = `wheelchair` only; `CheckResult.answer` without `likely_yes`. Names unchanged → merge without migration.
