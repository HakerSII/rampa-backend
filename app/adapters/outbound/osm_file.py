"""Offline OSM source: JSON snapshot produced by get_from_api.py (Overpass)."""
import asyncio
import json
from pathlib import Path

from app.domain.osm import OsmPoint


class FileOsmSource:
    def __init__(self, path: str):
        self.path = Path(path)

    async def fetch(self) -> list[OsmPoint]:
        raw = await asyncio.to_thread(self.path.read_text, encoding="utf-8")
        return [
            OsmPoint(str(p.get("name") or ""), str(p.get("wheelchair") or ""), str(p.get("toilet") or ""),
                     str(p.get("category") or ""), float(p["lat"]), float(p["lon"]))
            for p in json.loads(raw)
            if p.get("lat") is not None and p.get("lon") is not None
        ]
