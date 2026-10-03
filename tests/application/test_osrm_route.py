"""F28: real walking geometry from a routing engine; barriers measured along the polyline; fallback straight line."""
import httpx
import pytest

from app.adapters.outbound.osrm import OsrmRouter
from app.domain.enums import NeedsProfile as P
from app.domain.model import GeoPoint
from app.domain.route import RoutePath
from tests.application.test_observations import user
from tests.conftest import make_use_cases

MNK, URZAD = GeoPoint(50.0603, 19.9238), GeoPoint(50.0650, 19.9450)
VIA_CAMELOT = RoutePath([MNK, GeoPoint(50.0628, 19.9383), URZAD], 1850, 1500)   # passes Café Camelot
NORTH_DETOUR = RoutePath([MNK, GeoPoint(50.0700, 19.9238), GeoPoint(50.0700, 19.9450), URZAD], 2600, 2100)


class FakeRouter:
    def __init__(self, path=None, fail=False):
        self.path, self.fail = path, fail

    async def walk(self, a, b):
        if self.fail:
            raise httpx.ConnectError("offline")
        return self.path


async def test_route_uses_engine_geometry_distance_and_duration():
    uc = make_use_cases(router=FakeRouter(VIA_CAMELOT))
    r = await uc.accessible_route_live("plc_mnk", "plc_urzad", P.WHEELCHAIR)
    assert r.engine == "osrm" and (r.distance_m, r.duration_min) == (1850, 25)
    assert r.geometry == [[19.9238, 50.0603], [19.9383, 50.0628], [19.945, 50.065]]
    assert "heuristic" not in r.note


async def test_barriers_follow_the_real_path_not_the_straight_line():
    uc = make_use_cases(router=FakeRouter(NORTH_DETOUR))
    uc.add_observation(user(uc, "anna"), "plc_camelot", feature="lowered_curb", value="no")
    straight = uc.accessible_route("plc_mnk", "plc_urzad", P.WHEELCHAIR)
    assert [b.place_id for b in straight.barriers] == ["plc_camelot"]        # ~75 m from the straight line
    detour = await uc.accessible_route_live("plc_mnk", "plc_urzad", P.WHEELCHAIR)
    assert detour.barriers == [] and detour.engine == "osrm"                 # the real path avoids it


async def test_router_failure_or_empty_falls_back_to_straight_line():
    for router in (FakeRouter(fail=True), FakeRouter(None)):
        uc = make_use_cases(router=router)
        r = await uc.accessible_route_live("plc_mnk", "plc_urzad", P.WHEELCHAIR)
        assert (r.engine, r.distance_m) == ("straight_line", 1601) and "heuristic" in r.note


async def test_no_router_configured_is_straight_line(uc):
    r = await uc.accessible_route_live("plc_mnk", "plc_urzad", P.WHEELCHAIR)
    assert r.engine == "straight_line"


# ---------------------------------------------------------------- adapter
OSRM_OK = {"code": "Ok", "routes": [{"distance": 1834.2, "duration": 1320.5, "geometry": {
    "type": "LineString", "coordinates": [[19.9238, 50.0603], [19.94, 50.063], [19.945, 50.065]]}}]}


async def test_osrm_adapter_parses_geojson_route():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=OSRM_OK)
    router = OsrmRouter("https://osrm.example/routed-foot", "RampaTest/1.0", transport=httpx.MockTransport(handler))
    path = await router.walk(MNK, URZAD)
    assert (path.distance_m, path.duration_s) == (1834, 1320)
    assert path.points == [MNK, GeoPoint(50.063, 19.94), URZAD]
    assert seen[0].url.path == "/routed-foot/route/v1/foot/19.9238,50.0603;19.945,50.065"
    assert seen[0].url.params["geometries"] == "geojson" and seen[0].url.params["overview"] == "full"


async def test_osrm_no_route_returns_none():
    router = OsrmRouter("https://osrm.example", "x",
                        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"code": "NoRoute"})))
    assert await router.walk(MNK, URZAD) is None


async def test_osrm_http_error_raises():
    router = OsrmRouter("https://osrm.example", "x", transport=httpx.MockTransport(lambda r: httpx.Response(502)))
    with pytest.raises(httpx.HTTPError):
        await router.walk(MNK, URZAD)
