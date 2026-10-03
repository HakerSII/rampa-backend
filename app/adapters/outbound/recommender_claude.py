"""F30: Claude turns a natural-language query into needs + filters (forced tool call `set_filters`).
Tool schema + prompt: app/domain/recommend.py (shared with Gemini, F40 A) — this file is only the envelope.
The model sees only the user's query and never returns facts about places — ranking and facts come from the DB.
Errors raise; the use case falls back to the rules interpreter."""
import httpx

from app.adapters.outbound.osm_live import _LazyClient
from app.domain.city import City
from app.domain.recommend import (
    FILTER_SYSTEM_PROMPT,
    FILTER_TOOL,
    FILTER_TOOL_DESCRIPTION,
    Intent,
    default_city,
    filters_schema,
    intent_from_filters,
)

API_URL = "https://api.anthropic.com/v1/messages"
def tool(city: City) -> dict:
    return {"name": FILTER_TOOL, "description": FILTER_TOOL_DESCRIPTION, "input_schema": filters_schema(city)}


class ClaudeQueryInterpreter(_LazyClient):
    def __init__(self, api_key: str, model: str, *, url: str = API_URL, timeout_s: float = 20.0,
                 city: City | None = None, transport: httpx.AsyncBaseTransport | None = None):
        super().__init__("rampa-backend", timeout_s, transport)
        self.api_key, self.model, self.url = api_key, model, url
        self.city = city or default_city()

    async def interpret(self, query: str) -> Intent:
        r = await self.client.post(self.url, headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                                   json={"model": self.model, "max_tokens": 400,
                                         "system": FILTER_SYSTEM_PROMPT.format(city=self.city.name),
                                         "tools": [tool(self.city)],
                                         "tool_choice": {"type": "tool", "name": FILTER_TOOL},
                                         "messages": [{"role": "user", "content": query}]})
        r.raise_for_status()
        call = next((c for c in r.json().get("content", [])
                     if c.get("type") == "tool_use" and c.get("name") == FILTER_TOOL), None)
        if call is None:
            raise ValueError("model did not call set_filters")
        return intent_from_filters(call.get("input") or {}, self.city)
