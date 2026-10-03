# STATUS — rampa-backend MVP

> **Read first.** After every step (🔴 red / 🟢 green / 🔵 refactor / task done): update this file + local commit. Push when online.
> Plan: [README.md](README.md) · features: [features/](features/)

## Current

- **Task:** F3 observations/votes/trust
- **Who:** Claude
- **State:** todo
- **Next step:** 🔴 `tests/unit/test_trust.py`, `tests/unit/test_validation.py`
- **Last pytest:** `uv run pytest` → 16 passed, 4 xfailed
- **Branch:** `feat/mvp-backend`

## Run

```
uv sync
uv run pytest
uv run uvicorn app.adapters.inbound.http.main:app --port 8000   # /docs
```

## Blockers / decisions

- F1.0 needs a human: Google Cloud OAuth "Web" client + `GOOGLE_CLIENT_ID` in `.env`. Demo mode works without it.

## Tasks

States: `todo` · `red` · `green` · `done` · `blocked`

| Task | What | Who | State | Notes |
|---|---|---|---|---|
| F0.1–F0.8 | Skeleton | Claude | done | `2c032f2` |
| F1.0 | Google Cloud OAuth client (human, online) | | todo | |
| F1.1–F1.4 | Auth: tests, use cases, Google adapter, HTTP | | todo | |
| F1.5 | Front button | frontend | todo | |
| F2.1–F2.5 | Places, search, check; demo steps 1–3 | Claude | done | steps 1–3 green |
| F3.1–F3.8 | Trust, validation, reports, uploads, votes; steps 4–6 | | todo | core |
| F4.1–F4.4 | Queue, decision; step 7 → full flow green | | todo | |

## Log (newest first)

- 2026-10-03 · F2 · done · check rules, search/details/accessibility/check endpoints; 16 passed, 4 xfail
- 2026-10-03 · F0 · done · skeleton, seed, demo auth, reset; 1 passed, 7 xfail · `2c032f2`
