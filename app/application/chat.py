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
from app.domain.text import fold

log = logging.getLogger(__name__)

MAX_TOOL_CHARS = 2500  # tool data in the answer prompt (short context = fast on CPU)
CHOICE_TOKENS = 60

# patterns match the folded question (lower case, no diacritics): "prog" and "próg" alike
FEATURE_WORDS = [
    (r"wind", "elevator"), (r"toalet|\bwc\b|lazienk", "accessible_toilet"), (r"podjazd|ramp", "ramp"),
    (r"schod|\bprog", "step_free_entrance"), (r"petl|aparat sluch|niedoslysz", "induction_loop"),
    (r"przewij", "baby_changing_table"), (r"\bpies|\bpsa\b|\bpsem\b", "assistance_dog_allowed"),
]
PROFILE_WORDS = [
    (r"wozk\w* dzieci|wozek dzieci", "stroller"), (r"\bkul\b|o kulach|kulach", "crutches"),
    (r"niewidom", "blind"), (r"slabowid|niedowid", "low_vision"), (r"gluch|niesl?ysz", "deaf"),
    (r"pies asystu|psem asystu|psa asystu", "assistance_dog"),
]
# general questions ("jakie miejsca znasz", "pomoc"): no tool, a short guide what to ask
GENERAL = re.compile(r"^(jakie|ktore|co) (miejsca|wiesz|znasz|umiesz|potrafisz)|\bpomoc\b|\bhelp\b|"
                     r"co potrafisz|co umiesz|jak (dzialasz|to dziala|cie uzywac)|\bw bazie\b")
HELP_ANSWER = ("Znam miejsca w Krakowie z bazy Kraków bez barier: restauracje, kawiarnie, muzea, teatry, hotele, "
               "apteki, urzędy i wiele innych, z danymi o dostępności (wejście bez schodów, winda, toaleta…). "
               "Zapytaj o konkretne miejsce, np. „Czy Muzeum Narodowe jest dostępne na wózku?”, albo o udogodnienia: "
               "„Gdzie jest winda i toaleta dla niepełnosprawnych?”.")
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
# words of a question that are not part of a place name (folded): question words, linking words, verbs of getting
# in, "dostępne", and the visitor's means ("wózkiem", "o kulach") — removed wherever they stand
NOT_NAME = re.compile(
    r"(czy|gdzie|jak|a|do|w|we|na|z|ze|o|i|jest|sa|ma|maja|da|sie|mozna|moge|posiada|wejde|wjade|wejsc|wjechac|"
    r"dostane|dojade|dostac|tam|tu|mnie|ja|dostepn\w*|przystosowan\w*|wozk\w*|wozek|dzieci\w*|inwalidz\w*|"
    r"kul\w*|osob\w*|niepelnospraw\w*|niewidom\w*|gluch\w*|psem|pies|psa)")


def _place_name(question: str) -> str:
    """'czy do teatru na słowackiego wjade wozkiem ?' → 'teatru słowackiego' (search ignores endings/diacritics)."""
    words = [w for w in re.split(r"\s+", question.strip()) if w]
    kept = [w for w in words if not NOT_NAME.fullmatch(fold(w).strip("?.!,;:()\"'„”"))]
    name = " ".join(kept).strip(" ?.!,;:")
    return name or question.strip(" ?.!")


def _names_a_place(question: str) -> bool:
    words = question.split()[1:]  # the first word is capitalised anyway
    return any(w[:1].isupper() for w in words) or bool(
        re.search(r"muzeum|teatr|kino|hotel|restaurac|kawiarni|galeri|dworzec|szpital|urzad|kosci|zamek|wawel|"
                  r"plywalni|basen|park|sklep|apteka|bank|poczta", fold(question)))


def is_general(question: str) -> bool:
    """'jakie miejsca znasz', 'co potrafisz', 'pomoc' — a question about the assistant, not about a place."""
    return bool(GENERAL.search(fold(question).strip()))


# F51 "co jest w pobliżu X" / "koło X" / "blisko X" → the location of X, then what is within 500 m
NEARBY = re.compile(r"\b(w poblizu|w okolicy|w okolicach|kolo|blisko|niedaleko|obok)\s+(.+)")
NEARBY_RADIUS_M = 500


def choose_tool(question: str, tool_names: list[str]) -> tuple[str, dict]:
    """Keyword rules: "w pobliżu X" → location of X; features without a named place → search; else check the place
    by name (+ profile)."""
    folded = fold(question)
    near = NEARBY.search(folded)
    if near and "find_location" in tool_names:
        # fold() keeps the length of Polish text, so the match positions cut the original question
        return "find_location", {"query": question[near.start(2):].strip(" ?.!,")}
    features = list(dict.fromkeys(f for pattern, f in FEATURE_WORDS if re.search(pattern, folded)))
    if features and not _names_a_place(question) and "search_accessible_places" in tool_names:
        return "search_accessible_places", {"features": features}
    args = {"place_name": _place_name(question)}
    profile = next((p for pattern, p in PROFILE_WORDS if re.search(pattern, folded)), None)
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


def _yes_labels(summary) -> list[str]:
    keys = [k for k, v in summary.items() if v] if isinstance(summary, dict) else list(summary or [])
    return [_label(k) for k in keys]


def _nearby_line(place: dict) -> str:
    """'Teatr im. Juliusza Słowackiego (Plac Świętego Ducha 1, 12 m, wejście bez schodów)'."""
    details = [place.get("address") or "", f"{place.get('distance_m')} m", *_yes_labels(place.get("accessibility_summary"))]
    return f"{place['name']} ({', '.join(d for d in details if d)})"


def answer_from_data(tool: str, data: dict) -> str:
    """Template answer (Polish) from a tool's result — used without a model and as the model's fallback."""
    if "error" in data:
        return f"Nie udało się pobrać danych: {data['error']}"
    if tool == "find_location":
        return data.get("message") or f"Nie znaleziono lokalizacji „{data.get('query', '')}”."
    if tool == "places_nearby":
        where = (data.get("location") or {}).get("label") or f"{data.get('lat')}, {data.get('lon')}"
        places = data.get("places") or []
        radius = data.get("radius_m", NEARBY_RADIUS_M)
        lead = f"{data['not_found']} " if data.get("not_found") else ""
        if not places:
            return f"{lead}W promieniu {radius} m od: {where} nie mam miejsc w bazie."
        listed = "; ".join(_nearby_line(p) for p in places[:5])
        return f"{lead}W promieniu {radius} m od: {where} jest {data.get('total', len(places))} miejsc. Najbliżej: {listed}."
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


def compact_for_model(tool: str, data: dict) -> dict:
    """Only what the answer needs (no ids, dates, per-feature confidence): a short prompt is much faster on CPU."""
    if "error" in data:
        return data
    if tool == "places_nearby":
        return {"lokalizacja": (data.get("location") or {}).get("label"), "promien_m": data.get("radius_m"),
                "uwaga": data.get("not_found", ""),
                "miejsca": [{"nazwa": p["name"], "adres": p.get("address"), "odleglosc_m": p.get("distance_m"),
                             "jest": _yes_labels(p.get("accessibility_summary"))} for p in (data.get("places") or [])[:5]]}
    if tool == "search_accessible_places":
        return {"razem": data.get("total", 0),
                "miejsca": [{"nazwa": p["name"], "adres": p.get("address")} for p in (data.get("places") or [])[:5]]}
    if not data.get("matches"):
        return {"miejsca": [], "info": data.get("message", "")}
    return {"miejsca": [{
        "nazwa": m["place"]["name"], "adres": m["place"].get("address"), "odpowiedz": m.get("answer"),
        "pewnosc": m.get("confidence"), "porada": m.get("advice"),
        "cechy": {_label(k): "tak" if v.get("value") else "nie"
                  for k, v in (m.get("accessibility") or {}).items() if v.get("value") is not None},
    } for m in data["matches"][:2]]}


def answer_messages(question: str, tool: str, data: dict) -> list[dict]:
    return [
        {"role": "system", "content": "Jesteś asystentem dostępności Krakowa. Odpowiadaj po polsku, krótko (2-4 zdania), "
                                      "wyłącznie na podstawie danych z narzędzia. Cecha 'tak' znaczy, że udogodnienie jest; "
                                      "nie, że go nie ma; brak cechy = brak danych. Nie zgaduj. Podaj pewność danych (0-1). "
                                      "Zacznij od nazwy i adresu znalezionego miejsca."},
        {"role": "user", "content": f"Pytanie: {question}\n\nDane z narzędzia {tool}:\n"
                                    f"{json.dumps(compact_for_model(tool, data), ensure_ascii=False)[:MAX_TOOL_CHARS]}"},
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

    async def _call(self, name: str, args: dict, emit) -> dict:
        emit(("tool_call", {"name": name, "arguments": args, "chosen_by": "chain"}))
        data = await self.tools.call(name, args)
        emit(("tool_result", {"name": name, "result": data}))
        return data

    async def _follow_up(self, name: str, args: dict, data: dict, emit) -> tuple[str, dict]:
        """F51: a location → what is within 500 m of it (the MCP tools again); a place missing by name → its
        location and surroundings. Returns the tool and data the answer is written from."""
        tools = {t["name"] for t in self.tools.definitions}
        not_found = ""
        if (name == "check_accessibility" and not data.get("matches") and "error" not in data
                and "find_location" in tools):
            not_found = data.get("message") or ""
            name, data = "find_location", await self._call("find_location", {"query": args["place_name"]}, emit)
            if not data.get("locations"):
                return "check_accessibility", {"matches": [], "message": not_found}
        if name == "find_location" and data.get("locations") and "places_nearby" in tools:
            location = data["locations"][0]
            nearby = await self._call("places_nearby", {"lat": location["lat"], "lon": location["lon"],
                                                        "radius_m": NEARBY_RADIUS_M}, emit)
            if "error" in nearby:
                return "places_nearby", nearby
            note = (f"{not_found} Pokazuję okolicę tej lokalizacji." if not_found else "")
            return "places_nearby", {**nearby, "location": location, "not_found": note}
        return name, data

    async def ask(self, question: str, emit: Callable[[tuple[str, dict]], None]) -> None:
        emit(("status", {"stage": "received"}))
        if is_general(question):
            emit(("token", {"text": HELP_ANSWER}))
            emit(("done", {"answer": HELP_ANSWER, "model": "rules", "tool": None}))
            return
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
        name, data = await self._follow_up(name, args, data, emit)

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
