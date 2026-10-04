"""F47: AI_RECOMMENDER=onnx — the local Phi-3.5 (shared with the chat and photo analysis) turns a query into the same
filters as Claude/Gemini (F40: values from app/domain/recommend.py, checked by intent_from_filters). It has no
function calling: the prompt lists the allowed values with two examples and asks for one short JSON object
(a full JSON schema made the small model copy every value). Not loaded / no JSON / timeout → raise → rules."""
import json

from app.domain.city import City
from app.domain.enums import FeatureKey as F, NeedsProfile as P
from app.domain.recommend import Intent, default_city, intent_from_filters

MAX_NEW_TOKENS = 100
CLOSERS = ["", "}", "]}", "\"]}", "\"}"]  # a reply cut by the token limit


def _parse(text: str) -> dict:
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON filters in the model's answer")
    body = text[start:text.rfind("}") + 1] if "}" in text[start:] else text[start:]
    for closer in CLOSERS:
        try:
            data = json.loads(body + closer)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
        break
    raise ValueError("no JSON filters in the model's answer")


class OnnxQueryInterpreter:
    def __init__(self, llm, city: City | None = None):
        self.llm = llm  # OnnxPhiChatModel (name, state(), complete())
        self.city = city or default_city()
        self.model = llm.name

    def _messages(self, query: str) -> list[dict]:
        categories, areas = list(self.city.category_groups), list(self.city.areas)
        example1 = {"profiles": [P.WHEELCHAIR.value], "features": [], "categories": categories[:1]}
        if areas:
            example1["area"] = areas[-1]
        example2 = {"profiles": [], "features": [F.ELEVATOR.value, F.ACCESSIBLE_TOILET.value], "categories": []}
        system = (
            f"Convert a request for an accessible place in {self.city.name} into search filters. "
            "Reply with ONE short JSON object and nothing else. List ONLY what the user mentioned "
            "(usually 0-3 values per list); never copy the whole list of allowed values.\n"
            f"profiles: {', '.join(p.value for p in P)}\n"
            f"features: {', '.join(f.value for f in F)}\n"
            f"categories: {', '.join(categories)}\n"
            + (f"area (only if named): {', '.join(areas)}\n" if areas else "")
            + f'Example: "restauracja, jestem na wózku" -> {json.dumps(example1)}\n'
            + f'Example: "gdzie jest winda i toaleta?" -> {json.dumps(example2)}')
        return [{"role": "system", "content": system}, {"role": "user", "content": query}]

    async def interpret(self, query: str) -> Intent:
        if self.llm.state() != "ready":
            raise RuntimeError(f"local model not ready ({self.llm.state()})")
        return intent_from_filters(_parse(await self.llm.complete(self._messages(query), MAX_NEW_TOKENS)), self.city)
