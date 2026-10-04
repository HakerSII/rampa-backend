# F46 — Chat assistant on the server (local Phi-3.5 + MCP tools), streamed

Overview: [../../README.md](../../README.md) · uses F8/F41 (MCP tools), F6 (local ONNX model), F44 (SSE)

## Why
- A chat that answers accessibility questions from the database, on any device (also phones without WebGPU).
- The model is heavy (~2.6 GB): load it once when the server starts, not per request or per browser.

## What
- **Model.** `CHAT_MODE`: `rules` (default; no model, keyword rules + answer template) · `onnx` (local Phi-3.5,
  same files as `AI_MODEL_PATH` unless `CHAT_MODEL_PATH`) · `off` (endpoints answer 503 `CHAT_DISABLED`).
  - `CHAT_PRELOAD=true` (default): with `onnx` the model starts loading in a background thread at app start;
    the server answers at once. One loaded model is shared with photo analysis (`AI_MODE=onnx`), one inference at a time.
  - Not loaded yet / failed to load / timeout (`CHAT_TIMEOUT_S`, default 120) / any model error → the rules answer
    (the chat never breaks, like the vision fallback).
- **Tools** = the MCP server's tools (`check_accessibility`, `search_accessible_places`, same code `clients/rampa_tools.py`),
  run in-process against this app's Open API (`/public/v1`, first `PUBLIC_API_KEYS` key).
- **One question:** model picks a tool as JSON (`{"tool", "arguments"}`); invalid → keyword rules pick one →
  tool runs → model answers in Polish from the tool data only (streamed) → template when the model is not usable.
- `GET /api/v1/ai/chat/status` → `{mode, state: off|loading|ready|error|rules, model, tools: [names]}`.
- `POST /api/v1/ai/chat/stream` `{question}` (1–500 chars; guest allowed; `/ai/*` rate limits) → `text/event-stream`:
  - `status` `{"stage": "received"}` · `{"stage": "model_loading"}` (onnx not ready → rules)
    · `{"stage": "choosing_tool", "model"}` · `{"stage": "answering", "model"}`
  - `tool_call` `{"name", "arguments", "chosen_by": "model"|"rules"}` · `tool_result` `{"name", "result"}`
  - `token` `{"text"}` (pieces of the answer) · `: keepalive` every 10 s
  - last: `done` `{"answer", "model", "tool"}` or `error` `{"error": {"code", "message"}}`.

## Files
- `app/application/chat.py` (ChatAssistant, rules, prompts) · ports `ChatModel`, `ChatTools`
- `app/adapters/outbound/phi_onnx.py` (shared model + inference lock) · `chat_onnx.py` · `vision_onnx.py` uses the shared loader
- `app/adapters/inbound/http/chat_tools.py` (in-process MCP tools) · router `ai.py` · `main.py` (preload) · `config.py`
- `clients/rampa_tools.py`: `TOOL_DEFS`, `RampaTools.call(name, args)`

## Acceptance
- tests/application/test_chat.py, tests/adapters/test_chat_onnx.py, tests/api/test_chat_api.py
- e2e `requests/demo.http` F46a–b
