"""F46: local Phi-3.5 chat model — prompt format, background loading, shared model, timeout."""
import asyncio
import threading
import time

import pytest

from app.adapters.outbound import chat_onnx, phi_onnx
from app.adapters.outbound.chat_onnx import OnnxPhiChatModel, build_prompt
from app.bootstrap import build_chat_model
from app.config import Settings


def test_prompt_format():
    assert build_prompt([{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}]) == \
        "<|system|>\nS<|end|>\n<|user|>\nQ<|end|>\n<|assistant|>\n"


class FakeLoaded:
    def __init__(self, tokens=("Tak", ", jest", " winda."), delay=0.0):
        self.tokens, self.delay = tokens, delay


@pytest.fixture
def fake_phi(monkeypatch):
    """phi_onnx.load → a fake; chat_onnx._generate → yields the fake's tokens."""
    loads = []

    def load(path):
        loads.append(path)
        return FakeLoaded()

    def generate(loaded, prompt, max_new_tokens, cancel):
        for t in loaded.tokens:
            if cancel.is_set():
                return
            time.sleep(loaded.delay)
            yield t

    monkeypatch.setattr(phi_onnx, "load", load)
    monkeypatch.setattr(chat_onnx, "_generate", generate)
    return loads


def test_loads_in_the_background_and_becomes_ready(fake_phi):
    m = OnnxPhiChatModel("models/x")
    assert m.state() == "off"
    m.start_loading()
    for _ in range(100):
        if m.state() == "ready":
            break
        time.sleep(0.01)
    assert m.state() == "ready" and fake_phi == ["models/x"]


def test_load_failure_is_error_state(monkeypatch):
    monkeypatch.setattr(phi_onnx, "load", lambda path: (_ for _ in ()).throw(RuntimeError("no model")))
    m = OnnxPhiChatModel("models/x")
    m.start_loading()
    m._thread.join(2)
    assert m.state() == "error"


def test_complete_streams_tokens(fake_phi):
    m = OnnxPhiChatModel("models/x")
    m.load_now()
    pieces = []
    text = asyncio.run(m.complete([{"role": "user", "content": "Q"}], 50, on_token=pieces.append))
    assert text == "Tak, jest winda." and pieces == ["Tak", ", jest", " winda."]


def test_complete_before_ready_raises(fake_phi):
    with pytest.raises(RuntimeError):
        asyncio.run(OnnxPhiChatModel("models/x").complete([], 10))


def test_timeout_stops_generation(fake_phi, monkeypatch):
    m = OnnxPhiChatModel("models/x", timeout_s=0.05)
    m.load_now()
    m._loaded.delay = 0.2
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(m.complete([{"role": "user", "content": "Q"}], 50))


def test_shared_loader_loads_once(monkeypatch):
    calls = []

    class FakeOg:
        class Model:
            def __init__(self, path):
                calls.append(path)

            def create_multimodal_processor(self):
                return "processor"

    monkeypatch.setattr(phi_onnx, "_og", lambda: FakeOg)
    monkeypatch.setattr(phi_onnx, "_LOADED", {})
    a, b = phi_onnx.load("m"), phi_onnx.load("m")
    assert a is b and calls == ["m"] and a.processor == "processor"
    assert isinstance(phi_onnx.RUN_LOCK, type(threading.Lock()))


def test_bootstrap_modes(monkeypatch):
    assert build_chat_model(Settings(chat_mode="rules")) is None
    assert build_chat_model(Settings(chat_mode="off")) is None
    m = build_chat_model(Settings(chat_mode="onnx", ai_model_path="models/a"))
    assert isinstance(m, OnnxPhiChatModel) and m.model_path == "models/a"
    assert build_chat_model(Settings(chat_mode="onnx", chat_model_path="models/b")).model_path == "models/b"
