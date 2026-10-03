# F10 — Gemini vision for photo suggestions

Overview: [../../README.md](../../README.md) · contract: F6 [openapi.yaml](../06-ai-image-tags/openapi.yaml) (same endpoint, `model: gemini` added) · needs: [F6](../06-ai-image-tags/plan.md)

## Scope

- New `VisionAnalyzer` adapter: Google Gemini API, REST `models/{model}:generateContent` via **httpx** (no SDK, no new dependency).
- Selected by config: `AI_MODE=mock|onnx|gemini`.
- Config (`app/config.py` ↔ `.env.example`):
  - `GEMINI_API_KEY` — secret, only in `.env` (gitignored); sent as `x-goog-api-key` header (never in URL/logs)
  - `GEMINI_MODEL` — default `gemini-3.8-flash` (API said `gemini-2.5-flash` is no longer available to new users)
  - `GEMINI_API_URL` — default `https://generativelanguage.googleapis.com/v1beta`
  - `AI_TIMEOUT_S` — shared with onnx
- Request: same instruction + JSON schema as Phi (shared `vision_prompt.py`), image as `inline_data` base64, `generationConfig.response_mime_type=application/json`, `temperature=0`.
- Response: `candidates[0].content.parts[*].text` → `parse_analysis` → `ImageAnalysis(model="gemini")`.
- Retries 429/5xx ("high demand") up to 2× with backoff 2 s, 4 s.
- Severity: `wheelchair` / `mobility` / `physical` affected → critical.
- Wrapped in `FallbackVisionAnalyzer`: no key / HTTP error / timeout / blocked / bad JSON → mock (`model: "mock"`), warning in log. Demo never breaks.

## Tasks

| Id | What | Output / acceptance |
|---|---|---|
| F10.1 | 🔴 tests | `adapters/test_vision_gemini.py` with `httpx.MockTransport`: request shape (URL, header, base64 image, JSON mode), parse OK, HTTP 4xx/5xx → error, no candidates → error, no key → error; bootstrap `AI_MODE=gemini` → Fallback(Gemini, mock); use case falls back to mock on Gemini failure |
| F10.2 | `vision_prompt.py` (shared instruction + parser), `vision_gemini.py`, config, bootstrap | F10.1 green |
| F10.3 | Contract + docs | F6 openapi `model` enum + `gemini`; `.env.example`; README |
| F10.4 | e2e | demo.http comment; manual live check with real key (not automated — needs secret + network) |

## DoD

Tests green, e2e verified (mock path), STATUS.md + commit. Live Gemini call: **manual** with own key.
