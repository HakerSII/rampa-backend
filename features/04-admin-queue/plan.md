# F4 — Moderation queue (admin)

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · needs: [F3](../03-observations-trust/plan.md)

## Scope

- Admin sees conflicts (created by F3 `recompute`), opens detail, decides `confirm` / `reject`.
- History kept: decisions change `validation` only + add admin observation; nothing deleted.
- Demo reset endpoint (implemented F0.6) documented in this contract.

## Decision semantics

| action | requires | effect |
|---|---|---|
| `confirm` | `winning_observation_id` (must be in item) | winner → `VALID`; new observation `source=admin`, same value, author = admin, comment = decision comment; observations in item with **other value** → `REJECTED`; recompute; item `resolved` |
| `reject` | — | all observations in item → `REJECTED`; recompute (state falls back to older data, e.g. seed); item `resolved` |

- Item not `open` → 409 `CONFLICT`.
- `confirm` without / foreign `winning_observation_id` → 400.
- Non-admin → 403, no token → 401.
- Scenario: confirm marek's `yes` → admin `yes` (1.0) wins, anna's `no` rejected → `elevator: yes, confidence 1.0, VALID`.

## Use cases

```python
list_queue(filter: Literal["all", "conflict"] = "all", status: Literal["open", "resolved", "all"] = "open") -> QueuePage
get_queue_item(item_id) -> QueueDetail      # place summary, feature, observations (author, value, votes, evidence, confidence), current state
decide(admin, item_id, action, winning_observation_id=None, comment="") -> DecisionResult   # {id, status, feature_state}
reset_demo(admin) -> None                   # F0.6
```

## Tasks

| Id | What | Output / acceptance |
|---|---|---|
| F4.1 | 🔴 `tests/application/test_use_cases.py::test_decide_*` | confirm → state = winner value, confidence 1.0, opposite REJECTED, item resolved; reject → state from older obs; 2nd decision → `ConflictError`; foreign winner → `ValidationFailed` |
| F4.2 | Use cases `list_queue`, `get_queue_item`, `decide` | F4.1 green |
| F4.3 | HTTP | `GET /admin/queue`, `GET /admin/queue/{id}`, `POST /admin/queue/{id}/decision`, `POST /admin/demo/reset` per [openapi.yaml](openapi.yaml); `require_admin` |
| F4.4 | Demo step 7 | remove `xfail` step 7 (+ step 6 via endpoint) → **whole `test_demo_flow.py` green** |

## DoD

- `GET /admin/queue?filter=conflict` after step 6 → 1 item for `plc_mnk` / `elevator`, `observation_count ≥ 2`.
- Decision → `elevator: yes`, `check` → `yes`; same decision again → 409.
- `POST /admin/demo/reset` → step 1 state, identical numbers on re-run.
- Full `test_demo_flow.py` green = MVP DoD ([README §5](../../README.md)). STATUS.md + commit.

> Diff vs full contract: no `escalate`; filter only `all|conflict`; no `/comments`, `/stats`, `/history`, `/confidence`. `POST /admin/demo/reset` is new — add to full contract on merge (full plan T6.1).
