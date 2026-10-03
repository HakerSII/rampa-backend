"""FastAPI app. Run (from sourcedoc/mvp): uv run uvicorn app.adapters.inbound.http.main:app"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.inbound.http.errors import error_body, install_error_handlers
from app.adapters.inbound.http.rate_limit import FixedWindowRateLimiter, RequestRateLimitMiddleware
from app.adapters.inbound.http.security import CleanJsonBodyMiddleware, SecurityHeadersMiddleware
from app.adapters.inbound.http.routers import admin, ai, auth, me, observations, owner, places, public
from app.application.ports import IdentityVerifier, StaleData
from app.bootstrap import build_use_cases
from app.config import Settings

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None, verifier: IdentityVerifier | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Kraków bez barier — MVP", version="0.1.0-mvp")
    # built eagerly (not in lifespan) so test clients without lifespan get seeded data too
    app.state.use_cases = build_use_cases(settings, verifier)
    app.state.settings = settings
    app.state.rate_limiter = FixedWindowRateLimiter(settings.public_rate_limit_per_min)

    app.add_middleware(CleanJsonBodyMiddleware)     # F42: user text → plain text
    app.add_middleware(SecurityHeadersMiddleware)   # F42: nosniff, CSP, no framing
    app.add_middleware(RequestRateLimitMiddleware,  # F43: /ai/* and login → 429 + Retry-After
                       ai_per_user=settings.ai_rate_limit_per_min, ai_per_ip=settings.ai_rate_limit_per_ip_per_min,
                       auth_per_ip=settings.auth_rate_limit_per_min, trusted_hops=settings.trusted_proxy_hops)
    # CORS outermost (added last): also 429 / error responses carry the CORS headers the browser needs
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["Retry-After"])
    install_error_handlers(app)
    for module in (auth, me, places, observations, ai, owner, admin):
        app.include_router(module.router, prefix=API_PREFIX)
    app.include_router(public.router, prefix="/public/v1")  # Open API, versioned separately
    app.mount("/media", StaticFiles(directory=settings.media_dir, check_dir=False), name="media")

    @app.middleware("http")
    async def commit_writes(request, call_next):
        """Unit of work per request: sync with other workers (F29), run, persist after every write.
        Another worker committed in between → this write is dropped, 409 CONFLICT (client retries)."""
        uc = app.state.use_cases
        uc.sync()
        response = await call_next(request)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            try:
                uc.repo.commit()
            except StaleData as e:
                return JSONResponse(error_body("CONFLICT", str(e)), 409)
        return response

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("/docs")

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "auth_mode": settings.auth_mode, "ai_mode": settings.ai_mode,
                "storage": settings.repo_mode,
                "database": settings.db_dialect if settings.repo_mode == "sql" else None}

    return app


app = create_app()
