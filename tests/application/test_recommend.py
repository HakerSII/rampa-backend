"""F30: natural-language recommendations. The interpreter only produces needs + filters;
every fact in the answer (state, source, date) comes from the database; unknown/stale data → `missing`."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.adapters.outbound.recommender_claude import ClaudeQueryInterpreter
from app.config import Settings
from app.domain.enums import FeatureKey as F, NeedsProfile as P
from app.domain.errors import ValidationFailed
from app.domain.recommend import Intent, interpret_rules
from tests.conftest import make_use_cases


# ---------------------------------------------------------------- rules interpreter (pure)
@pytest.mark.parametrize("query, profiles, features, categories, area", [
    ("kawiarnia w centrum, wjadę wózkiem", [P.WHEELCHAIR], [], ["gastronomy"], "centrum"),
    ("restauracja w centrum, wejdę z wózkiem dziecięcym i psem", [P.STROLLER], [F.PETS_ALLOWED], ["gastronomy"],
     "centrum"),
    ("muzeum dla osoby niewidomej z psem asystującym", [P.BLIND, P.ASSISTANCE_DOG], [], ["culture"], None),
    ("urząd z pętlą indukcyjną, jestem osobą głuchą", [P.DEAF], [F.INDUCTION_LOOP], ["services"], None),
    ("museum with a wheelchair accessible toilet", [P.WHEELCHAIR], [F.ACCESSIBLE_TOILET], ["culture"], None),
    ("coś miłego", [], [], [], None),
])
def test_rules_interpreter(query, profiles, features, categories, area):
    i = interpret_rules(query)
    assert (i.profiles, i.features, i.categories, i.area) == (profiles, features, categories, area)


# ---------------------------------------------------------------- use case
async def test_recommend_ranks_by_data_and_explains():
    uc = make_use_cases()
    r = await uc.recommend(None, "kawiarnia lub muzeum w centrum, wjadę wózkiem")
    assert r.model == "rules"
    first = r.items[0]
    assert first.place.id == "plc_camelot" and first.match == "yes"     # cafe in the centre, ramp yes
    ramp = next(x for x in first.reasons if x.feature == F.RAMP)
    assert ramp.state == "yes" and ramp.source and ramp.last_verified is not None


async def test_missing_data_is_listed_never_guessed():
    uc = make_use_cases()
    r = await uc.recommend(None, "muzeum, wejdę z wózkiem dziecięcym i psem")
    mnk = next(x for x in r.items if x.place.id == "plc_mnk")
    assert mnk.match == "partial" and F.PETS_ALLOWED in mnk.missing       # nobody said whether pets may enter
    states = uc.get_accessibility("plc_mnk")
    for reason in mnk.reasons:                                            # every fact = the DB state
        assert reason.state == states[reason.feature].state


async def test_bad_answers_go_last_and_profile_param_merges():
    uc = make_use_cases()
    r = await uc.recommend(None, "urząd albo muzeum", profile=P.WHEELCHAIR)
    assert [x.place.id for x in r.items][-1] == "plc_urzad" and r.items[-1].match == "no"
    assert P.WHEELCHAIR in r.intent.profiles


async def test_unrecognised_query_says_so():
    uc = make_use_cases()
    r = await uc.recommend(None, "coś miłego")
    assert r.items and "nie rozpoznano" in r.note.lower()


class FailingInterpreter:
    model = "claude-test"

    async def interpret(self, query):
        raise httpx.ConnectError("offline")


class FixedInterpreter:
    model = "claude-test"

    async def interpret(self, query):
        return Intent(profiles=[P.DEAF], features=[], categories=["services"])


async def test_model_interpreter_used_and_falls_back_to_rules():
    uc = make_use_cases(recommender=FixedInterpreter())
    r = await uc.recommend(None, "cokolwiek")
    assert r.model == "claude-test" and r.items[0].place.id == "plc_urzad"  # deaf: induction loop yes
    uc = make_use_cases(recommender=FailingInterpreter())
    r = await uc.recommend(None, "kawiarnia, wózek")
    assert r.model == "rules" and r.intent.categories == ["gastronomy"]


@pytest.mark.parametrize("query", ["", "   ", "x" * 501])
async def test_query_validation(query):
    with pytest.raises(ValidationFailed):
        await make_use_cases().recommend(None, query)


# ---------------------------------------------------------------- Claude adapter
def claude_reply(intent: dict):
    return {"content": [{"type": "tool_use", "name": "set_filters", "input": intent}], "stop_reason": "tool_use"}


async def test_claude_interpreter_parses_tool_call_and_never_sends_db_facts():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=claude_reply(
            {"profiles": ["wheelchair", "nonsense"], "features": ["accessible_toilet"], "categories": ["gastronomy", "zoo"],
             "area": "centrum"}))
    interp = ClaudeQueryInterpreter("k-test", "claude-sonnet-5-5", transport=httpx.MockTransport(handler))
    intent = await interp.interpret("restauracja w centrum z toaletą, jeżdżę na wózku")
    assert (intent.profiles, intent.features, intent.categories, intent.area) == (
        [P.WHEELCHAIR], [F.ACCESSIBLE_TOILET], ["gastronomy"], "centrum")       # unknown enum values dropped
    req = seen[0]
    assert req.headers["x-api-key"] == "k-test" and req.headers["anthropic-version"]
    body = json.loads(req.content)
    assert body["model"] == "claude-sonnet-5-5" and body["tool_choice"] == {"type": "tool", "name": "set_filters"}


async def test_claude_interpreter_without_tool_call_raises():
    interp = ClaudeQueryInterpreter("k", "m", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"content": [{"type": "text", "text": "hi"}]})))
    with pytest.raises(ValueError):
        await interp.interpret("x")


# ---------------------------------------------------------------- HTTP
def test_recommend_endpoint_guest(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    r = c.post("/api/v1/ai/recommend", json={"query": "muzeum, wózek dziecięcy i pies", "limit": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "rules" and len(body["items"]) == 2
    assert body["intent"]["profiles"] == ["stroller"] and "pets_allowed" in body["items"][0]["missing"]
    assert c.post("/api/v1/ai/recommend", json={"query": ""}).status_code == 400
