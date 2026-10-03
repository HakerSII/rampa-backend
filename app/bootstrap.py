"""Composition root: settings → adapters → use cases."""
import logging

from app.adapters.outbound.files import LocalFileStorage
from app.adapters.outbound.osm_file import FileOsmSource
from app.adapters.outbound.vision_mock import FallbackVisionAnalyzer, MockVisionAnalyzer
from app.adapters.outbound.memory import FixedClock, InMemoryRepo, SeqIdGenerator, SystemClock
from app.application.ports import IdentityVerifier
from app.application.use_cases import UseCases
from app.config import Settings


log = logging.getLogger(__name__)


def build_vision(settings: Settings):
    mock = MockVisionAnalyzer()
    if settings.ai_mode == "gemini":
        from app.adapters.outbound.vision_gemini import GeminiVisionAnalyzer
        if not settings.gemini_api_key:
            log.warning("AI_MODE=gemini but GEMINI_API_KEY is empty → every call falls back to mock")
        gemini = GeminiVisionAnalyzer(settings.gemini_api_key, settings.gemini_model, settings.gemini_api_url,
                                      timeout_s=settings.ai_timeout_s)
        return FallbackVisionAnalyzer(gemini, mock, settings.ai_timeout_s)
    if settings.ai_mode == "onnx":
        from app.adapters.outbound.vision_onnx import OnnxPhiVisionAnalyzer
        return FallbackVisionAnalyzer(OnnxPhiVisionAnalyzer(settings.ai_model_path), mock, settings.ai_timeout_s)
    return mock


def build_use_cases(settings: Settings, verifier: IdentityVerifier | None = None) -> UseCases:
    clock = FixedClock(settings.demo_now) if settings.demo_now else SystemClock()
    if verifier is None and settings.auth_mode == "google":
        from app.adapters.outbound.google_auth import GoogleIdentityVerifier
        verifier = GoogleIdentityVerifier(settings.google_client_id)
    vision = build_vision(settings)
    ids = SeqIdGenerator()
    repo = InMemoryRepo() if settings.repo_mode == "memory" else _sql_repo(settings.database_url)
    use_cases = UseCases(
        repo, clock, ids, LocalFileStorage(settings.media_dir), verifier,
        auth_mode=settings.auth_mode, admin_emails=settings.admin_email_list,
        session_ttl_hours=settings.session_ttl_hours, vision=vision,
        osm=FileOsmSource(settings.osm_file),
    )
    if repo.is_empty():
        use_cases.load_seed()
        repo.commit()
    else:  # persisted data: keep it, continue id sequences
        for existing_id in repo.all_ids():
            ids.observe(existing_id)
    return use_cases


def _sql_repo(url: str):
    from app.adapters.outbound.sql import SqlRepo
    return SqlRepo(url)
