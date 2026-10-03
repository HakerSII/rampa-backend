# F43 — Rate limits on AI and login

Overview: [../../README.md](../../README.md) · extends F5 (Open API key limit) and F33 (3 login e-mails / address / 15 min)

- `RequestRateLimitMiddleware` (in memory, per process, fixed 60 s window) → `429 RATE_LIMITED` + `Retry-After`:
  - `/api/v1/ai/*`: per user (Bearer token, else IP) `AI_RATE_LIMIT_PER_MIN` (10) and per IP `AI_RATE_LIMIT_PER_IP_PER_MIN` (30) — the IP cap stops many anonymous accounts from one machine.
  - `POST /api/v1/auth/*` except logout: per IP `AUTH_RATE_LIMIT_PER_MIN` (20).
  - `0` disables a limit (e2e / load tests).
- Client IP: socket address; with `TRUSTED_PROXY_HOPS=1` (Render) the address appended by the proxy (`X-Forwarded-For`, counted from the right) — never the client-supplied left part.
- Limiter drops expired windows when it holds more than 10 000 keys (no unbounded memory).
- Limits: per worker (several workers → limit × workers); a model daily budget is not part of this (failures already fall back to rules / mock).
