"""F29: several workers (processes) on one database. Two SqlRepo instances on one file = two workers.
Every request first syncs (reload when another worker committed); commit = optimistic lock on data_version."""
from fastapi.testclient import TestClient
import pytest

from app.adapters.inbound.http.main import create_app
from app.adapters.outbound.memory import FixedClock, SeqIdGenerator
from app.adapters.outbound.sql import SqlRepo, StaleData
from app.application.use_cases import UseCases
from app.config import Settings
from tests.conftest import NOW, FakeStorage
from tests.application.test_observations import user


def worker(url) -> UseCases:
    repo = SqlRepo(url)
    uc = UseCases(repo, FixedClock(NOW), SeqIdGenerator(), FakeStorage(), None)
    if repo.is_empty():
        uc.load_seed()
        repo.commit()
    uc.sync(force=True)
    return uc


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{tmp_path / 'shared.db'}"


def test_worker_sees_other_workers_writes_after_sync(url):
    a, b = worker(url), worker(url)
    obs = a.add_observation(user(a, "anna"), "plc_ice", feature="ramp", value="no")
    a.repo.commit()
    assert b.repo.get_observation(obs.id) is None          # stale cache …
    assert b.sync() is True                                 # … reloaded on the next request
    assert b.repo.get_observation(obs.id).value == "no"
    assert b.sync() is False                                # nothing new → no reload
    mine = b.add_observation(user(b, "jan"), "plc_ice", feature="ramp", value="yes")
    assert mine.id != obs.id                                # id sequences continue after reload
    b.repo.commit()
    a.sync()
    assert {a.repo.get_observation(i).id for i in (obs.id, mine.id)} == {obs.id, mine.id}


def test_concurrent_commit_is_rejected_and_cache_reloaded(url):
    a, b = worker(url), worker(url)
    first = a.add_observation(user(a, "anna"), "plc_ice", feature="ramp", value="no")
    lost = b.add_observation(user(b, "jan"), "plc_ice", feature="elevator", value="no")   # both on the same version
    a.repo.commit()
    with pytest.raises(StaleData):
        b.repo.commit()
    assert b.repo.get_observation(first.id) is not None    # b now holds a's data …
    assert lost.id not in {o.id for o in b.repo.list_observations("plc_ice")}  # … and its own write is dropped
    fresh = worker(url)
    assert fresh.repo.get_observation(first.id) is not None


def test_commit_without_changes_never_conflicts(url):
    a, b = worker(url), worker(url)
    a.add_observation(user(a, "anna"), "plc_ice", feature="ramp", value="no")
    a.repo.commit()
    b.repo.commit()  # read-only request on a stale worker: nothing to write → no error


def test_memory_repo_sync_is_noop(uc):
    assert uc.sync() is False


def test_two_app_workers_over_http(url, tmp_path):
    settings = Settings(repo_mode="sql", database_url=url, media_dir=str(tmp_path / "m"))
    w1, w2 = TestClient(create_app(settings)), TestClient(create_app(settings))
    o = w1.post("/api/v1/places/plc_ice/observations", headers={"Authorization": "Bearer demo-anna"},
                json={"feature": "ramp", "value": "no"}).json()
    items = w2.get("/api/v1/places/plc_ice/observations").json()["items"]
    assert o["id"] in [i["id"] for i in items]             # written by worker 1, read by worker 2
    o2 = w2.post("/api/v1/places/plc_ice/observations", headers={"Authorization": "Bearer demo-jan"},
                 json={"feature": "ramp", "value": "yes"})
    assert o2.status_code == 201 and o2.json()["id"] != o["id"]


def test_stale_commit_over_http_returns_409(url, tmp_path, monkeypatch):
    settings = Settings(repo_mode="sql", database_url=url, media_dir=str(tmp_path / "m"))
    app1, app2 = create_app(settings), create_app(settings)
    w1, w2 = TestClient(app1), TestClient(app2)
    uc2 = app2.state.use_cases
    real_add = uc2.add_observation

    def add_while_other_worker_commits(*args, **kwargs):  # worker 1 commits between w2's sync and commit
        w1.post("/api/v1/places/plc_ice/observations", headers={"Authorization": "Bearer demo-anna"},
                json={"feature": "elevator", "value": "no"})
        return real_add(*args, **kwargs)
    monkeypatch.setattr(uc2, "add_observation", add_while_other_worker_commits)
    r = w2.post("/api/v1/places/plc_ice/observations", headers={"Authorization": "Bearer demo-jan"},
                json={"feature": "ramp", "value": "yes"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"
    monkeypatch.undo()
    retry = w2.post("/api/v1/places/plc_ice/observations", headers={"Authorization": "Bearer demo-jan"},
                    json={"feature": "ramp", "value": "yes"})
    assert retry.status_code == 201
