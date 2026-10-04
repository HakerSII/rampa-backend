# F45 — Photo metadata + mismatch check (photo deleted)

Overview: [../../README.md](../../README.md) · extends F3 (uploads), F6 (image tags), F44 (stream)

## Why
- The user picks what the photo shows (place, element, state); the AI check must confirm it, not only suggest.
- A photo that does not show what the user claimed must not stay in the system.

## What
- **Upload with metadata.** `POST /api/v1/uploads` (multipart) takes optional form fields `place_id`, `element`
  (FeatureKey), `current_state` (CurrentState) → still **201** `{id, url, place_id, element, current_state}`.
  Unknown place / invalid enum → 400 `VALIDATION_ERROR` (nothing stored).
- **Expected values.** `/ai/image-tags` and `/ai/image-tags/stream` take optional `expected: {element, current_state?}`;
  without it the photos' upload metadata is used. No expectation → behaviour unchanged (suggestion only).
- **Mismatch.** The model suggests an element/state and it differs from the expected one
  (other element, or same element with another state) → **400 `PHOTO_MISMATCH`**
  (stream: last event `event: error`), `details: {expected, suggested, description, deleted_photo_ids}`.
  - The checked photos are **deleted** (record + file) unless already evidence of a report/observation.
  - No suggestion from the model (nothing recognised) → no verdict, normal result.
- Demo path: mock model is name-based — `winda.png` uploaded with `element=stairs` → mismatch; with `element=elevator` → result.

## Files
- `app/domain/model.py` Photo metadata · `app/domain/errors.py` `PhotoMismatch`, `details`
- `app/application/use_cases.py` upload metadata, `analyze_image(expected=…)`, photo deletion
- `app/adapters/outbound/memory.py` / `files.py` delete · `sql.py` columns (auto `ADD COLUMN`)
- routers `observations.py` (form fields), `ai.py` (`expected`), `errors.py` (400 + details)

## Acceptance
- tests/application/test_photo_mismatch.py, tests/api/test_photo_mismatch_api.py
- e2e `requests/demo.http` F45a–c
