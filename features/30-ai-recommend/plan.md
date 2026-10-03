# F30 — AI recommendations from a natural-language query

Overview: [../../PLAN-GAPS.md](../../PLAN-GAPS.md) · contract: [openapi.yaml](openapi.yaml)

- `POST /ai/recommend {query, profile?, lat?, lon?, limit?}` (guest allowed) → `{intent, items[{place, match, distance_m, reasons[{feature, state, source, last_verified}], missing[]}], model, note}`.
- Interpreter = port `QueryInterpreter`: `rules` (default, offline, PL+EN) | `claude` (`ANTHROPIC_API_KEY`, `CLAUDE_MODEL`) | `gemini` (`GEMINI_API_KEY`, `GEMINI_MODEL`) via forced tool call `set_filters` — one schema for both, see [../40-llm-tools-unification/plan.md](../40-llm-tools-unification/plan.md). The model gets only the query and returns needs/filters; it never sees or writes facts. Failure → rules.
- Ranking in the domain (`app/domain/recommend.py`) from DB states: `check` per profile + requested features; yes > partial > unknown > no; ties → distance. `missing` = unknown or stale (> 90 days) data for what the user asked.
