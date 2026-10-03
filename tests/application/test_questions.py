"""F34: users ask the owner about a place; the owner answers, can set the attribute (verified_owner observation)
or mark it planned; needs statistics for owners and the city (admin)."""
import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings
from app.domain.enums import FeatureKey as F
from app.domain.errors import Forbidden, NotFound, Unauthorized, ValidationFailed
from tests.application.test_observations import user


async def test_ask_and_owner_answers_with_attribute(uc):
    q = uc.ask_question(user(uc, "anna"), "plc_camelot", "Czy można wejść z psem?", feature="pets_allowed")
    assert (q.status, q.feature) == ("open", F.PETS_ALLOWED)
    ewa = user(uc, "ewa")
    assert [x.id for x in uc.owner_questions(ewa)] == [q.id]
    uc.answer_question(ewa, q.id, "Tak, psy są mile widziane.", value="yes")
    assert (q.status, q.outcome, q.answered_by) == ("answered", "yes", "usr_ewa")
    state = uc.get_accessibility("plc_camelot")[F.PETS_ALLOWED]
    assert state.state == "yes"                                           # owner observation created
    assert uc.repo.get_observation(state.active_observation_id).source == "verified_owner"
    assert [x.id for x in uc.place_questions("plc_camelot")] == [q.id]   # public Q&A on the place


async def test_owner_marks_feature_planned_without_changing_data(uc):
    q = uc.ask_question(user(uc, "jan"), "plc_mnk", "Brakuje informacji o szerokości drzwi", feature="wide_doors")
    uc.answer_question(user(uc, "ewa"), q.id, "Pomiar drzwi w przyszłym tygodniu.", planned=True)
    assert q.outcome == "planned" and uc.get_accessibility("plc_mnk")[F.WIDE_DOORS].state == "unknown"


async def test_question_rules(uc):
    with pytest.raises(Unauthorized):
        uc.ask_question(None, "plc_mnk", "x")
    with pytest.raises(ValidationFailed):
        uc.ask_question(user(uc, "anna"), "plc_mnk", "  ")
    with pytest.raises(ValidationFailed):
        uc.ask_question(user(uc, "anna"), "plc_mnk", "x", feature="teleport")
    with pytest.raises(NotFound):
        uc.ask_question(user(uc, "anna"), "nope", "x")
    q = uc.ask_question(user(uc, "anna"), "plc_ice", "Czy jest pętla?", feature="induction_loop")
    with pytest.raises(Forbidden):
        uc.answer_question(user(uc, "ewa"), q.id, "nie moje")           # ICE is not Ewa's
    with pytest.raises(ValidationFailed):
        uc.answer_question(user(uc, "admin"), q.id, "ok", value="yes", planned=True)  # one or the other


async def test_admin_can_answer_and_answer_once(uc):
    q = uc.ask_question(user(uc, "anna"), "plc_ice", "Czy jest pętla?", feature="induction_loop")
    uc.answer_question(user(uc, "admin"), q.id, "Jest w sali głównej.", value="partial")
    from app.domain.errors import ConflictError
    with pytest.raises(ConflictError):
        uc.answer_question(user(uc, "admin"), q.id, "again")


async def test_needs_stats_and_owner_reminder(uc):
    for who in ("anna", "jan", "ola"):
        uc.ask_question(user(uc, who), "plc_mnk", "Pies?", feature="pets_allowed")
    uc.ask_question(user(uc, "anna"), "plc_camelot", "Toaleta?", feature="accessible_toilet")
    uc.ask_question(user(uc, "jan"), "plc_camelot", "Godziny?")
    stats = uc.needs_stats(user(uc, "admin"))
    assert stats.by_feature[0] == (F.PETS_ALLOWED, 3) and stats.open == 5 and stats.without_feature == 1
    own = uc.needs_stats(user(uc, "ewa"))                                 # owner: own places only
    assert own.open == 5
    kinds = [r.kind for r in uc.owner_reminders(user(uc, "ewa"))]
    assert "unanswered_question" in kinds
    with pytest.raises(Forbidden):
        uc.needs_stats(user(uc, "anna"))


def test_questions_over_http(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    anna, ewa, admin = ({"Authorization": f"Bearer demo-{u}"} for u in ("anna", "ewa", "admin"))
    q = c.post("/api/v1/places/plc_camelot/questions", headers=anna,
               json={"text": "Czy jest przewijak?", "feature": "baby_changing_table"})
    assert q.status_code == 201 and q.json()["status"] == "open"
    assert c.get("/api/v1/owner/questions", headers=ewa).json()["items"][0]["id"] == q.json()["id"]
    a = c.post(f"/api/v1/owner/questions/{q.json()['id']}/answer", headers=ewa,
               json={"text": "Nie mamy, ale planujemy.", "planned": True})
    assert a.status_code == 200 and a.json()["outcome"] == "planned"
    pub = c.get("/api/v1/places/plc_camelot/questions").json()["items"]
    assert pub[0]["answer"]["text"] == "Nie mamy, ale planujemy."
    stats = c.get("/api/v1/admin/needs-stats", headers=admin).json()
    assert stats["by_feature"][0] == {"feature": "baby_changing_table", "label": "Przewijak dla dzieci", "questions": 1}
    assert c.post("/api/v1/places/plc_camelot/questions", json={"text": "x"}).status_code == 401
