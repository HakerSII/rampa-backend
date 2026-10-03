"""F30b / F40 A: Gemini turns a natural-language query into needs + filters (forced function call `set_filters`).
Same tool as Claude — schema + prompt from app/domain/recommend.py (F40 A); this file is only the envelope.
Only filters come back, facts always come from the DB.
Key only in the x-goog-api-key header. Errors (429 quota, no call) raise → the use case falls back to rules."""
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


def declaration(city: City) -> dict:
    return {"name": FILTER_TOOL, "description": FILTER_TOOL_DESCRIPTION, "parameters": filters_schema(city)}


class GeminiQueryInterpreter(_LazyClient):
    def __init__(self, api_key: str, model: str, api_url: str, *, timeout_s: float = 20.0, city: City | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        super().__init__("rampa-backend", timeout_s, transport)
        self.api_key, self.model, self.api_url = api_key, model, api_url.rstrip("/")
        self.city = city or default_city()

    async def interpret(self, query: str) -> Intent:
        body = {
            "systemInstruction": {"parts": [{"text": FILTER_SYSTEM_PROMPT.format(city=self.city.name)}]},
            "contents": [{"role": "user", "parts": [{"text": query}]}],
            "tools": [{"functionDeclarations": [declaration(self.city)]}],
            "toolConfig": {"functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": [FILTER_TOOL]}},
            "generationConfig": {"temperature": 0},
        }
        r = await self.client.post(f"{self.api_url}/models/{self.model}:generateContent", json=body,
                                   headers={"x-goog-api-key": self.api_key})
        r.raise_for_status()
        parts = ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        call = next((p["functionCall"] for p in parts
                     if p.get("functionCall", {}).get("name") == FILTER_TOOL), None)
        if call is None:
            raise ValueError("model did not call set_filters")
        return intent_from_filters(call.get("args") or {}, self.city)
