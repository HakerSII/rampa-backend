"""F27: geocode = local places first, then live geocoder hits; import from live OSM with fallback."""
import pytest

from app.application.use_cases import GeocodeHit
from app.domain.errors import ValidationFailed
from app.domain.model import GeoPoint
from app.domain.osm import OsmPoint
from tests.application.test_observations import user
from tests.conftest import make_use_cases


class FakeGeocoder:
    def __init__(self, hits=None, fail=False):
        self.hits, self.fail, self.calls = hits or [], fail, 0

    async def search(self, q):
        self.calls += 1
        if self.fail:
            raise RuntimeError("offline")
        return self.hits


class FakeOsm:
    last_source = "overpass"

    async def fetch(self):
        return [OsmPoint("Nowa Kawiarnia Live", "yes", "", "cafe", 50.05, 19.93)]


async def test_geocode_live_appends_external_hits_after_local():
    far = GeocodeHit("Tauron Arena Kraków, Lema 7", None, GeoPoint(50.0675, 19.9915))
    uc = make_use_cases(geocoder=FakeGeocoder([far]))
    hits = await uc.geocode_live("muze")
    assert hits[0].place_id == "plc_mnk"            # local first (has data)
    assert hits[-1] == far                          # then external (no place_id)


async def test_geocode_live_drops_external_duplicates_of_local_places():
    dup = GeocodeHit("Muzeum Narodowe w Krakowie", None, GeoPoint(50.0603, 19.9235))
    uc = make_use_cases(geocoder=FakeGeocoder([dup]))
    assert all(h.place_id for h in await uc.geocode_live("muzeum narodowe"))


async def test_geocode_live_falls_back_to_local_when_geocoder_fails():
    uc = make_use_cases(geocoder=FakeGeocoder(fail=True))
    assert [h.place_id for h in await uc.geocode_live("Tomasza")] == ["plc_camelot"]


async def test_geocode_live_without_geocoder_is_local_and_validates():
    uc = make_use_cases()
    assert [h.place_id for h in await uc.geocode_live("Tomasza")] == ["plc_camelot"]
    with pytest.raises(ValidationFailed):
        await uc.geocode_live("m")


async def test_import_from_live_osm_reports_actual_source():
    uc = make_use_cases(osm_live=FakeOsm())
    r = await uc.import_osm(user(uc, "admin"), "overpass")
    assert (r.source, r.places_created, r.observations) == ("overpass", 1, 1)


async def test_import_overpass_unavailable_without_live_source():
    uc = make_use_cases()
    with pytest.raises(ValidationFailed):
        await uc.import_osm(user(uc, "admin"), "overpass")
