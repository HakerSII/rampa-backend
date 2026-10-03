from app.domain.enums import ObservationSource
from tests.application.test_ai import upload
from tests.application.test_observations import report, user


async def scenario(uc):
    photo = await upload(uc, "winda.png")
    anna = report(uc, photo_ids=[photo]).observation_ids[0]
    uc.vote(user(uc, "jan"), anna, 1)
    marek = uc.add_observation(user(uc, "marek"), "plc_mnk", feature="elevator", value="yes")
    (item,) = uc.list_queue(user(uc, "admin"))
    uc.decide(user(uc, "admin"), item.id, "confirm", winning_observation_id=marek.id)
    uc.add_owner_observations(user(uc, "ewa"), "plc_mnk", [{"feature": "ramp", "value": "yes"}])
    return photo, anna


async def test_activity_feed_newest_first_with_types(uc):
    await scenario(uc)
    feed = uc.place_activity("plc_mnk", limit=50)
    assert [uc_type for uc_type in (uc.activity_type(o) for o in feed[:4])] == [
        "owner_update", "admin_decision", "confirmation", "issue_reported"]
    assert uc.activity_type(feed[-1]) == "initial_data"
    assert len(uc.place_activity("plc_mnk", limit=2)) == 2


async def test_photos_gallery_from_evidence(uc):
    photo, anna = await scenario(uc)
    ((p, obs),) = uc.place_photos("plc_mnk")
    assert (p.id, obs.id, obs.author_id) == (photo, anna, "usr_anna")
    assert uc.place_photos("plc_ice") == []


async def test_verification_reflects_fresh_admin_decision(uc):
    await scenario(uc)
    v = uc.verification_for("plc_mnk")
    assert v.label == "Potwierdzone dzisiaj" and v.status == "confirmed"
    assert {"admin", "verified_owner", "community"} <= set(v.sources)
    seed_only = uc.verification_for("plc_urzad")
    assert seed_only.label == "Zweryfikowane 60 dni temu" and seed_only.sources == [ObservationSource.COMMUNITY]
