import json

import pytest

from app.adapters.outbound.osm_file import FileOsmSource
from app.domain.enums import CheckAnswer, FeatureKey as F, NeedsProfile, ObservationSource
from app.domain.errors import Forbidden, Unauthorized
from tests.application.test_observations import user
from tests.conftest import make_use_cases

POINTS = [
    {"name": "Kawiarnia Testowa", "wheelchair": "yes", "toilet": "yes", "category": "cafe", "lat": 50.07, "lon": 19.99},
    {"name": "Brak nazwy", "wheelchair": "yes", "toilet": "brak danych", "category": "inne", "lat": 50.071, "lon": 19.99},
    {"name": "Sklep Limited", "wheelchair": "limited", "toilet": "brak danych", "category": "shop", "lat": 50.072,
     "lon": 19.99},
    # same name as seed place, ~13 m away → matched, not duplicated
    {"name": "Muzeum Narodowe w Krakowie", "wheelchair": "no", "toilet": "brak danych", "category": "museum",
     "lat": 50.0604, "lon": 19.9239},
    {"name": "Inne Miejsce", "wheelchair": "yes", "toilet": "brak danych", "category": "inne", "lat": 50.073,
     "lon": 19.99},
]


@pytest.fixture
def uc(tmp_path):
    path = tmp_path / "osm.json"
    path.write_text(json.dumps(POINTS), encoding="utf-8")
    return make_use_cases(osm=FileOsmSource(str(path)))


async def test_first_import_creates_places_and_open_data_observations(uc):
    r = await uc.import_osm(user(uc, "admin"))
    # F23: "Sklep Limited" (wheelchair=limited) now imported as partial instead of skipped
    assert (r.points, r.places_created, r.places_matched, r.observations, r.skipped_unnamed, r.skipped_no_data) == (
        5, 3, 1, 5, 1, 0)
    (cafe,) = uc.search_places(q="Kawiarnia Testowa")
    assert cafe.id.startswith("plc_osm_") and cafe.external_id == "osm:50.070000,19.990000"
    states = uc.get_accessibility(cafe.id)
    assert (states[F.STEP_FREE_ENTRANCE].state, states[F.STEP_FREE_ENTRANCE].confidence) == ("yes", 0.6)
    assert states[F.ACCESSIBLE_TOILET].state == "yes"
    obs = uc.list_observations(cafe.id)
    assert {o.source for o in obs} == {ObservationSource.OPEN_DATA} and obs[0].author_id == "usr_osm"
    assert uc.search_places(q="Inne Miejsce")[0].category == "other"


async def test_matched_place_gets_open_data_observation(uc):
    await uc.import_osm(user(uc, "admin"))
    s = uc.get_accessibility("plc_mnk")[F.STEP_FREE_ENTRANCE]
    assert (s.state, s.confidence) == ("no", 0.6)  # fresh open data (0.6) beats 60-day-old community (0.5)
    assert len(uc.search_places(q="Muzeum Narodowe")) == 1


async def test_import_is_idempotent(uc):
    await uc.import_osm(user(uc, "admin"))
    r = await uc.import_osm(user(uc, "admin"))
    assert (r.places_created, r.places_matched, r.observations) == (0, 4, 0)


@pytest.mark.parametrize("who, error", [("anna", Forbidden), (None, Unauthorized)])
async def test_only_admin_imports(uc, who, error):
    with pytest.raises(error):
        await uc.import_osm(user(uc, who) if who else None)


async def test_real_snapshot_makes_tauron_stops_searchable():
    uc = make_use_cases()  # default: data/osm_krakow_tauron.json
    await uc.import_osm(user(uc, "admin"))
    stops = uc.search_places(q="tauron")
    assert len(stops) == 3
    assert {uc.check_place(p.id, NeedsProfile.WHEELCHAIR).answer for p in stops} == {CheckAnswer.YES}
