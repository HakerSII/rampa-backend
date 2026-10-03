"""F37 city configuration: everything city-specific (name, map box, centre, named areas, category groups and
their keywords) comes from a JSON file, validated at start. Kraków = data/cities/krakow.json."""
import json
from dataclasses import dataclass
from pathlib import Path

from app.domain.model import GeoPoint

DEFAULT_CITY_FILE = str(Path(__file__).resolve().parents[2] / "data" / "cities" / "krakow.json")


@dataclass(frozen=True, slots=True)
class Area:
    center: GeoPoint
    radius_m: int
    words: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CategoryGroup:
    categories: tuple[str, ...]
    words: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class City:
    name: str
    viewbox: tuple[float, float, float, float]  # lon1, lat1, lon2, lat2 (Nominatim order)
    center: GeoPoint
    osm_radius_m: int
    areas: dict[str, Area]
    category_groups: dict[str, CategoryGroup]

    @property
    def viewbox_param(self) -> str:
        return ",".join(f"{v:g}" for v in self.viewbox)


def _point(raw, where: str) -> GeoPoint:
    try:
        return GeoPoint(float(raw["lat"]), float(raw["lon"]))
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"city config: {where} needs numeric lat and lon") from e


def _words(raw) -> tuple[str, ...]:
    return tuple(str(w).lower() for w in raw or ())


def parse_city(data: dict) -> City:
    """Raise ValueError with the offending field."""
    try:
        name = str(data["name"]).strip()
        viewbox = tuple(float(v) for v in data["viewbox"])
        if not name or len(viewbox) != 4:
            raise ValueError
        center = _point(data["center"], "center")
        areas = {}
        for key, a in (data.get("areas") or {}).items():
            if "radius_m" not in a:
                raise ValueError(f"city config: area {key} needs radius_m")
            areas[key] = Area(_point(a, f"area {key}"), int(a["radius_m"]), _words(a.get("words")))
        groups = {key: CategoryGroup(tuple(g.get("categories") or ()), _words(g.get("words")))
                  for key, g in (data.get("category_groups") or {}).items()}
        return City(name, viewbox, center, int(data.get("osm_radius_m", 1500)), areas, groups)
    except ValueError as e:
        raise ValueError(str(e) or "city config: name and viewbox [lon1, lat1, lon2, lat2] required") from e
    except (KeyError, TypeError) as e:
        raise ValueError(f"city config: missing or invalid field {e}") from e


def load_city(path: str | None = None) -> City:
    p = Path(path or DEFAULT_CITY_FILE)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"city config {p}: {e}") from e
    return parse_city(data)
