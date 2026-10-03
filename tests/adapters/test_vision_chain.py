"""F44: vision fallback chain (Gemini → local ONNX → mock) and its status events."""
import asyncio

import pytest

from app.adapters.outbound import vision_onnx
from app.adapters.outbound.vision_gemini import GeminiVisionAnalyzer
from app.adapters.outbound.vision_mock import FallbackVisionAnalyzer, MockVisionAnalyzer
from app.adapters.outbound.vision_onnx import OnnxPhiVisionAnalyzer
from app.bootstrap import build_vision
from app.config import Settings
from app.domain.model import ImageAnalysis
from tests.application.test_ai import upload
from tests.application.test_observations import user
from tests.conftest import make_use_cases


class Broken:
    LABEL = "broken-model"

    def __init__(self):
        self.calls = 0

    async def analyze(self, image_path, original_name):
        self.calls += 1
        raise RuntimeError("quota exceeded")


class Slow:
    LABEL = "slow-model"

    async def analyze(self, image_path, original_name):
        await asyncio.sleep(1)


class Works:
    LABEL = "works-model"

    async def analyze(self, image_path, original_name):
        return ImageAnalysis(True, True, "stairs without ramp", ["wheelchair"], "Steps.", 0.9, "works-model")


async def test_chain_tries_each_step_until_one_answers():
    first, second = Broken(), Broken()
    chain = FallbackVisionAnalyzer(first, FallbackVisionAnalyzer(second, MockVisionAnalyzer(), 1), 1)
    a = await chain.analyze("x.png", "winda.png")
    assert (first.calls, second.calls, a.model) == (1, 1, "mock")


async def test_chain_reports_each_step():
    events = []
    chain = FallbackVisionAnalyzer(Broken(), FallbackVisionAnalyzer(Works(), MockVisionAnalyzer(), 1), 1)
    a = await chain.analyze("x.png", "x.png", on_step=events.append)
    assert a.model == "works-model"
    assert events == [
        {"stage": "analyzing", "model": "broken-model"},
        {"stage": "fallback", "from": "broken-model", "model": "works-model"},
    ]


async def test_timeout_counts_as_failure():
    events = []
    a = await FallbackVisionAnalyzer(Slow(), MockVisionAnalyzer(), timeout_s=0.05).analyze(
        "x.png", "winda.png", on_step=events.append)
    assert a.model == "mock"
    assert events[-1] == {"stage": "fallback", "from": "slow-model", "model": "mock"}


async def test_no_events_without_a_listener():
    a = await FallbackVisionAnalyzer(Works(), MockVisionAnalyzer(), 1).analyze("x.png", "x.png")
    assert a.model == "works-model"


def test_labels_of_the_real_adapters():
    assert GeminiVisionAnalyzer.LABEL == "gemini"
    assert OnnxPhiVisionAnalyzer.LABEL == "phi-3.5-vision-onnx"
    assert MockVisionAnalyzer.LABEL == "mock"


def test_bootstrap_chain_gemini_onnx_mock(monkeypatch):
    monkeypatch.setattr(vision_onnx, "onnx_available", lambda path: True)
    v = build_vision(Settings(ai_mode="gemini", gemini_api_key="k", ai_vision_fallback="onnx",
                              ai_onnx_timeout_s=120))
    assert isinstance(v.primary, GeminiVisionAnalyzer)
    assert isinstance(v.fallback, FallbackVisionAnalyzer)
    assert isinstance(v.fallback.primary, OnnxPhiVisionAnalyzer) and v.fallback.timeout_s == 120
    assert isinstance(v.fallback.fallback, MockVisionAnalyzer)


def test_bootstrap_skips_onnx_that_cannot_run(monkeypatch):
    monkeypatch.setattr(vision_onnx, "onnx_available", lambda path: False)
    v = build_vision(Settings(ai_mode="gemini", gemini_api_key="k", ai_vision_fallback="onnx"))
    assert isinstance(v.primary, GeminiVisionAnalyzer) and isinstance(v.fallback, MockVisionAnalyzer)


def test_default_fallback_is_mock():
    v = build_vision(Settings(ai_mode="gemini", gemini_api_key="k"))
    assert isinstance(v.fallback, MockVisionAnalyzer)


def test_onnx_available_needs_the_model_folder(tmp_path):
    assert vision_onnx.onnx_available(str(tmp_path / "missing")) is False


@pytest.mark.parametrize("ai_mode", ["mock", "onnx"])
def test_other_modes_unchanged(ai_mode):
    v = build_vision(Settings(ai_mode=ai_mode, ai_vision_fallback="onnx"))
    assert isinstance(v, MockVisionAnalyzer) if ai_mode == "mock" else isinstance(v.primary, OnnxPhiVisionAnalyzer)


async def test_use_case_passes_the_listener():
    events = []
    uc = make_use_cases(vision=FallbackVisionAnalyzer(Broken(), MockVisionAnalyzer(), 1))
    r = await uc.analyze_image(user(uc, "anna"), [await upload(uc, "winda.png")], on_step=events.append)
    assert r.model == "mock" and events[0] == {"stage": "analyzing", "model": "broken-model"}


async def test_use_case_works_with_a_plain_analyzer():
    events = []
    uc = make_use_cases()
    r = await uc.analyze_image(user(uc, "anna"), [await upload(uc, "winda.png")], on_step=events.append)
    assert r.model == "mock" and events == []
