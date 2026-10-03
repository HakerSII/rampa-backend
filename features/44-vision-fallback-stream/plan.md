# F44 — Vision fallback chain + streamed image check

Overview: [../../README.md](../../README.md) · extends F6 (image tags) and F40 (Gemini)

## Why
- On Render the Gemini vision call sometimes fails (quota, timeout) → the answer silently became the fixed mock sample.
- The check takes several seconds; the front end only had a spinner and no idea what was happening.

## What
- **Fallback chain.** `AI_VISION_FALLBACK=onnx` (default `mock`): with `AI_MODE=gemini` the order is Gemini → local Phi-3.5 Vision (ONNX) → mock.
  - ONNX is used only when it can run: `onnxruntime-genai` importable (`uv sync --extra ai`) and `AI_MODEL_PATH` exists. Otherwise the step is skipped with a warning at start (no crash) → Gemini → mock.
  - Each step has its own timeout (`AI_TIMEOUT_S` for Gemini, `AI_ONNX_TIMEOUT_S` for ONNX, default 180 s: CPU inference is slow).
  - Render free tier (512 MB) cannot load the model (~2–3 GB): there the chain is Gemini → mock; the ONNX step works locally / on a bigger instance.
- **Streamed check.** `POST /api/v1/ai/image-tags/stream` (same body as `/ai/image-tags`) → `text/event-stream`:
  - `event: status` `{"stage": "received"}` at once;
  - `event: status` `{"stage": "analyzing", "model": "gemini"}` before a model runs;
  - `event: status` `{"stage": "fallback", "from": "gemini", "model": "phi-3.5-vision-onnx"}` when a step fails;
  - `: keepalive` comment every 10 s while a model runs (proxies keep the connection open);
  - last: `event: result` with the same JSON as `/ai/image-tags`, or `event: error` `{"error": {"code", "message"}}` (e.g. `NOT_A_REAL_PLACE`, `VALIDATION_ERROR`).
  - Auth errors are normal HTTP 401 before the stream starts; `/ai/*` rate limits apply.
- `/ai/image-tags` (JSON) is unchanged and uses the same chain.

## Tests
- `tests/adapters/test_vision_chain.py`: chain order and status events, ONNX skipped when unavailable, bootstrap wiring.
- `tests/api/test_vision_stream_api.py`: event sequence, result equals the JSON endpoint, `NOT_A_REAL_PLACE` as an error event, 401, keepalive while a slow model runs.
- e2e: `requests/demo.http` F44.
