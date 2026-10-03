"""MCP server for Claude / Gemini / Grok / other assistants — answers from Kraków bez barier via the Open API.

Local (stdio, default):      uv run --extra mcp python -m clients.mcp_server       # backend must run (python main.py)
Remote (F41, Streamable HTTP): MCP_TRANSPORT=http uv run --extra mcp python -m clients.mcp_server
                              → http://0.0.0.0:$PORT/mcp  (+ GET /health); Docker: Dockerfile.mcp (Render service)

Env (own file for this service: .mcpenv, template .mcpenv.example; real env vars win, e.g. Render dashboard):
     RAMPA_API_URL (default http://localhost:8000), RAMPA_API_KEY (default demo-key),
     MCP_TRANSPORT (stdio | http), PORT (default 8080), MCP_AUTH_TOKEN (optional: require "Authorization: Bearer …"),
     MCP_ENV_FILE (default .mcpenv).
"""
import hmac
import os

import httpx
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from clients.rampa_tools import RampaTools

MCP_ENV_FILE = ".mcpenv"


def load_env_file(path: str) -> bool:
    """Load the MCP service's own env file (.mcpenv) if it exists; never overrides variables already set."""
    from pathlib import Path

    from dotenv import load_dotenv
    if not Path(path).is_file():
        return False
    load_dotenv(path, override=False)
    return True


MCP_PATH = "/mcp"
mcp = FastMCP("Kraków bez barier")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=os.getenv("RAMPA_API_URL", "http://localhost:8000"), timeout=10)


def _key() -> str:
    return os.getenv("RAMPA_API_KEY", "demo-key")


@mcp.tool()
async def check_accessibility(place_name: str, profile: str = "wheelchair") -> dict:
    """Czy osoba na wózku dostanie się do miejsca w Krakowie? Szuka miejsca po nazwie i zwraca
    odpowiedź (yes/partial/no/unknown), poradę, pewność danych i stan cech dostępności
    (wejście bez schodów, podjazd, winda, toaleta, pętla indukcyjna). Dane: społeczność,
    właściciele obiektów, OpenStreetMap — z oceną wiarygodności.
    profile: wheelchair | crutches | stroller | blind | low_vision | deaf | assistance_dog."""
    async with _client() as http:
        return await RampaTools(http, _key()).check_accessibility(place_name, profile)


@mcp.tool()
async def search_accessible_places(features: list[str]) -> dict:
    """Miejsca w Krakowie spełniające WSZYSTKIE podane cechy dostępności, np.
    step_free_entrance, ramp, elevator, accessible_toilet, induction_loop, assistance_dog_allowed,
    baby_changing_table (pełna lista: GET /api/v1/accessibility/features)."""
    async with _client() as http:
        return await RampaTools(http, _key()).search_accessible_places(features)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "transport": "http", "path": MCP_PATH})


class BearerTokenMiddleware:
    """F41: optional shared token for the public MCP endpoint (MCP_AUTH_TOKEN). /health stays open."""

    def __init__(self, app, token: str):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] != "/health":
            auth = dict(scope.get("headers") or []).get(b"authorization", b"").decode()
            if not hmac.compare_digest(auth, f"Bearer {self.token}"):
                await JSONResponse({"error": "unauthorized"}, status_code=401,
                                   headers={"WWW-Authenticate": "Bearer"})(scope, receive, send)
                return
        await self.app(scope, receive, send)


def build_http_app():
    """Streamable HTTP app (stateless: every request stands alone — fine behind Render's proxy / restarts)."""
    token = os.getenv("MCP_AUTH_TOKEN", "")
    middleware = [Middleware(BearerTokenMiddleware, token=token)] if token else None
    return mcp.http_app(path=MCP_PATH, stateless_http=True, middleware=middleware)


if __name__ == "__main__":
    load_env_file(os.getenv("MCP_ENV_FILE", MCP_ENV_FILE))
    if os.getenv("MCP_TRANSPORT", "stdio") == "http":
        import uvicorn
        uvicorn.run(build_http_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
    else:
        mcp.run()
