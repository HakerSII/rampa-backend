"""MCP server for Claude / other assistants — answers from Kraków bez barier via the Open API.

    uv run --extra mcp python -m clients.mcp_server       # stdio; backend must run (python main.py)

Env: RAMPA_API_URL (default http://localhost:8000), RAMPA_API_KEY (default demo-key).
"""
import os

import httpx
from fastmcp import FastMCP

from clients.rampa_tools import RampaTools

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
    właściciele obiektów, OpenStreetMap — z oceną wiarygodności."""
    async with _client() as http:
        return await RampaTools(http, _key()).check_accessibility(place_name, profile)


@mcp.tool()
async def search_accessible_places(features: list[str]) -> dict:
    """Miejsca w Krakowie spełniające WSZYSTKIE podane cechy dostępności. Dozwolone cechy:
    step_free_entrance, ramp, elevator, accessible_toilet, induction_loop."""
    async with _client() as http:
        return await RampaTools(http, _key()).search_accessible_places(features)


if __name__ == "__main__":
    mcp.run()
