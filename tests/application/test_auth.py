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


# ---------------------------------------------------------------- anonymous device identity (F12)
async def test_anonymous_login_creates_user_with_user_role():
    uc = make_use_cases()
    token, user = uc.login_anonymous()
    assert user.role == Role.USER and user.display_name == "Anonim"
    assert user.username is None and user.google_sub is None
    assert uc.current_user(token).id == user.id


async def test_each_anonymous_login_is_a_distinct_user():
    uc = make_use_cases()
    _, u1 = uc.login_anonymous()
    _, u2 = uc.login_anonymous()
    assert u1.id != u2.id


async def test_anonymous_session_outlives_google_session_ttl():
    clock = FixedClock(NOW)
    uc = make_use_cases(clock=clock)
    token, user = uc.login_anonymous()
    clock._now = NOW + timedelta(days=30)
    assert uc.current_user(token).id == user.id
    clock._now = NOW + timedelta(days=366)
    assert uc.current_user(token) is None


async def test_anonymous_login_works_in_google_mode_and_can_be_disabled():
    token, user = google_uc().login_anonymous()
    assert user.role == Role.USER
    with pytest.raises(NotFound):
        make_use_cases(anonymous_auth=False).login_anonymous()


async def test_anonymous_display_name_is_optional_and_trimmed():
    uc = make_use_cases()
    _, user = uc.login_anonymous("  Gość z Podgórza  ")
    assert user.display_name == "Gość z Podgórza"
    _, user = uc.login_anonymous("x" * 200)
    assert len(user.display_name) == 60
