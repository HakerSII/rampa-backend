# F33 — Passwordless e-mail login (magic link / code)

Overview: [../../PLAN-GAPS.md](../../PLAN-GAPS.md) · contract: [openapi.yaml](openapi.yaml)

- `POST /auth/email/request {email}` → 202 always (no account enumeration). One-time code, 15 min, single use; only its SHA-256 is stored (`login_tokens`). Max 3 requests per address per 15 min → 429.
- Mail: port `Mailer` — `MAILER=console` (default: logs the mail; in `AUTH_MODE=demo` the response also has `dev_token` for the demo / e2e) | `smtp` (`SMTP_HOST/PORT/USER/PASSWORD`, `MAIL_FROM`, STARTTLS). `EMAIL_LINK_URL` (front-end page) → link `…?token=`; empty → code only.
- `POST /auth/email/verify {token}` → session (same as Google). New address → new user (`display_name` = part before @; admin if in `ADMIN_EMAILS`). Google login with the same verified e-mail reuses that account.
- Works in every `AUTH_MODE` (`EMAIL_LOGIN=false` disables).
