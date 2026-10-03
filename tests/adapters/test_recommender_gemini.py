"""F30b: Gemini as the recommendation interpreter (function calling, forced). Only filters come back — never facts.
httpx.MockTransport — no network, no quota."""
import json

import httpx
import pytest

from app.adapters.outbound.recommender_gemini import GeminiQueryInterpreter
from app.bootstrap import build_recommender
from app.config import Settings
from app.domain.city import load_city
from app.domain.enums import FeatureKey as F, NeedsProfile as P


def gemini_reply(args: dict):
    return {"candidates": [{"content": {"parts": [{"functionCall": {"name": "set_filters", "args": args}}]}}]}


async def test_gemini_interpreter_parses_function_call():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=gemini_reply(
            {"profiles": ["stroller", "teleport"], "features": ["pets_allowed"], "categories": ["gastronomy"],
             "area": "centrum"}))
    g = GeminiQueryInterpreter("g-key", "gemini-3.8-flash", "https://gemini.example/v1beta",
                               transport=httpx.MockTransport(handler))
    intent = await g.interpret("restauracja w centrum, wózek dziecięcy i pies")
    assert (intent.profiles, intent.features, intent.categories, intent.area) == (
        [P.STROLLER], [F.PETS_ALLOWED], ["gastronomy"], "centrum")          # unknown enum value dropped
    req = seen[0]
    assert req.url.path == "/v1beta/models/gemini-3.8-flash:generateContent"
    assert req.headers["x-goog-api-key"] == "g-key" and "key=" not in str(req.url)   # key never in the URL
    body = json.loads(req.content)
    assert body["toolConfig"]["functionCallingConfig"] == {"mode": "ANY", "allowedFunctionNames": ["set_filters"]}
    decl = body["tools"][0]["functionDeclarations"][0]
    assert decl["name"] == "set_filters" and "kazimierz" in decl["parameters"]["properties"]["area"]["enum"]
    assert g.model == "gemini-3.8-flash"


async def test_gemini_without_function_call_raises():
    g = GeminiQueryInterpreter("k", "m", "https://g.example", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "hi"}]}}]})))
    with pytest.raises(ValueError):
        await g.interpret("x")


async def test_gemini_quota_error_raises_so_use_case_falls_back():
    g = GeminiQueryInterpreter("k", "m", "https://g.example",
                               transport=httpx.MockTransport(lambda r: httpx.Response(429, json={})))
    with pytest.raises(httpx.HTTPStatusError):
        await g.interpret("x")


def test_bootstrap_picks_gemini_and_needs_key():
    city = load_city()
    r = build_recommender(Settings(ai_recommender="gemini", gemini_api_key="k", _env_file=None), city)
    assert isinstance(r, GeminiQueryInterpreter) and r.model == "gemini-3.8-flash"
    assert build_recommender(Settings(ai_recommender="gemini", gemini_api_key="", _env_file=None), city) is None
    assert build_recommender(Settings(ai_recommender="rules", _env_file=None), city) is None


async def test_claude_and_gemini_send_the_same_tool_schema():
    """F40 A: one filter schema (app/domain/recommend.py) for every provider — no drift possible."""
    from app.adapters.outbound.recommender_claude import ClaudeQueryInterpreter
    from app.domain.recommend import filters_schema
    bodies = {}

    def claude(request):
        bodies["claude"] = json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "tool_use", "name": "set_filters", "input": {}}]})

    def gemini(request):
        bodies["gemini"] = json.loads(request.content)
        return httpx.Response(200, json=gemini_reply({}))
    await ClaudeQueryInterpreter("k", "c", transport=httpx.MockTransport(claude)).interpret("x")
    await GeminiQueryInterpreter("k", "g", "https://g.example", transport=httpx.MockTransport(gemini)).interpret("x")
    claude_schema = bodies["claude"]["tools"][0]["input_schema"]
    gemini_schema = bodies["gemini"]["tools"][0]["functionDeclarations"][0]["parameters"]
    assert claude_schema == gemini_schema == filters_schema(load_city())
    assert bodies["claude"]["system"] == bodies["gemini"]["systemInstruction"]["parts"][0]["text"]
