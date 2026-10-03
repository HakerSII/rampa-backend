"""FastAPI app. Run (from sourcedoc/mvp): uv run uvicorn app.adapters.inbound.http.main:app"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.adapters.inbound.http.errors import install_error_handlers
from app.adapters.inbound.http.routers import admin, auth, places
from app.application.ports import IdentityVerifier
from app.bootstrap import build_use_cases
from app.config import Settings

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None, verifier: IdentityVerifier | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Kraków bez barier — MVP", version="0.1.0-mvp")
    # built eagerly (not in lifespan) so test clients without lifespan get seeded data too
    app.state.use_cases = build_use_cases(settings, verifier)
    app.state.settings = settings

    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    install_error_handlers(app)
    for module in (auth, places, admin):
        app.include_router(module.router, prefix=API_PREFIX)
    app.mount("/media", StaticFiles(directory=settings.media_dir, check_dir=False), name="media")

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "auth_mode": settings.auth_mode, "storage": "memory"}

    return app


app = create_app()
