"""F43: rate limits on /ai/* (per user + per IP) and on login endpoints (per IP) → 429 + Retry-After."""
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.adapters.inbound.http.rate_limit import FixedWindowRateLimiter, client_ip
from app.config import Settings

Q = {"query": "muzeum, wózek"}


def app(tmp_path, **kw):
    return TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path), **kw)))


def test_ai_limit_per_user(tmp_path):
    c = app(tmp_path, ai_rate_limit_per_min=2, ai_rate_limit_per_ip_per_min=100)
    anna, jan = {"Authorization": "Bearer demo-anna"}, {"Authorization": "Bearer demo-jan"}
    assert [c.post("/api/v1/ai/recommend", json=Q, headers=anna).status_code for _ in range(2)] == [200, 200]
    r = c.post("/api/v1/ai/recommend", json=Q, headers=anna)
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED" and int(r.headers["retry-after"]) >= 1
    assert c.post("/api/v1/ai/recommend", json=Q, headers=jan).status_code == 200   # other user, own budget


def test_ai_limit_per_ip_caps_many_accounts(tmp_path):
    c = app(tmp_path, ai_rate_limit_per_min=100, ai_rate_limit_per_ip_per_min=3)
    codes = [c.post("/api/v1/ai/recommend", json=Q, headers={"Authorization": f"Bearer demo-{u}"}).status_code
             for u in ("anna", "jan", "ola", "piotr")]
    assert codes == [200, 200, 200, 429]                                          # same IP, many tokens


def test_login_limit_per_ip_and_other_endpoints_unaffected(tmp_path):
    c = app(tmp_path, auth_rate_limit_per_min=2)
    assert [c.post("/api/v1/auth/anonymous", json={}).status_code for _ in range(2)] == [201, 201]
    assert c.post("/api/v1/auth/demo", json={"username": "anna"}).status_code == 429   # shared login bucket
    assert c.post("/api/v1/auth/email/request", json={"email": "a@example.com"}).status_code == 429
    assert c.get("/api/v1/places").status_code == 200
    assert c.get("/api/v1/me", headers={"Authorization": "Bearer demo-anna"}).status_code == 200
    assert c.post("/api/v1/auth/logout", headers={"Authorization": "Bearer demo-anna"}).status_code == 204


def test_zero_disables_limit(tmp_path):
    c = app(tmp_path, auth_rate_limit_per_min=0)
    assert all(c.post("/api/v1/auth/anonymous", json={}).status_code == 201 for _ in range(30))


def test_forwarded_for_only_with_trusted_proxy():
    scope = {"client": ("10.0.0.1", 1234), "headers": [(b"x-forwarded-for", b"6.6.6.6, 1.2.3.4")]}
    assert client_ip(scope, trusted_hops=0) == "10.0.0.1"        # header ignored → cannot be spoofed
    assert client_ip(scope, trusted_hops=1) == "1.2.3.4"         # Render: the address its proxy appended
    assert client_ip({"client": None, "headers": []}, trusted_hops=1) == "unknown"


def test_forwarded_ips_get_separate_buckets(tmp_path):
    c = app(tmp_path, auth_rate_limit_per_min=1, trusted_proxy_hops=1)
    one = {"X-Forwarded-For": "1.1.1.1"}
    assert c.post("/api/v1/auth/anonymous", json={}, headers=one).status_code == 201
    assert c.post("/api/v1/auth/anonymous", json={}, headers=one).status_code == 429
    assert c.post("/api/v1/auth/anonymous", json={}, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 201


def test_limiter_forgets_old_windows():
    t = [0.0]
    lim = FixedWindowRateLimiter(1, now=lambda: t[0], max_keys=3)
    for i in range(3):
        lim.hit(f"ip{i}")
    t[0] = 61.0
    lim.hit("ip-new")                                             # over max_keys → expired windows dropped
    assert len(lim._windows) == 1


def test_429_reaches_the_browser_with_cors_headers(tmp_path):
    c = app(tmp_path, auth_rate_limit_per_min=1)
    origin = {"Origin": "https://front.example"}
    c.post("/api/v1/auth/anonymous", json={}, headers=origin)
    r = c.post("/api/v1/auth/anonymous", json={}, headers=origin)
    assert r.status_code == 429 and r.headers["access-control-allow-origin"] == "*"
    assert "retry-after" in r.headers["access-control-expose-headers"].lower()
