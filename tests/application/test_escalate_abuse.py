import pytest

from app.domain.enums import FeatureKey as F, QueueStatus, ValidationStatus
from app.domain.errors import ConflictError, Forbidden, Unauthorized, ValidationFailed
from tests.application.test_observations import report, user


def conflict(uc):
    anna = report(uc).observation_ids[0]
    marek = uc.add_observation(user(uc, "marek"), "plc_mnk", feature="elevator", value="yes")
    (item,) = uc.list_queue(user(uc, "admin"), filter="conflict")
    return item, anna, marek.id


# ---------------------------------------------------------------- escalate
async def test_escalate_keeps_item_pending_and_data_unchanged(uc):
    item, _, marek = conflict(uc)
    before = uc.repo.states_for("plc_mnk")[F.ELEVATOR].state
    uc.decide(user(uc, "admin"), item.id, "escalate", comment="Koordynator: telefon do MNK")
    assert (item.status, item.decision) == (QueueStatus.ESCALATED, "escalated")
    assert uc.repo.states_for("plc_mnk")[F.ELEVATOR].state == before
    assert [q.id for q in uc.list_queue(user(uc, "admin"), status="escalated")] == [item.id]
    # a new contradicting observation extends the escalated item instead of opening a second one
    uc.add_observation(user(uc, "jan"), "plc_mnk", feature="elevator", value="no")
    assert len(uc.list_queue(user(uc, "admin"), filter="conflict", status="all")) == 1
    # escalated can still be decided
    state = uc.decide(user(uc, "admin"), item.id, "confirm", winning_observation_id=marek)
    assert state.state == "yes" and item.status == QueueStatus.RESOLVED


# ---------------------------------------------------------------- abuse reports
async def test_user_reports_abuse_admin_confirms_flag(uc):
    spam = uc.add_observation(user(uc, "marek"), "plc_camelot", feature="ramp", value="no", comment="asdf")
    item = uc.report_abuse(user(uc, "anna"), spam.id, "Spam, to nieprawda")
    uc.report_abuse(user(uc, "jan"), spam.id, "Fałszywe zgłoszenie")
    assert item.type == "abuse" and len(item.comments) == 2
    assert [q.id for q in uc.list_queue(user(uc, "admin"), filter="abuse")] == [item.id]
    assert uc.list_queue(user(uc, "admin"), filter="conflict") == []  # not mixed with conflicts
    uc.decide(user(uc, "admin"), item.id, "confirm")
    assert spam.validation == ValidationStatus.FLAGGED and spam.flag_reason
    assert uc.repo.states_for("plc_camelot")[F.RAMP].state == "yes"  # seed again


async def test_admin_rejects_abuse_report_nothing_changes(uc):
    o = uc.add_observation(user(uc, "marek"), "plc_camelot", feature="ramp", value="no")
    item = uc.report_abuse(user(uc, "anna"), o.id, "Nie zgadzam się")
    uc.decide(user(uc, "admin"), item.id, "reject")
    assert (o.validation, item.decision) == (ValidationStatus.VALID, "rejected")


async def test_abuse_report_rules(uc):
    o = uc.add_observation(user(uc, "marek"), "plc_camelot", feature="ramp", value="no")
    with pytest.raises(ValidationFailed):
        uc.report_abuse(user(uc, "marek"), o.id, "own")      # not on own observation
    with pytest.raises(ValidationFailed):
        uc.report_abuse(user(uc, "anna"), o.id, "  ")        # reason required
    uc.report_abuse(user(uc, "anna"), o.id, "spam")
    with pytest.raises(ConflictError):
        uc.report_abuse(user(uc, "anna"), o.id, "again")     # once per user
    with pytest.raises(Unauthorized):
        uc.report_abuse(None, o.id, "x")


async def test_stats_and_owner_views_count_only_conflicts(uc):
    o = uc.add_observation(user(uc, "marek"), "plc_mnk", feature="ramp", value="no")
    uc.report_abuse(user(uc, "anna"), o.id, "spam")
    assert uc.admin_stats(user(uc, "admin")).data_conflicts.value == 0
    assert uc.owner_stats(user(uc, "ewa")).open_conflicts == 0
