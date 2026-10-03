# F1 — Auth (demo + Google Sign-In)

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · needs: [F0](../00-skeleton/plan.md)

## Scope

- Two modes, `AUTH_MODE`:
  - `demo` (default demo/tests): `POST /auth/demo {username}` → seeded account. Offline. Ships as stub in F0.7, finalized here.
  - `google`: Google Identity Services, "ID token" flow. Front gets `id_token` from Google (no server-side redirects) → backend verifies → issues own opaque session token.
- No passwords, no own refresh tokens. Google account → `User` mapping only.
- Roles: `guest` (no/invalid token), `user` (any login), `admin` (seeded `admin` in demo mode; email in `ADMIN_EMAILS` in google mode). No `owner` / `api_client`.

## Model

```python
User(id, display_name, role: Literal["user", "admin"], email: str | None, google_sub: str | None)
Session(token: str, user_id: str, expires_at: datetime)    # opaque, TTL 24 h
GoogleIdentity(sub, email, email_verified, name)            # port output, not persisted
```

Config: `AUTH_MODE`, `GOOGLE_CLIENT_ID` (env; not secret, still not hardcoded), `ADMIN_EMAILS` (comma list).

## Use cases

- `login_demo(username) -> (Session, User)` — `AUTH_MODE=demo` only (else `NotFound`); unknown username → `Unauthorized`.
- `login_with_google(id_token) -> (Session, User)`:
  - `IdentityVerifier.verify(id_token)`; checks signature, `aud == GOOGLE_CLIENT_ID`, `exp`, `iss`, `email_verified`.
  - Upsert user by `google_sub` (no duplicates); role `admin` if email in `ADMIN_EMAILS`, else `user`.
  - `display_name` stored full; public views use "Anna K." form (full plan value object `PublicName`).
- `logout(token)` — delete session.
- `current_user(token) -> User | None` — `None` = guest (missing/unknown/expired token).

## Tasks

| Id | What | Output / acceptance |
|---|---|---|
| F1.0 | Google Cloud Console (human, while online) | OAuth client "Web", authorized JS origins `http://localhost:5173`, `http://localhost:8000` (+ demo host). Client ID → `.env` (not committed) |
| F1.1 | 🔴 Tests first | `tests/application/test_auth.py` on `FakeIdentityVerifier`: new user created; 2nd login same `sub` → same user; admin email → `admin`; invalid token → `Unauthorized`; `email_verified=false` → `Unauthorized`; expired session → guest |
| F1.2 | Use cases | `login_demo`, `login_with_google`, `logout`, `current_user` in `use_cases.py` → F1.1 green |
| F1.3 | Google adapter | `adapters/outbound/google_auth.py`: wrap `google.oauth2.id_token.verify_oauth2_token(token, Request(), client_id, clock_skew_in_seconds=10)`. **Sync + network → `await asyncio.to_thread(...)`.** Cache certs (`CacheControl` session, or keep one `Request` object). Errors → `Unauthorized` |
| F1.4 | HTTP | `POST /auth/demo`, `POST /auth/google`, `POST /auth/logout`, `GET /me` per [openapi.yaml](openapi.yaml); `deps.current_user` reads `Authorization: Bearer` |
| F1.5 | Front button (F frontend) | Google Identity Services JS "Sign in with Google" → `POST /auth/google` → keep token in memory/`localStorage`. Demo: user picker → `POST /auth/demo` |

## Deps

- `uv add google-auth requests` (`requests` = transport for google-auth).
- Network only in `GoogleIdentityVerifier`, only in `AUTH_MODE=google`. Tests never hit Google (fake verifier).

## DoD

- `POST /auth/demo {"username":"anna"}` → 200 `{token, user}`; in `google` mode → 404.
- `POST /auth/google {"id_token": "<real Google token>"}` → 200; same account again → same `user.id`.
- Bad/expired `id_token` → 401 `{"error": {"code": "UNAUTHORIZED", ...}}`.
- `GET /me` with valid token → 200 user; no/unknown/expired token → **401** (same as full contract).
- Public endpoints (`/places*`) work without token (guest).
- F1.1 tests green, STATUS.md + commit.

> Diff vs full contract: full `openapi.yaml` has demo `POST /auth/login {username, password}`. MVP replaces it with `POST /auth/demo {username}` (no fake password) + adds `POST /auth/google`, `POST /auth/logout`. On merge: replace `/auth/login` in full contract with these three.
