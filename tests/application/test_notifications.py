"""F35: in-app notifications — the user learns what happened to their questions, reports and requests."""
import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings
from app.domain.errors import NotFound, Unauthorized
from tests.application.test_observations import report, user


def kinds(uc, who):
    return [n.kind for n in uc.list_notifications(user(uc, who))]


async def test_question_answer_notifies_asker(uc):
    q = uc.ask_question(user(uc, "anna"), "plc_camelot", "Pies?", feature="pets_allowed")
    uc.answer_question(user(uc, "ewa"), q.id, "Tak", value="yes")
    (n,) = uc.list_notifications(user(uc, "anna"))
    assert (n.kind, n.place_id, n.ref_id, n.read) == ("question_answered", "plc_camelot", q.id, False)
    assert "Cafe Camelot" in n.text
    assert kinds(uc, "ewa") == []                               # the actor is not notified


async def test_owner_reply_and_approve_notify_report_author(uc):
    r = report(uc)
    uc.reply_to_report(user(uc, "ewa"), r.id, "Serwis jutro rano.")
    uc.approve_report(user(uc, "ewa"), r.id)
    assert kinds(uc, "anna") == ["report_approved", "report_reply"]   # newest first


async def test_conflict_decision_notifies_observation_authors(uc):
    anna_report = report(uc)                                    # Anna: elevator no
    marek = uc.add_observation(user(uc, "marek"), "plc_mnk", feature="elevator", value="yes")
    (item,) = uc.list_queue(user(uc, "admin"), filter="conflict")
    uc.decide(user(uc, "admin"), item.id, "confirm", winning_observation_id=marek.id)
    assert "observation_rejected" in kinds(uc, "anna") and kinds(uc, "marek") == ["observation_confirmed"]
    assert anna_report


async def test_ownership_and_abuse_decisions_notify(uc):
    req = uc.request_ownership(user(uc, "jan"), "plc_ice", "Kierownik")
    uc.verify_ownership(user(uc, "admin"), req.id, True)
    assert kinds(uc, "jan") == ["ownership_decided"]
    o = uc.add_observation(user(uc, "marek"), "plc_camelot", feature="ramp", value="no")
    item = uc.report_abuse(user(uc, "anna"), o.id, "spam")
    uc.decide(user(uc, "admin"), item.id, "confirm")
    assert kinds(uc, "anna")[0] == "abuse_decided"


async def test_read_one_and_all(uc):
    for text in ("a", "b"):
        q = uc.ask_question(user(uc, "anna"), "plc_camelot", text)
        uc.answer_question(user(uc, "ewa"), q.id, "ok")
    anna = user(uc, "anna")
    first, second = uc.list_notifications(anna)
    uc.mark_notification_read(anna, first.id)
    assert [n.id for n in uc.list_notifications(anna, unread_only=True)] == [second.id]
    assert uc.mark_all_notifications_read(anna) == 1
    assert uc.list_notifications(anna, unread_only=True) == []
    with pytest.raises(NotFound):
        uc.mark_notification_read(user(uc, "jan"), second.id)  # someone else's
    with pytest.raises(Unauthorized):
        uc.list_notifications(None)


def test_notifications_over_http(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    anna, ewa = {"Authorization": "Bearer demo-anna"}, {"Authorization": "Bearer demo-ewa"}
    q = c.post("/api/v1/places/plc_camelot/questions", headers=anna, json={"text": "Toaleta?"}).json()
    c.post(f"/api/v1/owner/questions/{q['id']}/answer", headers=ewa, json={"text": "Jest na parterze."})
    body = c.get("/api/v1/me/notifications", headers=anna).json()
    assert body["unread"] == 1 and body["items"][0]["kind"] == "question_answered"
    nid = body["items"][0]["id"]
    assert c.post(f"/api/v1/me/notifications/{nid}/read", headers=anna).status_code == 204
    assert c.get("/api/v1/me/notifications", params={"unread": "true"}, headers=anna).json()["items"] == []
    assert c.post("/api/v1/me/notifications/read-all", headers=anna).json() == {"marked": 0}
    assert c.get("/api/v1/me/notifications").status_code == 401
