import pytest

from app.domain.enums import FeatureKey as F, ObservationSource
from app.domain.errors import ConflictError, Forbidden, ValidationFailed
from tests.application.test_ai import upload
from tests.application.test_observations import report, user


def ewa(uc):
    return user(uc, "ewa")


async def test_owner_profile_and_update(uc):
    p = uc.owner_profile(ewa(uc))
    assert (p.display_name, p.places) == ("Ewa Nowak", 2)
    uc.update_owner_profile(ewa(uc), display_name="Ewa Nowak-Kowalska", email="ewa@mnk.pl")
    assert (ewa(uc).display_name, ewa(uc).email) == ("Ewa Nowak-Kowalska", "ewa@mnk.pl")
    with pytest.raises(ValidationFailed):
        uc.update_owner_profile(ewa(uc), email="not-an-email")


async def test_owner_stats(uc):
    report(uc)  # anna on plc_mnk
    uc.add_owner_observations(ewa(uc), "plc_mnk", [{"feature": "ramp", "value": "yes"}])
    s = uc.owner_stats(ewa(uc))
    assert (s.managed_places, s.reports_30d, s.updates_30d) == (2, 1, 1)


async def test_edit_place_hours_contact(uc):
    uc.update_owner_place(ewa(uc), "plc_mnk", short_description="Nowy opis", contact={"phone": "+48 12 433 55 00"})
    uc.set_opening_hours(ewa(uc), "plc_mnk", [{"days": "Tue-Sun", "open": "10:00", "close": "18:00"},
                                             {"days": "Mon", "closed": True}])
    place = uc.get_place("plc_mnk")
    assert place.short_description == "Nowy opis" and place.contact["phone"] == "+48 12 433 55 00"
    assert place.opening_hours[1] == {"days": "Mon", "closed": True}
    with pytest.raises(ValidationFailed):
        uc.set_opening_hours(ewa(uc), "plc_mnk", [{"days": "Mon", "open": "18:00", "close": "10:00"}])
    with pytest.raises(Forbidden):
        uc.update_owner_place(ewa(uc), "plc_ice", name="x")


async def test_owner_photos(uc):
    ph = await upload(uc, "wejscie.jpg", who="ewa")
    uc.add_place_photo(ewa(uc), "plc_mnk", ph)
    assert [p.id for p in uc.place_owner_photos("plc_mnk")] == [ph]
    uc.remove_place_photo(ewa(uc), "plc_mnk", ph)
    assert uc.place_owner_photos("plc_mnk") == []


async def test_reply_and_approve_report(uc):
    r = report(uc)
    uc.reply_to_report(ewa(uc), r.id, "Dziękujemy, serwis jutro.")
    assert uc.repo.get_report(r.id).replies[0]["text"] == "Dziękujemy, serwis jutro."
    obs = uc.approve_report(ewa(uc), r.id)
    assert (obs.source, obs.value, obs.feature) == (ObservationSource.VERIFIED_OWNER, "no", F.ELEVATOR)
    assert uc.repo.get_report(r.id).owner_status == "approved"
    with pytest.raises(ConflictError):
        uc.approve_report(ewa(uc), r.id)
    other = report(uc, place_id="plc_ice")
    with pytest.raises(Forbidden):
        uc.reply_to_report(ewa(uc), other.id, "x")


async def test_place_stats_reminders_suggestions(uc):
    report(uc)
    st = uc.owner_place_stats(ewa(uc), "plc_mnk")
    assert st.by_source["community"] == 10 and st.observations == 10  # 9 seed + anna
    texts = " | ".join(r.text for r in uc.owner_reminders(ewa(uc)))
    assert "Uzupełnij" in texts and "Odpowiedz" in texts  # camelot unknowns; anna's report unanswered
    uc.add_owner_observations(ewa(uc), "plc_camelot", [{"feature": "accessible_toilet", "value": "no"}])
    assert any(s.feature == F.ACCESSIBLE_TOILET for s in uc.owner_suggestions(ewa(uc)))


async def test_batch_all_or_nothing(uc):
    created = uc.owner_batch(ewa(uc), [{"place_id": "plc_mnk", "feature": "ramp", "value": "yes"},
                                       {"place_id": "plc_camelot", "feature": "elevator", "value": "no"}])
    assert len(created) == 2
    before = len(uc.repo.list_observations("plc_mnk"))
    with pytest.raises(Forbidden):
        uc.owner_batch(ewa(uc), [{"place_id": "plc_mnk", "feature": "ramp", "value": "no"},
                                 {"place_id": "plc_ice", "feature": "ramp", "value": "no"}])
    assert len(uc.repo.list_observations("plc_mnk")) == before


async def test_csv_import_valid_rows_and_errors(uc):
    csv = ("place_id,feature,value,temporary,comment\n"
           "plc_mnk,ramp,yes,false,ok\n"
           "plc_ice,ramp,no,false,not mine\n"
           "plc_camelot,teleporter,yes,false,bad feature\n"
           "plc_camelot,elevator,no,true,winda w remoncie\n")
    r = uc.owner_csv_import(ewa(uc), csv)
    assert r.imported == 2 and [e["row"] for e in r.errors] == [3, 4]
    assert uc.repo.states_for("plc_camelot")[F.ELEVATOR].temporary is True
    assert uc.owner_csv_template().startswith("place_id,feature,value,temporary,comment")
