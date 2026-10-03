"""Gemini adapter against httpx.MockTransport — no network, no real key."""
import base64
import json

import httpx
import pytest

from app.adapters.outbound.vision_gemini import GeminiVisionAnalyzer
from app.adapters.outbound.vision_mock import FallbackVisionAnalyzer, MockVisionAnalyzer
from app.bootstrap import build_vision
from app.config import Settings
from tests.application.test_observations import PNG

ANALYSIS = {"real_place": True, "barrier_detected": True, "barrier_type": "stairs without ramp",
            "affected_disabilities": ["wheelchair"], "description": "Three steps at the entrance.", "confidence": 0.88}


def gemini_reply(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}], "role": "model"}}]}


@pytest.fixture
def photo(tmp_path):
    p = tmp_path / "schody.png"
    p.write_bytes(PNG)
    return str(p)


def analyzer(handler, key="secret-key") -> tuple[GeminiVisionAnalyzer, list]:
    seen = []

    def record(request: httpx.Request):
        seen.append(request)
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return GeminiVisionAnalyzer(key, model="gemini-test", api_url="https://gemini.example/v1beta", http=client), seen


async def test_request_shape_and_parsed_result(photo):
    g, seen = analyzer(lambda r: httpx.Response(200, json=gemini_reply(json.dumps(ANALYSIS))))
    a = await g.analyze(photo, "schody.png")
    (req,) = seen
    assert str(req.url) == "https://gemini.example/v1beta/models/gemini-test:generateContent"
    assert req.headers["x-goog-api-key"] == "secret-key" and "key=" not in str(req.url)
    body = json.loads(req.content)
    text_part, image_part = body["contents"][0]["parts"]
    assert "accessibility inspector" in text_part["text"]
    assert image_part["inline_data"] == {"mime_type": "image/png", "data": base64.b64encode(PNG).decode()}
    assert body["generationConfig"]["response_mime_type"] == "application/json"
    assert (a.barrier_type, a.confidence, a.model) == ("stairs without ramp", 0.88, "gemini")


async def test_json_wrapped_in_markdown_is_parsed(photo):
    g, _ = analyzer(lambda r: httpx.Response(200, json=gemini_reply("```json\n" + json.dumps(ANALYSIS) + "\n```")))
    assert (await g.analyze(photo, "x.png")).real_place is True


@pytest.mark.parametrize("response", [
    httpx.Response(400, json={"error": {"message": "API key not valid"}}),
    httpx.Response(503, text="overloaded"),
    httpx.Response(200, json={"candidates": []}),                       # blocked / empty
    httpx.Response(200, json=gemini_reply("I cannot help with that")),  # no JSON
])
async def test_failures_raise(photo, response):
    g, _ = analyzer(lambda r: response)
    with pytest.raises(Exception):
        await g.analyze(photo, "x.png")


async def test_missing_key_raises_without_calling_api(photo):
    g, seen = analyzer(lambda r: httpx.Response(200, json=gemini_reply("{}")), key="")
    with pytest.raises(ValueError):
        await g.analyze(photo, "x.png")
    assert seen == []


async def test_gemini_failure_falls_back_to_mock(photo):
    g, _ = analyzer(lambda r: httpx.Response(500, text="boom"))
    a = await FallbackVisionAnalyzer(g, MockVisionAnalyzer(), timeout_s=5).analyze(photo, "winda.png")
    assert a.model == "mock" and a.barrier_type == "elevator out of order"


def test_bootstrap_selects_gemini_from_config():
    v = build_vision(Settings(ai_mode="gemini", gemini_api_key="k", gemini_model="gemini-x"))
    assert isinstance(v, FallbackVisionAnalyzer) and isinstance(v.primary, GeminiVisionAnalyzer)
    assert v.primary.model == "gemini-x"
    assert isinstance(build_vision(Settings(ai_mode="mock")), MockVisionAnalyzer)
