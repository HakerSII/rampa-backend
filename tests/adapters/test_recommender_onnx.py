"""F47: AI_RECOMMENDER=onnx — the local Phi-3.5 turns a query into the same filters as Claude/Gemini (F40 schema)."""
import asyncio

import pytest

from app.adapters.outbound.chat_onnx import OnnxPhiChatModel
from app.adapters.outbound.recommender_onnx import OnnxQueryInterpreter
from app.bootstrap import build_recommender
from app.config import Settings
from app.domain.city import load_city


class FakeModel:
    name = "phi-3.5-vision-onnx"

    def __init__(self, reply='{"profiles": ["stroller"], "features": ["pets_allowed"], "categories": ["gastronomy"]}',
                 state="ready"):
        self.reply, self._state, self.prompts = reply, state, []

    def state(self):
        return self._state

    async def complete(self, messages, max_new_tokens, on_token=None):
        self.prompts.append(messages)
        return self.reply


@pytest.fixture
def city():
    return load_city(None)


def test_query_becomes_filters(city):
    model = FakeModel()
    intent = asyncio.run(OnnxQueryInterpreter(model, city).interpret("kawiarnia, wózek dziecięcy i pies"))
    assert [p.value for p in intent.profiles] == ["stroller"]
    assert [f.value for f in intent.features] == ["pets_allowed"]
    assert intent.categories == ["gastronomy"]
    system = model.prompts[0][0]["content"]
    assert "JSON" in system and "pets_allowed" in system  # the schema is in the prompt


def test_answer_around_json_and_unknown_values(city):
    reply = 'Oto filtry: {"profiles": ["wheelchair", "teleport"], "features": [], "categories": [], "area": "mars"} gotowe'
    intent = asyncio.run(OnnxQueryInterpreter(FakeModel(reply), city).interpret("wózek"))
    assert [p.value for p in intent.profiles] == ["wheelchair"] and intent.area is None


@pytest.mark.parametrize("reply", ["nie wiem", '{"profiles": ', "[1, 2]"])
def test_no_filters_raises(city, reply):
    with pytest.raises(ValueError):
        asyncio.run(OnnxQueryInterpreter(FakeModel(reply), city).interpret("x"))


def test_model_not_ready_raises(city):
    with pytest.raises(RuntimeError):
        asyncio.run(OnnxQueryInterpreter(FakeModel(state="loading"), city).interpret("x"))


def test_model_name(city):
    assert OnnxQueryInterpreter(FakeModel(), city).model == "phi-3.5-vision-onnx"


def test_bootstrap_picks_onnx(city):
    r = build_recommender(Settings(ai_recommender="onnx", ai_model_path="models/a", chat_preload=False, _env_file=None),
                          city)
    assert isinstance(r, OnnxQueryInterpreter) and isinstance(r.llm, OnnxPhiChatModel)
    assert r.llm.model_path == "models/a" and r.llm.state() == "off"


def test_use_case_falls_back_to_rules_when_not_loaded():
    from tests.conftest import make_use_cases
    uc = make_use_cases(recommender=OnnxQueryInterpreter(FakeModel(state="loading"), load_city(None)))
    r = asyncio.run(uc.recommend(None, "kawiarnia z toaletą dla wózka", None, None, None, 5))
    assert r.model == "rules"


def test_truncated_json_is_repaired(city):
    reply = '{"profiles": ["wheelchair"], "features": ["elevator"'
    intent = asyncio.run(OnnxQueryInterpreter(FakeModel(reply), city).interpret("winda"))
    assert [p.value for p in intent.profiles] == ["wheelchair"] and [f.value for f in intent.features] == ["elevator"]


def test_prompt_is_short_with_examples(city):
    model = FakeModel()
    asyncio.run(OnnxQueryInterpreter(model, city).interpret("x"))
    system = model.prompts[0][0]["content"]
    assert len(system) < 1800 and "->" in system and '"type"' not in system


def test_copying_the_vocabulary_keeps_only_categories_and_area(city):
    """Over-listed profiles/features come from the rules instead; the model's category and area stay."""
    reply = ('{"profiles": ["wheelchair", "crutches", "stroller", "blind"], "features": ["step_free_entrance", "ramp", '
             '"lowered_curb", "wide_doors", "baby_changing_table"], "categories": ["culture"], "area": "kazimierz"}')
    intent = asyncio.run(OnnxQueryInterpreter(FakeModel(reply), city).interpret("muzeum z windą, jestem na wózku"))
    assert [p.value for p in intent.profiles] == ["wheelchair"]
    assert [f.value for f in intent.features] == ["elevator"]
    assert intent.categories == ["culture"] and intent.area == "kazimierz"


def test_recommender_uses_the_ai_timeout(city):
    r = build_recommender(Settings(ai_recommender="onnx", ai_timeout_s=33, chat_preload=False, _env_file=None), city)
    assert r.llm.timeout_s == 33
