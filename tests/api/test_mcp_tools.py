"""MCP tool logic (clients/rampa_tools.py) against the real app via ASGI — no network, no fastmcp."""
import httpx
import pytest

from app.adapters.inbound.http.main import create_app
from app.config import Settings
from clients.rampa_tools import RampaTools
from tests.conftest import NOW


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(demo_now=NOW, media_dir=str(tmp_path), public_api_keys="k"))


def tools(app, key="k") -> RampaTools:
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return RampaTools(http, api_key=key)


async def test_check_known_place(app):
    r = await tools(app).check_accessibility("Muzeum Narodowe")
    (m,) = r["matches"]
    assert (m["place"]["id"], m["answer"]) == ("plc_mnk", "yes")
    assert m["accessibility"]["elevator"]["value"] is True and m["advice"]


async def test_check_unknown_place_says_so(app):
    r = await tools(app).check_accessibility("Wawel Dragon Cave")
    assert r["matches"] == [] and "Nie znaleziono" in r["message"]


async def test_tauron_after_osm_import(app):
    t = tools(app)
    assert (await t.check_accessibility("Tauron"))["matches"] == []
    await t.http.post("/api/v1/admin/imports", json={"source": "osm_file"},
                      headers={"Authorization": "Bearer demo-admin"})
    r = await t.check_accessibility("Tauron")
    assert len(r["matches"]) == 3 and {m["answer"] for m in r["matches"]} == {"yes"}


async def test_search_by_features(app):
    r = await tools(app).search_accessible_places(["step_free_entrance", "elevator"])
    assert [p["id"] for p in r["places"]] == ["plc_mnk"]


async def test_wrong_key_and_backend_down_return_error_not_exception(app):
    assert "error" in await tools(app, key="bad").check_accessibility("Muzeum")
    down = RampaTools(httpx.AsyncClient(base_url="http://127.0.0.1:9", timeout=0.5), api_key="k")
    assert "error" in await down.check_accessibility("Muzeum")
