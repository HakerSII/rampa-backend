"""SqlRepo: write-behind cache. Runs on SQLite always and on Postgres when TEST_POSTGRES_URL is set
(e.g. postgresql+psycopg://rampa:rampa@localhost:5432/rampa_test — tables are dropped!).
Reload = new SqlRepo on the same database."""
import os

import pytest

from app.adapters.outbound.memory import FixedClock, SeqIdGenerator
from app.adapters.outbound.sql import SqlRepo
from app.application.use_cases import UseCases
from app.domain.enums import FeatureKey as F, ObservationSource, QueueStatus, Role, ValidationStatus
from tests.conftest import NOW, FakeStorage
from tests.application.test_observations import report, user


@pytest.fixture(params=["sqlite", "postgres"])
def url(request, tmp_path):
    if request.param == "sqlite":
        return f"sqlite:///{tmp_path / 'test.db'}"
    pg = os.getenv("TEST_POSTGRES_URL")
    if not pg:
        pytest.skip("set TEST_POSTGRES_URL to run SqlRepo tests on Postgres")
    from sqlalchemy import create_engine

    from app.adapters.outbound.sql import md
    engine = create_engine(pg)
    md.drop_all(engine)  # clean database per test
    engine.dispose()
    return pg


def make(url) -> UseCases:
    repo = SqlRepo(url)
    ids = SeqIdGenerator()
    uc = UseCases(repo, FixedClock(NOW), ids, FakeStorage(), None)
    if repo.is_empty():
        uc.load_seed()
        repo.commit()
    else:
        for i in repo.all_ids():
            ids.observe(i)
    return uc


def test_fresh_database_is_empty(url):
    assert SqlRepo(url).is_empty()


def test_seed_roundtrip_gives_equal_objects(url):
    a = make(url)
    b = make(url)  # reload from file
    assert not b.repo.is_empty()
    assert b.repo.list_places() == a.repo.list_places()
    assert b.repo.list_observations("plc_mnk") == a.repo.list_observations("plc_mnk")
    assert b.repo.states_for("plc_mnk") == a.repo.states_for("plc_mnk")
    assert b.repo.get_user("usr_ewa") == a.repo.get_user("usr_ewa")
    assert b.repo.get_place("plc_mnk").owner_id == "usr_ewa"


def test_mutations_persist_votes_validation_queue_owner(url):
    uc = make(url)
    obs_id = report(uc).observation_ids[0]
    uc.vote(user(uc, "jan"), obs_id, 1)
    marek = uc.add_observation(user(uc, "marek"), "plc_mnk", feature="elevator", value="yes")
    (item,) = uc.list_queue(user(uc, "admin"))
    uc.decide(user(uc, "admin"), item.id, "confirm", winning_observation_id=marek.id)
    uc.assign_owner(user(uc, "admin"), "plc_ice", "usr_anna")
    uc.repo.commit()

    r = make(url)
    o = r.repo.get_observation(obs_id)
    assert o.votes == {"usr_jan": 1} and o.validation == ValidationStatus.REJECTED
    assert r.repo.get_queue_item(item.id).status == QueueStatus.RESOLVED
    s = r.repo.states_for("plc_mnk")[F.ELEVATOR]
    assert (s.state, s.confidence) == ("yes", 1.0)
    assert r.repo.get_place("plc_ice").owner_id == "usr_anna" and r.repo.get_user("usr_anna").role == Role.OWNER
    assert len(r.list_owner_reports(r.repo.get_user("usr_ewa"))) == 1


def test_types_survive_roundtrip(url):
    uc = make(url)
    o = make(url).repo.list_observations("plc_mnk")[0]
    assert o.created_at.tzinfo is not None and o.created_at == uc.repo.list_observations("plc_mnk")[0].created_at
    assert isinstance(o.source, ObservationSource) and isinstance(o.feature, F)
    assert isinstance(o.votes, dict) and isinstance(o.evidence_ids, list)


def test_clear_deletes_rows(url):
    uc = make(url)
    uc.repo.clear()
    uc.repo.commit()
    assert SqlRepo(url).is_empty()


def test_ids_continue_after_reload_no_collision(url):
    uc = make(url)
    first = report(uc).observation_ids[0]
    uc.repo.commit()
    r = make(url)
    second = report(r).observation_ids[0]
    assert second != first and r.repo.get_observation(first) is not None


def test_reset_demo_wipes_back_to_seed(url):
    uc = make(url)
    report(uc)
    uc.reset_demo(user(uc, "admin"))
    uc.repo.commit()
    r = make(url)
    assert r.repo.list_reports() == [] and len(r.repo.list_places()) == 4


def test_adds_missing_columns_to_existing_tables(url):
    """Schema evolution: a DB created before a column existed gets it on start (nullable)."""
    from sqlalchemy import create_engine, inspect, text
    make(url)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE queue_items DROP COLUMN resolved_at"))
    assert "resolved_at" not in {c["name"] for c in inspect(engine).get_columns("queue_items")}
    engine.dispose()
    r = make(url)  # restart → migration adds column, data still loads
    assert "resolved_at" in {c["name"] for c in inspect(r.repo.engine).get_columns("queue_items")}
    assert len(r.repo.list_places()) == 4


def test_favorites_persist(url):
    uc = make(url)
    uc.add_favorite(uc.repo.get_user("usr_anna"), "plc_ice")
    uc.repo.commit()
    assert make(url).repo.get_user("usr_anna").favorite_place_ids == ["plc_ice"]


def test_draft_with_empty_fields_roundtrip(url):
    uc = make(url)
    d = uc.create_report(uc.repo.get_user("usr_anna"), place_id="plc_mnk", draft=True)
    uc.repo.commit()
    r = make(url).repo.get_report(d.id)
    assert (r.status, r.element, r.current_state, r.description) == ("draft", None, None, None)


def test_admin_extras_persist(url):
    uc = make(url)
    adm = uc.repo.get_user("usr_admin")
    obs = uc.add_observation(uc.repo.get_user("usr_anna"), "plc_mnk", feature="ramp", value="no")
    uc.flag_observation(adm, obs.id, "spam")
    req = uc.request_ownership(uc.repo.get_user("usr_jan"), "plc_ice", "manager")
    uc.merge_places(adm, "plc_camelot", "plc_mnk")
    uc.repo.commit()
    r = make(url)
    assert r.repo.get_observation(obs.id).flag_reason == "spam"
    assert r.repo.get_ownership_request(req.id).status == "pending"
    assert r.repo.get_place("plc_camelot") is None and len(r.repo.list_places()) == 3


def test_owner_extras_persist(url):
    uc = make(url)
    ewa = uc.repo.get_user("usr_ewa")
    uc.set_opening_hours(ewa, "plc_mnk", [{"days": "Mon", "closed": True}])
    uc.update_owner_place(ewa, "plc_mnk", contact={"website": "https://mnk.pl"})
    r = uc.create_report(uc.repo.get_user("usr_anna"), place_id="plc_mnk", element="ramp", current_state="works",
                         severity="minor", nature="permanent", description="ok")
    uc.reply_to_report(ewa, r.id, "Dzięki")
    uc.repo.commit()
    again = make(url)
    place = again.repo.get_place("plc_mnk")
    assert place.opening_hours == [{"days": "Mon", "closed": True}] and place.contact == {"website": "https://mnk.pl"}
    assert again.repo.get_report(r.id).replies[0]["text"] == "Dzięki"


def test_needs_profile_persists(url):
    """F31: needs + preferred features survive a restart."""
    uc = make(url)
    uc.set_needs_profile(uc.repo.get_user("usr_anna"), ["stroller"], ["pets_allowed"])
    uc.repo.commit()
    assert make(url).get_needs_profile(make(url).repo.get_user("usr_anna")) == (["stroller"], ["pets_allowed"])


async def test_login_token_persists_between_workers(url):
    """F33: the link may be opened on a request served by another worker / after a restart."""
    from app.adapters.outbound.mailer import ConsoleMailer
    uc = make(url)
    uc.mailer = ConsoleMailer()
    await uc.request_email_login("w@example.com")
    uc.repo.commit()
    code = uc.mailer.outbox[-1].text.split("Kod logowania: ")[1].split()[0]
    other = make(url)
    _, user = other.verify_email_login(code)
    assert user.email == "w@example.com"


def test_questions_persist(url):
    """F34"""
    uc = make(url)
    q = uc.ask_question(uc.repo.get_user("usr_anna"), "plc_mnk", "Pies?", feature="pets_allowed")
    uc.answer_question(uc.repo.get_user("usr_ewa"), q.id, "Tak", value="yes")
    uc.repo.commit()
    again = make(url).repo.get_question(q.id)
    assert (again.status, again.outcome, again.answer_text, again.feature) == ("answered", "yes", "Tak", "pets_allowed")
