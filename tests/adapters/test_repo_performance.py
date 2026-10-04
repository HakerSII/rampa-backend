"""F56: observations are indexed by place — the map / observation feeds stay fast with the full city catalogue
(~6,500 places): every request used to scan all observations once per place."""
import time

from app.adapters.outbound.memory import InMemoryRepo
from app.domain.enums import FeatureKey, ObservationSource, ObservationValue
from app.domain.model import GeoPoint, Observation, Place
from tests.conftest import NOW


def obs(id_, place_id, feature, value):
    return Observation(id=id_, place_id=place_id, feature=feature, value=value, source=ObservationSource.OPEN_DATA,
                       author_id="usr_osm", created_at=NOW)


def big_repo(places=6500, observations=2000):
    repo = InMemoryRepo()
    for i in range(places):
        repo.add_place(Place(f"plc_{i}", f"P{i}", "restaurant", GeoPoint(50 + i * 1e-5, 19.9)))
    for i in range(observations):
        repo.add_observation(obs(f"obs_{i}", f"plc_{i * 3 % places}", FeatureKey.STEP_FREE_ENTRANCE, ObservationValue.YES))
    return repo


def test_list_observations_per_place_is_fast():
    repo = big_repo()
    t = time.perf_counter()
    found = sum(len(repo.list_observations(p.id)) for p in repo.list_places())
    assert found == 2000 and time.perf_counter() - t < 0.5


def test_index_follows_adds_and_feature_filter():
    repo = big_repo(places=10, observations=0)
    repo.add_observation(obs("o1", "plc_1", FeatureKey.ELEVATOR, ObservationValue.NO))
    repo.add_observation(obs("o2", "plc_1", FeatureKey.RAMP, ObservationValue.YES))
    assert [o.id for o in repo.list_observations("plc_1")] == ["o1", "o2"]
    assert [o.id for o in repo.list_observations("plc_1", FeatureKey.RAMP)] == ["o2"]
    repo.observations = {"o3": obs("o3", "plc_2", FeatureKey.RAMP, ObservationValue.YES)}
    assert [o.id for o in repo.list_observations("plc_2")] == ["o3"] and repo.list_observations("plc_1") == []


def test_map_observations_with_the_full_catalogue_is_fast():
    from tests.conftest import make_use_cases
    uc = make_use_cases()
    big = big_repo()
    for p in big.list_places():
        uc.repo.add_place(p)
    for o in big.observations.values():
        uc.repo.add_observation(o)
    t = time.perf_counter()
    uc.map_observations(active=True, limit=500)
    uc.map_observations(active=True, current=True, limit=500)
    assert time.perf_counter() - t < 2.0
