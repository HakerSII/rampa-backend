"""F46: chat assistant — picks an MCP tool (model JSON or keyword rules), runs it, answers from its data only.

The model is optional: without one (CHAT_MODE=rules), not loaded yet, or failing, the rules pick the tool and a
template writes the answer, so every question gets the database's facts. Events go to `emit((event, data))`:
status, tool_call, tool_result, token, done (see features/46-chat-assistant/plan.md)."""
import json
import logging
import re
from collections.abc import Callable
from typing import Protocol

from app.domain.enums import LABELS_PL

log = logging.getLogger(__name__)

MAX_TOOL_CHARS = 2500  # tool data in the answer prompt (short context = fast on CPU)
CHOICE_TOKENS = 60

FEATURE_WORDS = [
    (r"wind", "elevator"), (r"toalet|\bwc\b|łazienk", "accessible_toilet"), (r"podjazd|ramp", "ramp"),
    (r"bez schod|bez progu|schod", "step_free_entrance"), (r"pętl|aparat słuch|niedosłysz", "induction_loop"),
    (r"przewij", "baby_changing_table"), (r"\bpies|\bpsa\b|\bpsem\b", "assistance_dog_allowed"),
]
PROFILE_WORDS = [
    (r"wózk\w* dziecięc|wózek dziecięcy", "stroller"), (r"\bkul\b|o kulach|kulach", "crutches"),
    (r"niewidom", "blind"), (r"słabowid|niedowid", "low_vision"), (r"głuch|niesłysz", "deaf"),
    (r"pies asystu|psem asystu|psa asystu", "assistance_dog"),
]
VERBS = r"\s+(jest|są|ma|mają|da się|wejdę|wjadę|dostanę|można|posiada)(?=\s|$).*$"
ANSWER_PL = {"yes": "tak", "partial": "częściowo", "no": "nie", "unknown": "brak pewnych danych"}


class ChatModel(Protocol):
    name: str

    def state(self) -> str: ...  # off | loading | ready | error

    async def complete(self, messages: list[dict], max_new_tokens: int,
                       on_token: Callable[[str], None] | None = None) -> str: ...


class ChatTools(Protocol):
    definitions: list[dict]  # [{name, description, parameters (JSON schema)}]

    async def call(self, name: str, arguments: dict) -> dict: ...


# ----------------------------------------------------------------- rules
def _place_name(question: str) -> str:
    """'Czy do Teatru Słowackiego wejdę z wózkiem?' → 'Teatru Słowackiego'."""
    q = re.sub(r"[?.!]+$", "", question.strip())
    q = re.sub(VERBS, "", q, flags=re.I)
    q = re.sub(r"^(czy|gdzie|jak|a)\s+", "", q, flags=re.I)
    q = re.sub(r"^(do|w|we|na|z)\s+", "", q, flags=re.I)
    return q.strip() or question.strip()


def _names_a_place(question: str) -> bool:
    words = question.split()[1:]  # the first word is capitalised anyway
    return any(w[:1].isupper() for w in words) or bool(
        re.search(r"muzeum|teatr|kino|hotel|restaurac|kawiarni|galeri|dworzec|szpital|urząd|kości|zamek|wawel",
                  question, re.I))


def choose_tool(question: str, tool_names: list[str]) -> tuple[str, dict]:
    """Keyword rules: features without a named place → search, else check the place by name (+ profile)."""
    features = list(dict.fromkeys(f for pattern, f in FEATURE_WORDS if re.search(pattern, question, re.I)))
    if features and not _names_a_place(question) and "search_accessible_places" in tool_names:
        return "search_accessible_places", {"features": features}
    args = {"place_name": _place_name(question)}
    profile = next((p for pattern, p in PROFILE_WORDS if re.search(pattern, question, re.I)), None)
    if profile:
        args["profile"] = profile
    return "check_accessibility", args


def parse_tool_call(text: str, definitions: list[dict]) -> tuple[str, dict] | None:
    """The model's {"tool", "arguments"} → (name, arguments) if the tool exists and required arguments are there."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        call = json.loads(text[start:end + 1])
    except ValueError:
        return None
    if not isinstance(call, dict):
        return None
    tool = next((t for t in definitions if t["name"] == call.get("tool")), None)
    args = call.get("arguments")
    if tool is None or not isinstance(args, dict):
        return None
    props = tool["parameters"].get("properties", {})
    args = {k: v for k, v in args.items() if k in props}
    if not all(k in args and args[k] not in ("", [], None) for k in tool["parameters"].get("required", [])):
        return None
    return tool["name"], args


def _label(feature: str) -> str:
    return LABELS_PL.get(feature, feature).lower()


def answer_from_data(tool: str, data: dict) -> str:
    """Template answer (Polish) from a tool's result — used without a model and as the model's fallback."""
    if "error" in data:
        return f"Nie udało się pobrać danych: {data['error']}"
    if tool == "search_accessible_places":
        places = data.get("places") or []
        wanted = ", ".join(_label(f) for f in data.get("features", []))
        if not places:
            return f"Nie znalazłem miejsc, które mają: {wanted}."
        listed = "; ".join(p["name"] + (f" ({p['address']})" if p.get("address") else "") for p in places[:5])
        return f"Znalazłem {data.get('total', len(places))} miejsc, które mają: {wanted}. Na przykład: {listed}."
    matches = data.get("matches") or []
    if not matches:
        return data.get("message") or f"Nie znaleziono miejsca „{data.get('query', '')}”."
    m = matches[0]
    place = m["place"]
    acc = m.get("accessibility") or {}
    has = [_label(k) for k, v in acc.items() if v.get("value") is True]
    lacks = [_label(k) for k, v in acc.items() if v.get("value") is False]
    parts = [f"{place['name']}" + (f" ({place['address']})" if place.get("address") else "")
             + f": {ANSWER_PL.get(m.get('answer'), m.get('answer'))}.",
             m.get("advice") or ""]
    if has:
        parts.append(f"Jest: {', '.join(has)}.")
    if lacks:
        parts.append(f"Brak: {', '.join(lacks)}.")
    parts.append(f"Pewność danych: {round(float(m.get('confidence', 0)) * 100)}%.")
    if len(matches) > 1:
        parts.append(f"Podobnych miejsc w bazie: {len(matches) - 1} więcej.")
    return " ".join(p for p in parts if p)


# ----------------------------------------------------------------- prompts
def tool_messages(question: str, definitions: list[dict]) -> list[dict]:
    tools = "\n".join(f"- {t['name']}: {' '.join(t['description'].split())}\n  argumenty: "
                      f"{json.dumps(t['parameters'].get('properties', {}), ensure_ascii=False)}" for t in definitions)
    return [
        {"role": "system", "content": f"Masz narzędzia z danymi o dostępności miejsc w Krakowie:\n{tools}\n"
                                      'Odpowiedz TYLKO jednym obiektem JSON: {"tool": "<nazwa>", "arguments": {...}}. '
                                      "Nazwę miejsca podaj tak, jak w pytaniu."},
        {"role": "user", "content": question},
    ]


def answer_messages(question: str, tool: str, data: dict) -> list[dict]:
    return [
        {"role": "system", "content": "Jesteś asystentem dostępności Krakowa. Odpowiadaj po polsku, krótko (2-4 zdania), "
                                      "wyłącznie na podstawie danych z narzędzia. value=true znaczy, że udogodnienie jest; "
                                      "false, że go nie ma; brak cechy = brak danych. Nie zgaduj. Podaj pewność danych."},
        {"role": "user", "content": f"Pytanie: {question}\n\nDane z narzędzia {tool}:\n"
                                    f"{json.dumps(data, ensure_ascii=False)[:MAX_TOOL_CHARS]}"},
    ]


# ----------------------------------------------------------------- assistant
class ChatAssistant:
    def __init__(self, model: ChatModel | None, tools: ChatTools, max_new_tokens: int = 160):
        self.model = model
        self.tools = tools
        self.max_new_tokens = max_new_tokens

    def status(self) -> dict:
        names = [t["name"] for t in self.tools.definitions]
        if self.model is None:
            return {"state": "rules", "model": "rules", "tools": names}
        return {"state": self.model.state(), "model": self.model.name, "tools": names}

    async def ask(self, question: str, emit: Callable[[tuple[str, dict]], None]) -> None:
        emit(("status", {"stage": "received"}))
        definitions = self.tools.definitions
        model = self.model
        if model is not None and model.state() == "off" and hasattr(model, "start_loading"):
            model.start_loading()  # not preloaded: start now, this question gets the rules answer
        use_model = model is not None and model.state() == "ready"
        if model is not None and not use_model:
            emit(("status", {"stage": "model_loading"}))

        call, chosen_by = None, "rules"
        if use_model:
            emit(("status", {"stage": "choosing_tool", "model": model.name}))
            try:
                call = parse_tool_call(await model.complete(tool_messages(question, definitions), CHOICE_TOKENS),
                                       definitions)
            except Exception as e:  # noqa: BLE001 — any model failure → rules
                log.warning("chat model failed choosing a tool (%s: %s) → rules", type(e).__name__, e)
                use_model = False
            chosen_by = "model" if call else "rules"
        name, args = call or choose_tool(question, [t["name"] for t in definitions])
        emit(("tool_call", {"name": name, "arguments": args, "chosen_by": chosen_by}))
        data = await self.tools.call(name, args)
        emit(("tool_result", {"name": name, "result": data}))

        answer, answered_by = "", "rules"
        if use_model:
            emit(("status", {"stage": "answering", "model": model.name}))
            try:
                answer = (await model.complete(answer_messages(question, name, data), self.max_new_tokens,
                                               on_token=lambda t: emit(("token", {"text": t})))).strip()
                answered_by = model.name
            except Exception as e:  # noqa: BLE001 — any model failure → template
                log.warning("chat model failed answering (%s: %s) → template", type(e).__name__, e)
                answer = ""
        if not answer:
            answer, answered_by = answer_from_data(name, data), "rules"
            emit(("token", {"text": answer}))
        emit(("done", {"answer": answer, "model": answered_by, "tool": name}))
