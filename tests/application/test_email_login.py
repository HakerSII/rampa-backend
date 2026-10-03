"""F33: passwordless login — one-time link / code sent by e-mail (15 min, single use, hashed at rest)."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.adapters.outbound.mailer import ConsoleMailer, SmtpMailer
from app.adapters.outbound.memory import FixedClock
from app.config import Settings
from app.domain.enums import Role
from app.domain.errors import RateLimited, Unauthorized, ValidationFailed
from app.domain.model import GoogleIdentity
from tests.conftest import NOW, FakeIdentityVerifier, make_use_cases


def make(**kw):
    mailer = ConsoleMailer()
    uc = make_use_cases(mailer=mailer, **kw)
    return uc, mailer


def token_from(mail) -> str:
    return mail.text.split("Kod logowania: ")[1].split()[0]


async def test_request_sends_mail_and_verify_logs_in():
    uc, mailer = make()
    await uc.request_email_login("Basia@Example.com")
    (mail,) = mailer.outbox
    assert mail.to == "basia@example.com" and "15 min" in mail.text
    token, user = uc.verify_email_login(token_from(mail))
    assert (user.email, user.role, user.display_name) == ("basia@example.com", Role.USER, "basia")
    assert uc.current_user(token).id == user.id
    await uc.request_email_login("basia@example.com")
    _, again = uc.verify_email_login(token_from(mailer.outbox[-1]))
    assert again.id == user.id                                     # same account next time


async def test_token_is_single_use_expires_and_is_hashed():
    clock = FixedClock(NOW)
    uc, mailer = make(clock=clock)
    await uc.request_email_login("a@example.com")
    code = token_from(mailer.outbox[-1])
    assert all(code not in str(t) for t in uc.repo.login_tokens.values())  # only the hash is stored
    uc.verify_email_login(code)
    with pytest.raises(Unauthorized):
        uc.verify_email_login(code)                                # used
    await uc.request_email_login("a@example.com")
    code = token_from(mailer.outbox[-1])
    clock._now = NOW + timedelta(minutes=16)
    with pytest.raises(Unauthorized):
        uc.verify_email_login(code)                                # expired
    with pytest.raises(Unauthorized):
        uc.verify_email_login("nonsense")


@pytest.mark.parametrize("email", ["", "no-at-sign", "a@b", "x" * 250 + "@example.com"])
async def test_invalid_email(email):
    uc, _ = make()
    with pytest.raises(ValidationFailed):
        await uc.request_email_login(email)


async def test_rate_limit_per_email():
    uc, _ = make()
    for _ in range(3):
        await uc.request_email_login("spam@example.com")
    with pytest.raises(RateLimited):
        await uc.request_email_login("spam@example.com")
    await uc.request_email_login("other@example.com")              # other addresses unaffected


async def test_admin_email_and_google_reuse_same_account():
    verifier = FakeIdentityVerifier({"g1": GoogleIdentity("sub-1", "boss@example.com", True, "Boss")})
    uc, mailer = make(admin_emails=["boss@example.com"], verifier=verifier, auth_mode="google")
    await uc.request_email_login("boss@example.com")
    _, user = uc.verify_email_login(token_from(mailer.outbox[-1]))
    assert user.role == Role.ADMIN
    _, google_user = await uc.login_with_google("g1")
    assert google_user.id == user.id and google_user.google_sub == "sub-1"


async def test_smtp_mailer_sends_with_starttls(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            sent["tls"] = True

        def login(self, user, password):
            sent["login"] = user

        def send_message(self, msg):
            sent["msg"] = msg

    monkeypatch.setattr("app.adapters.outbound.mailer.smtplib.SMTP", FakeSMTP)
    await SmtpMailer("smtp.example.com", 587, "user", "secret", "noreply@example.com").send("a@b.pl", "Temat", "Treść")
    assert sent["server"] == ("smtp.example.com", 587) and sent["tls"] and sent["login"] == "user"
    assert sent["msg"]["To"] == "a@b.pl" and sent["msg"]["From"] == "noreply@example.com"


def test_email_login_over_http(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    r = c.post("/api/v1/auth/email/request", json={"email": "ola.nowak@example.com"})
    assert r.status_code == 202 and r.json()["sent"] is True
    code = r.json()["dev_token"]                       # demo + console mailer only (never with real e-mail)
    v = c.post("/api/v1/auth/email/verify", json={"token": code})
    assert v.status_code == 200 and v.json()["user"]["display_name"] == "ola.nowak"
    me = c.get("/api/v1/me", headers={"Authorization": f"Bearer {v.json()['token']}"})
    assert me.status_code == 200
    assert c.post("/api/v1/auth/email/verify", json={"token": code}).status_code == 401
    assert c.post("/api/v1/auth/email/request", json={"email": "nope"}).status_code == 400
