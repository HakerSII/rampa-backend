import pytest

from app.domain.enums import FeatureKey as F
from app.domain.errors import ConflictError, Forbidden, ValidationFailed
from tests.application.test_observations import report, user


def draft(uc, who="anna", **fields):
    return uc.create_report(user(uc, who), place_id="plc_mnk", draft=True, **fields)


async def test_draft_needs_only_place_and_changes_nothing(uc):
    before = uc.repo.states_for("plc_mnk")[F.ELEVATOR].state
    d = draft(uc, description="Winda chyba nie działa")
    assert (d.status, d.element, d.observation_ids) == ("draft", None, [])
    assert uc.repo.states_for("plc_mnk")[F.ELEVATOR].state == before


async def test_patch_then_submit_creates_observation(uc):
    d = draft(uc)
    uc.update_report(user(uc, "anna"), d.id, element="elevator", current_state="not_working")
    uc.update_report(user(uc, "anna"), d.id, severity="critical", nature="temporary", description="Nieczynna")
    s = uc.submit_report(user(uc, "anna"), d.id)
    assert s.status == "submitted" and len(s.observation_ids) == 1
    assert uc.repo.states_for("plc_mnk")[F.ELEVATOR].state == "no"


async def test_submit_incomplete_lists_missing_fields(uc):
    d = draft(uc, element="elevator")
    with pytest.raises(ValidationFailed, match="current_state"):
        uc.submit_report(user(uc, "anna"), d.id)


async def test_patch_validates_each_field(uc):
    d = draft(uc)
    with pytest.raises(ValidationFailed):
        uc.update_report(user(uc, "anna"), d.id, element="teleporter")


async def test_only_author_and_only_drafts(uc):
    d = draft(uc)
    with pytest.raises(Forbidden):
        uc.update_report(user(uc, "jan"), d.id, description="x")
    with pytest.raises(Forbidden):
        uc.submit_report(user(uc, "admin"), d.id)
    submitted = report(uc)
    with pytest.raises(ConflictError):
        uc.update_report(user(uc, "anna"), submitted.id, description="x")
    with pytest.raises(ConflictError):
        uc.submit_report(user(uc, "anna"), submitted.id)


async def test_drafts_hidden_from_owner_and_stats_but_in_my_reports(uc):
    d = draft(uc)
    assert [r.id for r in uc.my_reports(user(uc, "anna"))] == [d.id]
    assert uc.list_owner_reports(user(uc, "ewa")) == []
    assert uc.admin_stats(user(uc, "admin")).new_reports_today.value == 0
