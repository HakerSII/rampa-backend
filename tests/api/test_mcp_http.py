"""F41: remote MCP — the same tools over Streamable HTTP (/mcp) for Claude, Gemini CLI, Grok … on another machine.
In-process: MCP HTTP app via Starlette TestClient; its backend = our FastAPI app over ASGI (no network)."""
import json

import httpx
import pytest

pytest.importorskip("fastmcp")
from starlette.testclient import TestClient  # noqa: E402

from app.adapters.inbound.http.main import create_app  # noqa: E402
from app.config import Settings  # noqa: E402
from tests.conftest import NOW  # noqa: E402

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rpc(method: str, params: dict | None = None, id_: int = 1) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})


def body(r) -> dict:
    """JSON response, or the last `data:` line of an SSE response."""
    if r.headers.get("content-type", "").startswith("application/json"):
        return r.json()
    data = [line[5:].strip() for line in r.text.splitlines() if line.startswith("data:")]
    return json.loads(data[-1])


@pytest.fixture
def mcp_client(tmp_path, monkeypatch):
    from clients import mcp_server
    backend = create_app(Settings(demo_now=NOW, media_dir=str(tmp_path), public_api_keys="k"))
    monkeypatch.setattr(mcp_server, "_client", lambda: httpx.AsyncClient(
        transport=httpx.ASGITransport(app=backend), base_url="http://backend"))
    monkeypatch.setenv("RAMPA_API_KEY", "k")

    def make(token: str = ""):
        monkeypatch.setenv("MCP_AUTH_TOKEN", token)
        return TestClient(mcp_server.build_http_app(), base_url="https://rampa-mcp.onrender.com")
    return make


def test_health_and_tools_over_http(mcp_client):
    with mcp_client() as c:
        assert c.get("/health").json() == {"status": "ok", "transport": "http", "path": "/mcp"}
        init = c.post("/mcp", headers=HEADERS, content=rpc("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}))
        assert init.status_code == 200 and body(init)["result"]["serverInfo"]["name"] == "Kraków bez barier"
        tools = body(c.post("/mcp", headers=HEADERS, content=rpc("tools/list", id_=2)))["result"]["tools"]
        assert {t["name"] for t in tools} >= {"check_accessibility", "search_accessible_places"}
        call = body(c.post("/mcp", headers=HEADERS, content=rpc("tools/call", {
            "name": "check_accessibility", "arguments": {"place_name": "Muzeum Narodowe"}}, id_=3)))
        (match,) = json.loads(call["result"]["content"][0]["text"])["matches"]
        assert (match["place"]["id"], match["answer"]) == ("plc_mnk", "yes")


def test_optional_bearer_token(mcp_client):
    with mcp_client(token="s3cret") as c:
        assert c.post("/mcp", headers=HEADERS, content=rpc("tools/list")).status_code == 401
        ok = c.post("/mcp", headers={**HEADERS, "Authorization": "Bearer s3cret"}, content=rpc("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}))
        assert ok.status_code == 200
        assert c.get("/health").status_code == 200          # health stays open for Render


def test_mcpenv_file_is_loaded_without_overriding_real_env(tmp_path, monkeypatch):
    """F41: the MCP service has its own env file (.mcpenv); real env vars (Render dashboard) win."""
    from clients import mcp_server
    env = tmp_path / ".mcpenv"
    env.write_text("RAMPA_API_URL=https://backend.example\nRAMPA_API_KEY=from-file\nMCP_AUTH_TOKEN=tok\n",
                   encoding="utf-8")
    monkeypatch.delenv("RAMPA_API_URL", raising=False)
    monkeypatch.setenv("RAMPA_API_KEY", "from-env")
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    assert mcp_server.load_env_file(str(env)) is True
    import os
    assert os.environ["RAMPA_API_URL"] == "https://backend.example"
    assert os.environ["RAMPA_API_KEY"] == "from-env"                  # not overridden
    assert os.environ["MCP_AUTH_TOKEN"] == "tok"
    monkeypatch.delenv("RAMPA_API_URL")
    monkeypatch.delenv("MCP_AUTH_TOKEN")
    assert mcp_server.load_env_file(str(tmp_path / "missing")) is False   # optional file
