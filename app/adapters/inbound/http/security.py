"""F42: HTTP-boundary hardening — clean user text in JSON bodies, add security headers. Pure ASGI middlewares."""
import json

from app.domain.text import clean_text

JSON_METHODS = {"POST", "PUT", "PATCH"}
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
API_CSP = b"default-src 'none'; frame-ancestors 'none'"
MEDIA_CSP = b"default-src 'none'; img-src 'self'; sandbox; frame-ancestors 'none'"


def _clean(value):
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}  # keys are field names — validated by the schemas
    return value


class CleanJsonBodyMiddleware:
    """Every string in a JSON request body → plain text (tags, <, >, control chars removed)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in JSON_METHODS:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        if not headers.get(b"content-type", b"").startswith(b"application/json"):
            return await self.app(scope, receive, send)
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        try:
            body = json.dumps(_clean(json.loads(body)), ensure_ascii=False).encode()
        except (ValueError, UnicodeDecodeError):
            pass  # invalid JSON → untouched, FastAPI answers 400
        scope = {**scope, "headers": [(k, v) for k, v in scope["headers"] if k != b"content-length"]
                 + [(b"content-length", str(len(body)).encode())]}
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()
        return await self.app(scope, replay, send)


class SecurityHeadersMiddleware:
    """nosniff, no referrer, no framing; strict CSP on the API, sandboxed CSP on /media; Swagger UI untouched."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]

        async def with_headers(message):
            if message["type"] == "http.response.start":
                extra = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"),
                         (b"x-frame-options", b"DENY")]
                if path.startswith("/media"):
                    extra.append((b"content-security-policy", MEDIA_CSP))
                elif not path.startswith(DOCS_PATHS) and path != "/":
                    extra.append((b"content-security-policy", API_CSP))
                message = {**message, "headers": list(message.get("headers") or []) + extra}
            await send(message)
        return await self.app(scope, receive, with_headers)
