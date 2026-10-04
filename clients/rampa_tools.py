"""MCP tool logic: a client of the Open API (/public/v1). Pure httpx, no fastmcp —
so it is testable against the app via ASGI. Errors come back as {"error": ...}, never raise."""
import httpx


class ToolError(Exception):
    pass


PROFILES = ["wheelchair", "crutches", "stroller", "blind", "low_vision", "deaf", "assistance_dog"]

TOOL_DEFS = [  # same tools as clients/mcp_server.py; used by the server chat (F46)
    {"name": "check_accessibility",
     "description": "Czy osoba z niepełnosprawnością dostanie się do miejsca w Krakowie? Szuka miejsca po nazwie i "
                    "zwraca odpowiedź (yes/partial/no/unknown), poradę, pewność danych i stan cech dostępności.",
     "parameters": {"type": "object", "required": ["place_name"], "properties": {
         "place_name": {"type": "string", "description": "nazwa miejsca"},
         "profile": {"type": "string", "enum": PROFILES, "description": "domyślnie wheelchair"}}}},
    {"name": "search_accessible_places",
     "description": "Miejsca w Krakowie, które mają WSZYSTKIE podane cechy dostępności, np. step_free_entrance, ramp, "
                    "elevator, accessible_toilet, induction_loop, assistance_dog_allowed, baby_changing_table.",
     "parameters": {"type": "object", "required": ["features"], "properties": {
         "features": {"type": "array", "items": {"type": "string"}}}}},
]


class RampaTools:
    def __init__(self, http: httpx.AsyncClient, api_key: str):
        self.http = http
        self.api_key = api_key

    async def _get(self, path: str, **params) -> dict:
        r = await self.http.get(f"/public/v1{path}", params=params, headers={"X-Api-Key": self.api_key})
        if r.status_code >= 400:
            try:
                message = r.json()["error"]["message"]
            except Exception:  # noqa: BLE001
                message = r.text[:200]
            raise ToolError(f"API {r.status_code}: {message}")
        return r.json()

    async def check_accessibility(self, place_name: str, profile: str = "wheelchair", limit: int = 3) -> dict:
        try:
            places = (await self._get("/places", q=place_name))["items"]
            if not places:
                return {"query": place_name, "matches": [],
                        "message": f"Nie znaleziono miejsca „{place_name}” w bazie Kraków bez barier."}
            matches = []
            for p in places[:limit]:
                check = await self._get(f"/places/{p['id']}/check", profile=profile)
                acc = await self._get(f"/places/{p['id']}/accessibility")
                matches.append({
                    "place": {"id": p["id"], "name": p["name"], "address": p["address"], "category": p["category"]},
                    "answer": check["answer"],
                    "confidence": check["confidence"],
                    "advice": check["advice"],
                    "accessibility": acc["accessibility"],
                })
            return {"query": place_name, "profile": profile, "matches": matches, "total_found": len(places)}
        except (httpx.HTTPError, ToolError) as e:
            return {"error": f"Kraków bez barier API niedostępne: {e}"}

    async def call(self, name: str, arguments: dict) -> dict:
        """Run a tool by name (TOOL_DEFS) with validated arguments; unknown tool or bad arguments → {"error"}."""
        if name == "check_accessibility" and isinstance(arguments.get("place_name"), str) and arguments["place_name"]:
            profile = arguments.get("profile") if arguments.get("profile") in PROFILES else "wheelchair"
            return await self.check_accessibility(arguments["place_name"][:100], profile)
        if name == "search_accessible_places" and isinstance(arguments.get("features"), list) and arguments["features"]:
            return await self.search_accessible_places([str(f) for f in arguments["features"][:10]])
        return {"error": f"nieznane narzędzie lub argumenty: {name}"}

    async def search_accessible_places(self, features: list[str], limit: int = 10) -> dict:
        try:
            data = await self._get("/places", features=",".join(features))
            places = [{"id": p["id"], "name": p["name"], "address": p["address"],
                       "accessibility_summary": p["accessibility_summary"]} for p in data["items"][:limit]]
            return {"features": features, "places": places, "total": data["total"]}
        except (httpx.HTTPError, ToolError) as e:
            return {"error": f"Kraków bez barier API niedostępne: {e}"}
