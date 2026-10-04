"""F46 over HTTP: chat status + streamed answer; tools run in-process against the Open API (real seed data)."""
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings
from tests.api.test_vision_stream_api import events


def client(tmp_path, **kw):
    return TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path), **kw)))


def ask(c, question):
    return c.post("/api/v1/ai/chat/stream", json={"question": question})


def test_status_rules_mode(tmp_path):
    r = client(tmp_path).get("/api/v1/ai/chat/status")
    assert r.status_code == 200
    assert r.json() == {"mode": "rules", "state": "rules", "model": "rules",
                        "tools": ["check_accessibility", "search_accessible_places"]}


def test_stream_answers_from_the_database_as_a_guest(tmp_path):
    r = ask(client(tmp_path), "Czy Muzeum Narodowe jest dostępne na wózku?")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    ev = [e for e in events(r.text) if e[0] != "comment"]
    assert ev[0] == ("status", {"stage": "received"})
    call = next(d for n, d in ev if n == "tool_call")
    assert call["name"] == "check_accessibility" and call["arguments"]["place_name"] == "Muzeum Narodowe"
    result = next(d for n, d in ev if n == "tool_result")["result"]
    assert result["matches"][0]["place"]["id"] == "plc_mnk"
    name, done = ev[-1]
    assert name == "done" and done["model"] == "rules" and "Muzeum Narodowe w Krakowie" in done["answer"]
    assert "".join(d["text"] for n, d in ev if n == "token") == done["answer"]


def test_stream_search_by_features(tmp_path):
    ev = [e for e in events(ask(client(tmp_path), "Gdzie jest winda?").text) if e[0] != "comment"]
    assert next(d for n, d in ev if n == "tool_call")["name"] == "search_accessible_places"
    assert ev[-1][0] == "done"


def test_question_is_validated(tmp_path):
    c = client(tmp_path)
    assert ask(c, "").status_code == 400
    assert ask(c, "x" * 501).status_code == 400


def test_chat_off(tmp_path):
    c = client(tmp_path, chat_mode="off")
    assert c.get("/api/v1/ai/chat/status").json()["state"] == "off"
    r = ask(c, "Wawel")
    assert r.status_code == 503 and r.json()["error"]["code"] == "CHAT_DISABLED"


def test_onnx_mode_without_model_still_answers(tmp_path):
    c = client(tmp_path, chat_mode="onnx", ai_model_path=str(tmp_path / "missing"), chat_preload=False)
    assert c.get("/api/v1/ai/chat/status").json()["state"] in ("off", "error")
    ev = [e for e in events(ask(c, "Czy Muzeum Narodowe jest dostępne?").text) if e[0] != "comment"]
    assert ("status", {"stage": "model_loading"}) in ev and ev[-1][0] == "done" and ev[-1][1]["model"] == "rules"
