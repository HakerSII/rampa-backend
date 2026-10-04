"""F49: the Accessly place catalogue (main branch's places.json, OSM) imported into Rampa — every named place,
with address/contact and OSM accessibility facts as open-data observations."""
import asyncio

import pytest

from app.domain.catalog import from_accessly
from app.domain.enums import FeatureKey, ObservationSource
from app.domain.errors import Forbidden
from tests.application.test_observations import user
from tests.conftest import make_use_cases

ACCESSLY = [
    {"ref": "node/1", "name": "Ogród Doświadczeń im. Stanisława Lema", "category": "kultura", "kind": "theme_park",
     "lat": 50.0684, "lng": 19.9968, "attributes": {"step_free": "yes"}},
    {"ref": "node/2", "name": "Kawiarnia Bez Danych", "category": "gastronomia", "kind": "cafe", "lat": 50.06, "lng": 19.94,
     "address": "Rynek 1", "phone": "+48 12 000 00 00", "website": "https://kawa.example"},
    {"ref": "node/3", "name": "Hotel Schody", "category": "noclegi", "kind": "hotel", "lat": 50.05, "lng": 19.93,
     "attributes": {"step_free": "no", "accessible_toilet": "partial", "changing_table": "yes", "open_24h": "yes"}},
    {"ref": "node/4", "name": "", "category": "inne", "kind": "x", "lat": 50.0, "lng": 19.9},
]


def entries():
    return from_accessly(ACCESSLY)


def test_conversion_maps_categories_and_features():
    e = {x["ref"]: x for x in entries()}
    assert e["osm:node/1"]["category"] == "culture"       # unknown kind → the category's Rampa key
    assert e["osm:node/2"]["category"] == "cafe"          # kind known to the city's groups
    assert e["osm:node/3"]["category"] == "hotel"
    assert e["osm:node/1"]["features"] == {"step_free_entrance": "yes"}
    assert e["osm:node/3"]["features"] == {"step_free_entrance": "no", "accessible_toilet": "partial",
                                           "baby_changing_table": "yes"}  # open_24h: no Rampa feature
    assert e["osm:node/2"] | {} == {"ref": "osm:node/2", "name": "Kawiarnia Bez Danych", "category": "cafe",
                                    "lat": 50.06, "lon": 19.94, "address": "Rynek 1", "phone": "+48 12 000 00 00",
                                    "website": "https://kawa.example", "features": {}}
    assert "osm:node/4" not in e  # unnamed


def run(uc, data):
    return asyncio.run(uc.import_catalog(user(uc, "admin"), data))


def test_import_creates_every_named_place_with_facts_and_contact():
    uc = make_use_cases()
    before = len(uc.repo.list_places())
    r = run(uc, entries())
    assert (r.places_created, r.places_matched, r.observations) == (3, 0, 4)
    assert len(uc.repo.list_places()) == before + 3
    kawa = next(p for p in uc.repo.list_places() if p.name == "Kawiarnia Bez Danych")
    assert kawa.address == "Rynek 1" and kawa.contact == {"phone": "+48 12 000 00 00", "website": "https://kawa.example"}
    assert kawa.external_id == "osm:node/2" and kawa.category == "cafe"
    lem = next(p for p in uc.repo.list_places() if p.name.startswith("Ogród"))
    obs = uc.repo.list_observations(lem.id, FeatureKey.STEP_FREE_ENTRANCE)
    assert len(obs) == 1 and obs[0].source == ObservationSource.OPEN_DATA


def test_import_is_idempotent():
    uc = make_use_cases()
    run(uc, entries())
    count = len(uc.repo.list_places())
    r = run(uc, entries())
    assert (r.places_created, r.places_matched, r.observations) == (0, 3, 0)
    assert len(uc.repo.list_places()) == count


def test_existing_place_with_the_same_name_nearby_is_matched():
    uc = make_use_cases()
    mnk = uc.repo.get_place("plc_mnk")
    r = run(uc, [{"ref": "osm:node/9", "name": mnk.name.upper(), "category": "museum", "lat": mnk.location.lat,
                  "lon": mnk.location.lon + 0.0001, "features": {"elevator": "yes"}}])
    assert (r.places_created, r.places_matched) == (0, 1)


def test_only_admin():
    uc = make_use_cases()
    with pytest.raises(Forbidden):
        run_as = asyncio.run(uc.import_catalog(user(uc, "anna"), entries()))
        assert run_as is None


def test_kind_and_opening_hours_are_kept():
    data = from_accessly([{"ref": "node/5", "name": "Ogród Doświadczeń", "category": "kultura", "kind": "theme_park",
                           "lat": 50.07, "lng": 19.99, "openingHours": "Sa,Su 10:00-19:00"}])
    assert data[0]["kind"] == "theme_park" and data[0]["opening_hours"] == "Sa,Su 10:00-19:00"
    uc = make_use_cases()
    run(uc, data)
    p = next(p for p in uc.repo.list_places() if p.name == "Ogród Doświadczeń")
    assert p.kind == "theme_park" and p.opening_hours == [{"text": "Sa,Su 10:00-19:00"}]
