"""F37: city-specific data (name, viewbox, centre, named areas, category groups + words) comes from a JSON file
instead of code. Kraków = default file; another city = another file (CITY_CONFIG)."""
import json

import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.adapters.outbound.osm_live import NominatimGeocoder
from app.config import Settings
from app.domain.city import DEFAULT_CITY_FILE, City, load_city
from app.domain.recommend import interpret_rules

GDANSK = {
    "name": "Gdańsk",
    "viewbox": [18.45, 54.45, 18.75, 54.28],
    "center": {"lat": 54.352, "lon": 18.6466},
    "osm_radius_m": 1200,
    "areas": {"starowka": {"lat": 54.3489, "lon": 18.6532, "radius_m": 900,
                           "words": ["starówk", "starówc", "starowk", "starowc", "główne miasto"]}},
    "category_groups": {"gastronomy": {"categories": ["cafe", "restaurant"], "words": ["kawiar", "restaurac"]},
                        "culture": {"categories": ["museum"], "words": ["muze"]}},
}


def write(tmp_path, data) -> str:
    p = tmp_path / "city.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(p)


def test_default_city_is_krakow():
    city = load_city(DEFAULT_CITY_FILE)
    assert city.name == "Kraków" and "centrum" in city.areas and "gastronomy" in city.category_groups
    assert city.viewbox_param == "19.79,50.13,20.22,49.97"


def test_other_city_drives_the_interpreter(tmp_path):
    city = load_city(write(tmp_path, GDANSK))
    i = interpret_rules("kawiarnia na starówce, wjadę wózkiem", city)
    assert (i.categories, i.area) == (["gastronomy"], "starowka")
    assert interpret_rules("kawiarnia w centrum", city).area is None      # Kraków's "centrum" is not defined


@pytest.mark.parametrize("broken", [{}, {**GDANSK, "viewbox": [1, 2]}, {**GDANSK, "center": {"lat": "x"}},
                                    {**GDANSK, "areas": {"a": {"lat": 1, "lon": 2}}}])
def test_invalid_city_file_fails_fast(tmp_path, broken):
    with pytest.raises(ValueError):
        load_city(write(tmp_path, broken))


async def test_geocoder_uses_city_viewbox(tmp_path):
    import httpx
    seen = []
    city = load_city(write(tmp_path, GDANSK))
    g = NominatimGeocoder("https://n.example/search", "ua", viewbox=city.viewbox_param,
                          transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200, json=[])))
    await g.search("x")
    assert seen[0].url.params["viewbox"] == "18.45,54.45,18.75,54.28"


def test_city_endpoint_and_recommend_use_configured_city(tmp_path):
    settings = Settings(repo_mode="memory", media_dir=str(tmp_path / "m"), city_config=write(tmp_path, GDANSK))
    c = TestClient(create_app(settings))
    body = c.get("/api/v1/city").json()
    assert body["name"] == "Gdańsk" and body["areas"][0]["key"] == "starowka"
    assert [g["key"] for g in body["category_groups"]] == ["gastronomy", "culture"]
    r = c.post("/api/v1/ai/recommend", json={"query": "muzeum na starówce"}).json()
    assert r["intent"]["area"] == "starowka" and r["intent"]["categories"] == ["culture"]


def test_krakow_endpoint_default(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    assert c.get("/api/v1/city").json()["center"] == {"lat": 50.0617, "lon": 19.9373}
    assert isinstance(load_city(DEFAULT_CITY_FILE), City)
