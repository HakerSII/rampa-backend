"""F30: Claude turns a natural-language query into needs + filters (forced tool call `set_filters`).
The model sees only the user's query and never returns facts about places — ranking and facts come from the DB.
Errors raise; the use case falls back to the rules interpreter."""
import httpx

from app.adapters.outbound.osm_live import _LazyClient
from app.domain.enums import FeatureKey, NeedsProfile
from app.domain.recommend import AREAS, CATEGORY_GROUPS, Intent

API_URL = "https://api.anthropic.com/v1/messages"
SYSTEM = ("You convert a user's request for an accessible place in Kraków into search filters by calling "
          "set_filters. Only list needs and features the user actually mentioned. Do not answer the question, "
          "do not describe places. The query may be Polish or English.")
TOOL = {
    "name": "set_filters",
    "description": "Accessibility needs and place filters extracted from the user's query.",
    "input_schema": {
        "type": "object",
        "properties": {
            "profiles": {"type": "array", "items": {"type": "string", "enum": [p.value for p in NeedsProfile]},
                         "description": "needs of the visitor (wheelchair, stroller = baby stroller, …)"},
            "features": {"type": "array", "items": {"type": "string", "enum": [f.value for f in FeatureKey]},
                         "description": "extra place features explicitly requested (toilet, pets, parking …)"},
            "categories": {"type": "array", "items": {"type": "string", "enum": list(CATEGORY_GROUPS)}},
            "area": {"type": ["string", "null"], "enum": [*AREAS, None]},
        },
        "required": ["profiles", "features", "categories"],
    },
}


def _valid(enum_cls, values) -> list:
    out = []
    for v in values or []:
        try:
            out.append(enum_cls(v))
        except ValueError:
            continue  # model answered outside the schema → drop
    return list(dict.fromkeys(out))


class ClaudeQueryInterpreter(_LazyClient):
    def __init__(self, api_key: str, model: str, *, url: str = API_URL, timeout_s: float = 20.0,
                 transport: httpx.AsyncBaseTransport | None = None):
        super().__init__("rampa-backend", timeout_s, transport)
        self.api_key, self.model, self.url = api_key, model, url

    async def interpret(self, query: str) -> Intent:
        r = await self.client.post(self.url, headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                                   json={"model": self.model, "max_tokens": 400, "system": SYSTEM,
                                         "tools": [TOOL], "tool_choice": {"type": "tool", "name": "set_filters"},
                                         "messages": [{"role": "user", "content": query}]})
        r.raise_for_status()
        call = next((c for c in r.json().get("content", [])
                     if c.get("type") == "tool_use" and c.get("name") == "set_filters"), None)
        if call is None:
            raise ValueError("model did not call set_filters")
        data = call.get("input") or {}
        area = data.get("area")
        return Intent(_valid(NeedsProfile, data.get("profiles")), _valid(FeatureKey, data.get("features")),
                      [c for c in dict.fromkeys(data.get("categories") or []) if c in CATEGORY_GROUPS],
                      area if area in AREAS else None)
