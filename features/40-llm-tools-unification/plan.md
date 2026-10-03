# F40 — one shared tool for MCP + Claude + Gemini (no duplicated tool schemas)

Overview: [../../PLAN-GAPS.md](../../PLAN-GAPS.md) · related: [../30-ai-recommend/plan.md](../30-ai-recommend/plan.md) · [../08-osm-mcp/plan.md](../08-osm-mcp/plan.md)

## Problem

Today there are **two unrelated tool definitions** doing almost the same job:

- `clients/rampa_tools.py::RampaTools` — real tools (`check_accessibility`, `search_accessible_places`), httpx client of `/public/v1`, exposed over **MCP stdio** (`clients/mcp_server.py`) for Claude Desktop/Code and other local MCP clients.
- `app/adapters/outbound/recommender_claude.py::tool()` — a **bespoke** `set_filters` JSON schema invented only for `POST /ai/recommend`, forced tool-call, never executed (no HTTP call) — the model's arguments are turned into an `Intent`, then the domain (`app/domain/recommend.py`) ranks places from DB state only.

Two schemas, two sets of field names, maintained in two places → drift risk, and the Gemini adapter we're about to add would have been a **third** copy.

## Decision

Single source of truth: **`RampaTools`** (`clients/rampa_tools.py`) is "our tool". Both LLM recommenders (Claude, Gemini) call into it the same way MCP does — no separate `set_filters` invention.

- `check_accessibility(place_name, profile="wheelchair", limit=3)` → real lookup + check, used when the query names a specific place.
- `search_accessible_places(features: list[str], limit=10)` → real search, used when the query is about features/needs in general.

### Keeping the anti-hallucination guarantee

`POST /ai/recommend` must still **never** let the model state facts about places — only `app/domain/recommend.py` (reading DB state) is allowed to say yes/partial/no/unknown. So the interpreter still does a **forced, single tool call**, and only reads the **call arguments** to build `Intent` — it does not execute the tool's HTTP side (no place facts flow back into the prompt/response). This is unchanged behaviour, just reusing the real tool's name/schema instead of a parallel one.

- `profiles`/`categories`/`area` are still needed for `Intent` and aren't part of today's `RampaTools` signatures → extend `search_accessible_places(features, profile=None, category=None, area=None)` (optional kwargs, backward compatible: MCP callers that omit them behave exactly as today) so the **one** schema covers both the public-API search and the recommend-intent extraction.
- `check_accessibility(place_name, profile)` already covers the "is place X accessible for Y" case 1:1.

### Where the shared schema lives

- Move/author the tool JSON-schema (Claude `input_schema` / Gemini `function_declarations` — same shape, different envelope) next to `RampaTools`, generated from one dict of field definitions (names, enums from `FeatureKey`/`NeedsProfile`/`city.category_groups`/`city.areas`), so:
  - `clients/mcp_server.py` keeps using `@mcp.tool()` (FastMCP derives schema from the Python signature — unchanged).
  - `recommender_claude.py` and `recommender_gemini.py` import the same schema dict/builder instead of defining their own.

## Plan

1. `clients/rampa_tools.py`: extend `search_accessible_places(features, profile=None, category=None, area=None, limit=10)`; thread the extra filters into the `GET /public/v1/places` call (`category`, and a profile-based feature check — reuses the existing `/places?features=&category=&q=` contract, no new backend endpoint needed).
2. New `app/adapters/outbound/llm_tools.py`: one function per provider that builds the tool schema from `RampaTools`' two methods + the domain enums (replaces `recommender_claude.py`'s local `tool()`), e.g. `claude_tools(city) -> list[dict]`, `gemini_tools(city) -> list[dict]`.
3. `recommender_claude.py` (`ClaudeQueryInterpreter.interpret`): force tool_choice over **both** tools instead of only `set_filters`; map whichever tool got called (`check_accessibility` → `place_name` hint only, no profiles/features assumed beyond what's given; `search_accessible_places` → `features`/`profile`/`category`/`area`) into `Intent`. Still raises on failure → rules fallback, unchanged.
4. New `app/adapters/outbound/recommender_gemini.py::GeminiQueryInterpreter` — same shape as Claude's, Gemini function-calling with `mode: ANY` (forced), reuses `app/config.py`'s existing `gemini_api_key`/`gemini_model`/`gemini_api_url` (already used by the vision adapter, F10) — no new secrets needed.
5. `config.py`: `ai_recommender: Literal["rules", "claude", "gemini"]`.
6. `bootstrap.py::build_recommender`: add the `gemini` branch next to `claude` (same empty-key → warn + fallback-to-`None` pattern already there for Claude).
7. Tests: mirror `tests/application/test_recommend.py`'s Claude tests (via `httpx.MockTransport`) for Gemini; add a case asserting `check_accessibility` vs `search_accessible_places` tool-call routing.
8. Docs: update `docs/api.md` / `docs/configuration.md` (`AI_RECOMMENDER=gemini` row) and `features/30-ai-recommend/plan.md` to point at this file instead of duplicating the tool description.

## Non-goals (for now)

- Not exposing MCP over HTTP publicly — this plan is only about *internal* reuse of the tool definitions; MCP stays stdio-only per [../08-osm-mcp/plan.md](../08-osm-mcp/plan.md) unless/until that's separately decided.
- Not having the LLM see live tool results inside `/ai/recommend` — ranking/facts stay DB-only, by design.
