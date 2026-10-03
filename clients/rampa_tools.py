"""MCP tool logic: a client of the Open API (/public/v1). Pure httpx, no fastmcp —
so it is testable against the app via ASGI. Errors come back as {"error": ...}, never raise."""
import httpx


class ToolError(Exception):
    pass


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

    async def search_accessible_places(self, features: list[str], limit: int = 10) -> dict:
        try:
            data = await self._get("/places", features=",".join(features))
            places = [{"id": p["id"], "name": p["name"], "address": p["address"],
                       "accessibility_summary": p["accessibility_summary"]} for p in data["items"][:limit]]
            return {"features": features, "places": places, "total": data["total"]}
        except (httpx.HTTPError, ToolError) as e:
            return {"error": f"Kraków bez barier API niedostępne: {e}"}
