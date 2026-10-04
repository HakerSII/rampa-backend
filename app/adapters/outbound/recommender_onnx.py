"""F47: AI_RECOMMENDER=onnx — the local Phi-3.5 (shared with the chat and photo analysis) turns a query into the same
filters as Claude/Gemini (F40 schema, app/domain/recommend.py). It has no function calling, so the schema goes into
the prompt and the answer must be one JSON object. Not loaded yet / no JSON / timeout → raise → rules."""
import json

from app.domain.city import City
from app.domain.recommend import FILTER_SYSTEM_PROMPT, Intent, default_city, filters_schema, intent_from_filters

MAX_NEW_TOKENS = 120


class OnnxQueryInterpreter:
    def __init__(self, llm, city: City | None = None):
        self.llm = llm  # OnnxPhiChatModel (name, state(), complete())
        self.city = city or default_city()
        self.model = llm.name

    def _messages(self, query: str) -> list[dict]:
        system = (FILTER_SYSTEM_PROMPT.format(city=self.city.name).replace("by calling set_filters", "")
                  + "\nAnswer ONLY with one JSON object matching this JSON schema (use only the listed values):\n"
                  + json.dumps(filters_schema(self.city), ensure_ascii=False))
        return [{"role": "system", "content": system}, {"role": "user", "content": query}]

    async def interpret(self, query: str) -> Intent:
        if self.llm.state() != "ready":
            raise RuntimeError(f"local model not ready ({self.llm.state()})")
        text = await self.llm.complete(self._messages(query), MAX_NEW_TOKENS)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no JSON filters in the model's answer")
        data = json.loads(text[start:end + 1])
        if not isinstance(data, dict):
            raise ValueError("filters are not an object")
        return intent_from_filters(data, self.city)
