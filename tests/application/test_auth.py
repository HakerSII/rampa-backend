from datetime import timedelta

import pytest

from app.adapters.outbound.memory import FixedClock
from app.domain.enums import Role
from app.domain.errors import NotFound, Unauthorized
from app.domain.model import GoogleIdentity
from tests.conftest import NOW, FakeIdentityVerifier, make_use_cases

ANNA = GoogleIdentity("sub-anna", "anna@example.com", True, "Anna Kowalska")
BOSS = GoogleIdentity("sub-boss", "Boss@Example.com", True, "Szef Moderator")
UNVERIFIED = GoogleIdentity("sub-x", "x@example.com", False, "X")


def google_uc(clock=None):
    verifier = FakeIdentityVerifier({"tok-anna": ANNA, "tok-boss": BOSS, "tok-unverified": UNVERIFIED})
    return make_use_cases(auth_mode="google", verifier=verifier, admin_emails=["boss@example.com"], clock=clock)


async def test_first_google_login_creates_user_second_reuses_it():
    uc = google_uc()
    token1, u1 = await uc.login_with_google("tok-anna")
    token2, u2 = await uc.login_with_google("tok-anna")
    assert u1.id == u2.id and token1 != token2
    assert (u1.role, u1.email, u1.display_name) == (Role.USER, "anna@example.com", "Anna Kowalska")
    assert uc.current_user(token1).id == u1.id


async def test_admin_email_gets_admin_role_case_insensitive():
    _, user = await google_uc().login_with_google("tok-boss")
    assert user.role == Role.ADMIN


@pytest.mark.parametrize("token", ["garbage", "tok-unverified"])
async def test_invalid_or_unverified_token_is_unauthorized(token):
    with pytest.raises(Unauthorized):
        await google_uc().login_with_google(token)


async def test_logout_and_expiry_make_user_guest():
    clock = FixedClock(NOW)
    uc = google_uc(clock)
    token, _ = await uc.login_with_google("tok-anna")
    uc.logout(token)
    assert uc.current_user(token) is None

    token, _ = await uc.login_with_google("tok-anna")
    clock._now = NOW + timedelta(hours=25)
    assert uc.current_user(token) is None


async def test_demo_login_only_in_demo_mode():
    with pytest.raises(NotFound):
        google_uc().login_demo("anna")
    uc = make_use_cases()
    token, user = uc.login_demo("anna")
    assert uc.current_user(token).id == user.id == "usr_anna"
    with pytest.raises(Unauthorized):
        uc.login_demo("nobody")


async def test_google_login_disabled_in_demo_mode():
    with pytest.raises(NotFound):
        await make_use_cases().login_with_google("tok-anna")
