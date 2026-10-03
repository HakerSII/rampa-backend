"""OpenStreetMap point → open_data observations (pure mapping).
Point format = get_from_api.py snapshot: {name, wheelchair, toilet, category, lat, lon}."""
from dataclasses import dataclass

from app.domain.enums import FeatureKey, ObservationValue

UNNAMED = "Brak nazwy"
MATCH_RADIUS_M = 50.0
YES_NO = {"yes": ObservationValue.YES, "limited": ObservationValue.PARTIAL, "no": ObservationValue.NO}


@dataclass(frozen=True, slots=True)
class OsmPoint:
    name: str
    wheelchair: str
    toilet: str
    category: str
    lat: float
    lon: float

    @property
    def external_id(self) -> str:
        return f"osm:{self.lat:.6f},{self.lon:.6f}"


def map_features(p: OsmPoint) -> list[tuple[FeatureKey, ObservationValue]]:
    result = []
    if p.wheelchair in YES_NO:
        result.append((FeatureKey.STEP_FREE_ENTRANCE, YES_NO[p.wheelchair]))
    if p.toilet in YES_NO:
        result.append((FeatureKey.ACCESSIBLE_TOILET, YES_NO[p.toilet]))
    return result


def map_category(osm_category: str) -> str:
    return "other" if osm_category in ("inne", "", None) else osm_category
