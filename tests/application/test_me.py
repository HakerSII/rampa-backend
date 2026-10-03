import pytest

from app.domain.errors import NotFound, Unauthorized
from tests.application.test_observations import report, user


async def test_favorites_add_list_remove_idempotent(uc):
    anna = user(uc, "anna")
    uc.add_favorite(anna, "plc_mnk")
    uc.add_favorite(anna, "plc_ice")
    uc.add_favorite(anna, "plc_mnk")  # idempotent
    assert [p.id for p in uc.list_favorites(anna)] == ["plc_mnk", "plc_ice"]
    uc.remove_favorite(anna, "plc_mnk")
    uc.remove_favorite(anna, "plc_mnk")  # idempotent
    assert [p.id for p in uc.list_favorites(anna)] == ["plc_ice"]
    assert uc.list_favorites(user(uc, "jan")) == []


async def test_favorite_unknown_place_and_login(uc):
    with pytest.raises(NotFound):
        uc.add_favorite(user(uc, "anna"), "nope")
    with pytest.raises(Unauthorized):
        uc.list_favorites(None)


async def test_my_reports_newest_first_only_mine(uc):
    r1 = report(uc)
    r2 = report(uc, element="ramp", description="Podjazd zastawiony")
    report(uc, author="jan")
    assert [r.id for r in uc.my_reports(user(uc, "anna"))] == [r2.id, r1.id]
