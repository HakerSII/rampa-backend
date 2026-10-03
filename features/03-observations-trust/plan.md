# F3 — Observations, votes, trust (MVP core)

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · needs: [F0](../00-skeleton/plan.md); F1 only for real login (demo stub enough)

## Scope

- Every input = `Observation`. Feature state **computed**: observations → validation → trust → `FeatureStateRecord`.
- Report with photo → observation(s). Quick observation (no form). Votes 👍/👎. Conflict detection → `QueueItem` (consumed by F4).
- Replaces F0 `recompute` stub; F2 API unchanged.

## Trust (MVP formula) — `domain/trust.py`

- Observation confidence:
  - base by source: `admin` 1.0, `community` 0.5
  - `+0.1` if evidence (≥1 photo)
  - `+0.1` per 👍 (max `+0.3`), `−0.1` per 👎
  - clamp `[0, 1]`; no age decay (cut)
- Feature state:
  - ignore `REJECTED`
  - winner = highest confidence; tie → newer
  - `state` = winner value; `temporary`, `confidence`, `last_verified` (= winner `created_at` or latest vote), `active_observation_id` from winner
  - `sources_count` = distinct authors of non-rejected observations
  - no observations → `unknown`, confidence 0
  - `validation` = `CONFLICT` if open conflict on feature, else `VALID`

## Validation — `domain/validation.py`

- Window: non-rejected observations with `created_at ≥ now − 30 days`.
- Conflict = window has ≥2 distinct values AND ≥2 distinct authors.
- On conflict: observations in window → `validation=CONFLICT`; open `QueueItem(type="conflict")` for place+feature, **one open item per place+feature** (append ids if exists).
- Seed observations are 60 days old → outside window → first new report never conflicts with seed.

## Invariants

1. State never set by hand; always `compute_feature_state`.
2. Observations never deleted; only `validation` changes.
3. One vote per user per observation (re-vote replaces); author can't vote own → `ValidationFailed`.
4. Writes atomic: one sync block per use case (no `await` between read-modify-write).

## Use cases

```python
upload_photo(user, stream, filename) -> Photo                  # PNG/JPG magic bytes, ≤10 MB streamed; else ValidationFailed / 413
create_report(user, ReportInput) -> Report                     # status=submitted; creates 1 observation
#   element → feature; current_state works→yes, not_working→no; nature=temporary → temporary=True
#   description 1..1000, photo_ids ≤5 and must exist; photos → evidence
add_observation(user, place_id, ObservationInput) -> Observation   # source: admin role → admin, else community
list_observations(place_id, feature=None, active=True) -> list[Observation]   # active = not REJECTED
vote(user, observation_id, value: 1 | -1) -> VoteResult         # {observation, feature_state}
remove_vote(user, observation_id) -> None
recompute(repo, place_id, feature, now) -> FeatureStateRecord   # trust + validation + queue
```

## Tasks

| Id | What | Output / acceptance |
|---|---|---|
| F3.1 | 🔴 `tests/unit/test_trust.py` | (a) no obs → unknown; (b) seed yes 0.5 vs new no + photo 0.6 → no; (c) +3 👍 → 0.9; (d) 👎 lowers; (e) REJECTED ignored; (f) tie → newer |
| F3.2 | `domain/trust.py` | F3.1 green |
| F3.3 | 🔴 `tests/unit/test_validation.py` | old (60 d) yes + new no → no conflict; new no (anna) + new yes (marek) → conflict; same author both values → no conflict; REJECTED ignored |
| F3.4 | `domain/validation.py` | F3.3 green |
| F3.5 | 🔴 → 🟢 use cases | `tests/application/test_use_cases.py`: report creates observation + state `no`; author self-vote → error; re-vote replaces; 2nd conflicting obs → 1 open `QueueItem`, 3rd → still 1 item |
| F3.6 | `LocalFileStorage` + `upload_photo` | 11 MB → 413; `.gif` → 400; jpg → 201, file under `/media/...` |
| F3.7 | HTTP | `POST /uploads`, `POST /reports`, `GET /reports/{id}`, `GET|POST /places/{id}/observations`, `POST /observations/{id}/votes`, `DELETE /observations/{id}/votes/me` per [openapi.yaml](openapi.yaml); writes need user (401 otherwise) |
| F3.8 | Demo steps 4–6 | remove `xfail` steps 4–6 → green (step 6 asserts `QueueItem` exists via repo until F4 endpoint lands) |

## DoD

- Scenario: anna report → `elevator: no, temporary, 0.6`; +3 votes → `0.9`; `check` → `partial`; marek `yes` → `validation: CONFLICT`, 1 open queue item, state still `no`.
- F3.1–F3.5 green, STATUS.md + commit.

> Diff vs full contract: `POST /reports` returns `status=submitted` (full: `draft` + `/submit`). `ObservationValue` = `yes|no` (no `partial`). `current_state` = `works|not_working`.
