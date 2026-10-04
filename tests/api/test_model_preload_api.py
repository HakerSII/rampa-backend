"""F48 over HTTP: the app starts loading the local model at start when any AI setting uses it; /health shows its state."""
import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.adapters.outbound import phi_onnx
from app.config import Settings


@pytest.fixture
def preloads(monkeypatch):
    calls = []

    class Done:
        def join(self, timeout=None):
            pass

    monkeypatch.setattr(phi_onnx, "preload", lambda path: calls.append(path) or Done())
    return calls


def app(tmp_path, **kw):
    return create_app(Settings(repo_mode="memory", media_dir=str(tmp_path), _env_file=None, **kw))


@pytest.mark.parametrize("kw", [
    {"ai_mode": "onnx"},
    {"ai_mode": "gemini", "gemini_api_key": "k", "ai_vision_fallback": "onnx"},
    {"chat_mode": "onnx"},
    {"ai_recommender": "onnx"},
])
def test_preloads_when_a_setting_uses_the_local_model(tmp_path, preloads, kw):
    app(tmp_path, ai_model_path="models/m", chat_preload=True, **kw)
    assert preloads == ["models/m"]


def test_no_preload_without_local_model_or_when_disabled(tmp_path, preloads):
    app(tmp_path, chat_preload=True)  # mock / rules everywhere
    app(tmp_path, ai_mode="onnx")  # CHAT_PRELOAD defaults to false
    app(tmp_path, ai_mode="onnx", chat_preload=False)
    assert preloads == []


def test_health_shows_the_local_model(tmp_path, preloads, monkeypatch):
    monkeypatch.setattr(phi_onnx, "state", lambda path: {"state": "downloading", "detail": "1.2 / 2.6 GB"})
    body = TestClient(app(tmp_path, ai_mode="onnx", ai_model_path="models/m", chat_preload=True)).get("/health").json()
    assert body["local_model"] == {"path": "models/m", "state": "downloading", "detail": "1.2 / 2.6 GB"}


def test_health_without_local_model(tmp_path, preloads):
    assert TestClient(app(tmp_path)).get("/health").json()["local_model"] is None


def test_docker_image_has_the_ai_extra():
    from pathlib import Path
    dockerfile = (Path(__file__).parents[2] / "Dockerfile").read_text(encoding="utf-8")
    assert "--extra ai" in dockerfile
