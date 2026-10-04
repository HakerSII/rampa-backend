"""F46: the chat assistant — tool choice (model JSON or rules), tool run, answer (model or template), events."""
import asyncio

import pytest

from app.application.chat import ChatAssistant, answer_from_data, choose_tool, compact_for_model, parse_tool_call
from clients.rampa_tools import TOOL_DEFS

TOOLS = [t["name"] for t in TOOL_DEFS]
MNK = {"query": "Muzeum Narodowe", "profile": "wheelchair", "total_found": 1, "matches": [{
    "place": {"id": "plc_mnk", "name": "Muzeum Narodowe w Krakowie", "address": "al. 3 Maja 1", "category": "museum"},
    "answer": "yes", "confidence": 0.5, "advice": "Wejście bez barier potwierdzone.",
    "accessibility": {"elevator": {"value": True, "confidence": 0.5}, "ramp": {"value": False, "confidence": 0.4}}}]}


class FakeTools:
    definitions = TOOL_DEFS

    def __init__(self, result=None):
        self.calls = []
        self.result = result if result is not None else MNK

    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        return self.result


class FakeModel:
    """Answers from a script: first the tool choice, then the answer (streamed in two pieces)."""
    name = "fake-phi"

    def __init__(self, choice='{"tool": "check_accessibility", "arguments": {"place_name": "Wawel"}}',
                 answer="Tak, jest winda.", state="ready", fail=False):
        self.replies = [choice, answer]
        self._state = state
        self.fail = fail
        self.prompts = []

    def state(self):
        return self._state

    async def complete(self, messages, max_new_tokens, on_token=None):
        self.prompts.append(messages)
        if self.fail:
            raise RuntimeError("out of memory")
        text = self.replies.pop(0)
        if on_token:
            for piece in (text[: len(text) // 2], text[len(text) // 2:]):
                on_token(piece)
        return text


def run(assistant, question):
    events = []
    asyncio.run(assistant.ask(question, events.append))
    return events


def names(events):
    return [e[0] for e in events]


# --- rules ---------------------------------------------------------------

@pytest.mark.parametrize("question, place", [
    ("Czy Muzeum Narodowe jest dostępne na wózku?", "Muzeum Narodowe"),
    ("Czy do Teatru Słowackiego wejdę z wózkiem dziecięcym?", "Teatru Słowackiego"),
    ("Wawel", "Wawel"),
])
def test_rules_pick_check_accessibility_with_the_place(question, place):
    name, args = choose_tool(question, TOOLS)
    assert (name, args["place_name"]) == ("check_accessibility", place)


def test_rules_pick_search_for_features_without_a_place():
    name, args = choose_tool("Gdzie jest winda i toaleta dla niepełnosprawnych?", TOOLS)
    assert name == "search_accessible_places" and args == {"features": ["elevator", "accessible_toilet"]}


def test_rules_profile_from_the_question():
    assert choose_tool("Czy do Muzeum Narodowego wjadę z wózkiem dziecięcym?", TOOLS)[1].get("profile") == "stroller"


def test_parse_tool_call():
    assert parse_tool_call('ok {"tool": "check_accessibility", "arguments": {"place_name": "Wawel"}} ', TOOL_DEFS) == \
        ("check_accessibility", {"place_name": "Wawel"})
    for bad in ["nie wiem", '{"tool": "rm_rf", "arguments": {}}', '{"tool": "check_accessibility", "arguments": {}}',
                '{"tool": "check_accessibility"']:
        assert parse_tool_call(bad, TOOL_DEFS) is None


def test_template_answer_names_the_place_and_facts():
    text = answer_from_data("check_accessibility", MNK)
    assert "Muzeum Narodowe w Krakowie" in text and "Wejście bez barier potwierdzone." in text
    assert "winda" in text.lower() and "50%" in text


def test_template_answer_when_nothing_found():
    text = answer_from_data("check_accessibility", {"query": "Xyz", "matches": [], "message": "Nie znaleziono miejsca „Xyz”."})
    assert "Nie znaleziono" in text


def test_template_answer_for_search():
    data = {"features": ["elevator"], "total": 2, "places": [{"name": "A", "address": "ul. 1"}, {"name": "B", "address": None}]}
    text = answer_from_data("search_accessible_places", data)
    assert "A" in text and "B" in text and "2" in text


# --- the assistant ---------------------------------------------------------

def test_rules_mode_events():
    tools = FakeTools()
    events = run(ChatAssistant(None, tools), "Czy Muzeum Narodowe jest dostępne na wózku?")
    assert events[0] == ("status", {"stage": "received"})
    assert ("tool_call", {"name": "check_accessibility", "arguments": {"place_name": "Muzeum Narodowe"},
                          "chosen_by": "rules"}) in events
    assert ("tool_result", {"name": "check_accessibility", "result": MNK}) in events
    assert "token" in names(events)
    done = events[-1]
    assert done[0] == "done" and done[1]["model"] == "rules" and done[1]["tool"] == "check_accessibility"
    assert "Muzeum Narodowe w Krakowie" in done[1]["answer"]


def test_model_mode_events_and_streamed_answer():
    model = FakeModel()
    tools = FakeTools()
    events = run(ChatAssistant(model, tools), "Czy Wawel jest dostępny?")
    assert ("status", {"stage": "choosing_tool", "model": "fake-phi"}) in events
    assert tools.calls == [("check_accessibility", {"place_name": "Wawel"})]
    assert ("tool_call", {"name": "check_accessibility", "arguments": {"place_name": "Wawel"}, "chosen_by": "model"}) in events
    assert [e[1]["text"] for e in events if e[0] == "token"] == ["Tak, jes", "t winda."]
    assert events[-1] == ("done", {"answer": "Tak, jest winda.", "model": "fake-phi", "tool": "check_accessibility"})
    # the answer prompt carries the tool's data
    assert "Muzeum Narodowe w Krakowie" in model.prompts[1][-1]["content"]


def test_invalid_model_choice_falls_back_to_rules():
    tools = FakeTools()
    events = run(ChatAssistant(FakeModel(choice="Nie wiem."), tools), "Czy Muzeum Narodowe jest dostępne?")
    call = next(e[1] for e in events if e[0] == "tool_call")
    assert call["chosen_by"] == "rules" and call["arguments"] == {"place_name": "Muzeum Narodowe"}


def test_model_not_loaded_yet_uses_rules():
    events = run(ChatAssistant(FakeModel(state="loading"), FakeTools()), "Wawel")
    assert ("status", {"stage": "model_loading"}) in events and events[-1][1]["model"] == "rules"


def test_model_error_falls_back_to_the_template():
    events = run(ChatAssistant(FakeModel(fail=True), FakeTools()), "Czy Muzeum Narodowe jest dostępne?")
    assert events[-1][0] == "done" and events[-1][1]["model"] == "rules"
    assert "Muzeum Narodowe w Krakowie" in events[-1][1]["answer"]


def test_empty_model_answer_falls_back_to_the_template():
    events = run(ChatAssistant(FakeModel(answer="   "), FakeTools()), "Wawel")
    assert "Muzeum Narodowe w Krakowie" in events[-1][1]["answer"] and events[-1][1]["model"] == "rules"


def test_tool_error_is_reported_in_the_answer():
    events = run(ChatAssistant(None, FakeTools({"error": "Kraków bez barier API niedostępne: 500"})), "Wawel")
    assert events[-1][0] == "done" and "niedostępne" in events[-1][1]["answer"]


def test_tool_data_for_the_model_is_compact():
    data = compact_for_model("check_accessibility", MNK)
    assert data == {"miejsca": [{"nazwa": "Muzeum Narodowe w Krakowie", "adres": "al. 3 Maja 1", "odpowiedz": "yes",
                                 "pewnosc": 0.5, "porada": "Wejście bez barier potwierdzone.",
                                 "cechy": {"winda": "tak", "podjazd": "nie"}}]}
    assert compact_for_model("search_accessible_places", {"places": [{"id": "x", "name": "A", "address": "ul. 1",
                                                                      "accessibility_summary": {}}], "total": 1}) ==         {"razem": 1, "miejsca": [{"nazwa": "A", "adres": "ul. 1"}]}
    assert compact_for_model("check_accessibility", {"error": "x"}) == {"error": "x"}


def test_rules_without_polish_letters():
    assert choose_tool("wysoki prog", TOOLS) == ("search_accessible_places", {"features": ["step_free_entrance"]})
    assert choose_tool("plywalnia akf", TOOLS)[1]["place_name"] == "plywalnia akf"


@pytest.mark.parametrize("question", ["jakie miejsca znasz?", "Co potrafisz", "pomoc", "Jakie miejsca są w bazie?"])
def test_general_questions_get_help_without_a_tool(question):
    tools = FakeTools()
    events = run(ChatAssistant(None, tools), question)
    assert tools.calls == [] and "tool_call" not in names(events)
    done = events[-1][1]
    assert done["tool"] is None and done["model"] == "rules" and "Muzeum Narodowe" in done["answer"]


@pytest.mark.parametrize("question", [
    "czy do teatru na słowackiego wjade wozkiem ?",
    "czy do teatru na slowackiego wjade wozkiem",
    "Czy wjadę wózkiem do Teatru Słowackiego?",
    "teatr słowackiego na wózku",
])
def test_everyday_questions_find_the_place(question):
    from app.domain.text import name_matches
    name, args = choose_tool(question, TOOLS)
    assert name == "check_accessibility"
    assert name_matches(args["place_name"], "Teatr im. Juliusza Słowackiego"), args
