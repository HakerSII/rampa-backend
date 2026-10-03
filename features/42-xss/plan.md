# F42 — XSS hardening (backend side)

Overview: [../../README.md](../../README.md)

- The API returns JSON only; XSS happens when a client renders user text as HTML. **The front end must render user text as text** (textContent / framework escaping). The backend adds defence in depth:
- `CleanJsonBodyMiddleware`: every string in a JSON request body → HTML tags, `<` `>` and control chars removed (`app/domain/text.py::clean_text`; newlines / tabs kept). Text that becomes empty fails validation like empty text.
- Also cleaned below HTTP: observation comments (`_new_observation`), upload file names, Gemini image description / barrier type.
- `contact.website` must be `http(s)://…` (no `javascript:` links); `email`, `phone` validated.
- `SecurityHeadersMiddleware`: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`; CSP `default-src 'none'; frame-ancestors 'none'` on the API, sandboxed CSP on `/media`; `/docs` and `/redoc` keep Swagger working.
- Limit: data stored before F42 is not rewritten (front-end escaping covers it).
