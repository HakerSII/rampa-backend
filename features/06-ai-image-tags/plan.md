# F6 — AI suggestions from photos

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · needs: [F3](../03-observations-trust/plan.md) (uploads)

## Scope

- `POST /api/v1/ai/image-tags {photo_ids, place_id?}` → model analysis + tags + suggested report fields.
- AI = **suggestion only** (`source: ai_suggestion` in full plan): fills the report form, never changes feature state.
- Port `VisionAnalyzer.analyze(path, original_name) -> ImageAnalysis`.
- `AI_MODE=mock` (default, offline, deterministic) | `onnx` (Phi-3.5 Vision ONNX, logic from `get_model.py`, model in `models/`, optional extra `ai`).
- `onnx` wrapped in fallback: error / timeout (`AI_TIMEOUT_S`, default 60) / bad JSON → mock answer, `model: "mock"`.

## `ImageAnalysis` (= JSON schema of `analyze_image()` in get_model.py)

`real_place, barrier_detected, barrier_type, affected_disabilities[], description, confidence` + `model`.

## Mock (deterministic)

| original file name contains | result |
|---|---|
| `screenshot`, `meme`, `screen` | `real_place: false` |
| `winda`, `elevator`, `lift` | elevator out of order + notice + stairs, conf 0.82 |
| `schody`, `stairs`, `steps` | stairs without ramp, conf 0.77 |
| anything else | crc32(name) % 3 → one of: elevator / stairs / no barrier |

## Mapping → tags / suggested (pure, `domain/suggestions.py`)

- Keywords in `barrier_type` (first) then `description` → features: elevator/lift/winda → `elevator`; stairs/steps/schody → `step_free_entrance`; ramp/podjazd → `ramp`; toilet/wc → `accessible_toilet`; induction/pętla → `induction_loop`.
- Extra tags: broken/out of order/nieczynn/awari → `awaria`; notice/sign/kartk → `tablica informacyjna`.
- `suggested` (only if `barrier_detected`): `element` = first feature; `current_state = not_working`; `severity` = `critical` if `wheelchair` affected, else `obstacle`.
- Tag confidence = analysis confidence.
- Many photos: analyze each; all `real_place: false` → 400 `NOT_A_REAL_PLACE`; else drop non-real ones, analysis = highest confidence, tags = union (max confidence), `detected` = joined descriptions.

## Tasks

| Id | What | Output / acceptance |
|---|---|---|
| F6.1 | 🔴 tests | `unit/test_suggestions.py` (3 cases), `unit/test_vision_onnx.py` (JSON extraction), `application/test_ai.py` (mock, merge, not real, fallback on error/timeout, validation, login) |
| F6.2 | Domain + port | `ImageAnalysis`, `suggestions.py`, `VisionAnalyzer`, `Photo.original_name` |
| F6.3 | Adapters | `vision_mock.py`, `vision_onnx.py` (lazy load in thread, `Semaphore(1)`), `FallbackVisionAnalyzer` |
| F6.4 | Use case + HTTP | `analyze_image`, `POST /ai/image-tags`, `NOT_A_REAL_PLACE` → 400 |
| F6.5 | e2e | `demo.http`: AI step after upload + 400 screenshot case; demo flow test step 4b |

## DoD

- Tests green, contract test 6 specs, e2e verified, STATUS.md + commit.
- `AI_MODE=onnx` real inference: **manual** check (`uv sync --extra ai`, GPU, slow) — not in CI.
