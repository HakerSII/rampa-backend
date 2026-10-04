"""F46: the MCP server's tools (clients/rampa_tools.py), run in-process against this app's Open API."""
import httpx

from clients.rampa_tools import TOOL_DEFS, RampaTools


class InProcessChatTools:
    definitions = TOOL_DEFS

    def __init__(self, app, api_key: str):
        self.app = app
        self.api_key = api_key

    async def call(self, name: str, arguments: dict) -> dict:
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://rampa.internal", timeout=30) as http:
            return await RampaTools(http, self.api_key).call(name, arguments)
