import pytest

from app.application.use_cases import PlaceQuery
from app.domain.errors import ValidationFailed
from app.domain.model import GeoPoint

RYNEK = GeoPoint(50.0617, 19.9373)


def ids(result):
    return [p.id for p, _ in result.items]


async def test_nearest_from_rynek_with_distances(uc):
    r = uc.find_places(PlaceQuery(near=RYNEK, radius_m=5000))
    assert ids(r) == ["plc_camelot", "plc_urzad", "plc_mnk", "plc_ice"]
    assert [d for _, d in r.items] == [142, 661, 976, 1728]


async def test_radius_default_2000_and_custom(uc):
    assert ids(uc.find_places(PlaceQuery(near=RYNEK))) == ["plc_camelot", "plc_urzad", "plc_mnk", "plc_ice"]
    assert ids(uc.find_places(PlaceQuery(near=RYNEK, radius_m=800))) == ["plc_camelot", "plc_urzad"]


async def test_bbox_viewport(uc):
    # old town only: lon 19.93..19.95, lat 50.055..50.07
    assert sorted(ids(uc.find_places(PlaceQuery(bbox="19.93,50.055,19.95,50.07")))) == ["plc_camelot", "plc_urzad"]


async def test_sort_name_and_pagination(uc):
    r = uc.find_places(PlaceQuery(sort="name", page=2, page_size=2))
    assert r.total == 4 and ids(r) == ["plc_mnk", "plc_urzad"]  # Cafe, Centrum | Muzeum, Urząd


async def test_recently_verified_first(uc):
    uc.add_observation(uc.repo.find_user_by_username("anna"), "plc_ice", feature="ramp", value="yes")
    assert ids(uc.find_places(PlaceQuery(sort="recently_verified")))[0] == "plc_ice"


@pytest.mark.parametrize("query", [
    PlaceQuery(sort="nearest"), PlaceQuery(page=0), PlaceQuery(page_size=101), PlaceQuery(bbox="1,2,3"),
    PlaceQuery(sort="rating"),
])
async def test_invalid_queries(uc, query):
    with pytest.raises(ValidationFailed):
        uc.find_places(query)


async def test_categories_and_geocode(uc):
    assert {c.key: c.count for c in uc.list_categories()} == {"museum": 1, "cafe": 1, "culture": 1, "office": 1}
    hits = uc.geocode("muze")
    assert [h.place_id for h in hits] == ["plc_mnk"] and hits[0].label.startswith("Muzeum Narodowe")
    assert [h.place_id for h in uc.geocode("Tomasza")] == ["plc_camelot"]  # by address
    with pytest.raises(ValidationFailed):
        uc.geocode("m")
