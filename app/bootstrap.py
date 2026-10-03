"""Composition root: settings → adapters → use cases."""
import logging

from app.adapters.outbound.files import LocalFileStorage
from app.adapters.outbound.osm_file import FileOsmSource
from app.adapters.outbound.vision_mock import FallbackVisionAnalyzer, MockVisionAnalyzer
from app.adapters.outbound.memory import FixedClock, InMemoryRepo, SeqIdGenerator, SystemClock
from app.application.ports import IdentityVerifier, StaleData
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


def build_geocoder(settings: Settings):
    if settings.geocoder != "nominatim":
        return None
    from app.adapters.outbound.osm_live import NominatimGeocoder
    return NominatimGeocoder(settings.nominatim_url, settings.http_user_agent, timeout_s=settings.external_timeout_s)


def build_recommender(settings: Settings):
    if settings.ai_recommender != "claude":
        return None
    if not settings.anthropic_api_key:
        log.warning("AI_RECOMMENDER=claude but ANTHROPIC_API_KEY is empty → rules")
        return None
    from app.adapters.outbound.recommender_claude import ClaudeQueryInterpreter
    return ClaudeQueryInterpreter(settings.anthropic_api_key, settings.claude_model, timeout_s=settings.ai_timeout_s)


def build_router(settings: Settings):
    if settings.router != "osrm":
        return None
    from app.adapters.outbound.osrm import OsrmRouter
    return OsrmRouter(settings.osrm_url, settings.http_user_agent, timeout_s=settings.external_timeout_s)


def build_osm_live(settings: Settings):
    """Only used on explicit admin import {"source": "overpass"}; falls back to the snapshot."""
    from app.adapters.outbound.osm_live import FallbackOsmSource, OverpassOsmSource
    live = OverpassOsmSource(settings.overpass_url, settings.osm_center_lat, settings.osm_center_lon,
                             settings.osm_radius_m, settings.http_user_agent, timeout_s=max(settings.external_timeout_s, 25))
    return FallbackOsmSource(live, FileOsmSource(settings.osm_file))


def build_use_cases(settings: Settings, verifier: IdentityVerifier | None = None) -> UseCases:
    clock = FixedClock(settings.demo_now) if settings.demo_now else SystemClock()
    if verifier is None and settings.auth_mode == "google":
        from app.adapters.outbound.google_auth import GoogleIdentityVerifier
        verifier = GoogleIdentityVerifier(settings.google_client_id)
    vision = build_vision(settings)
    ids = SeqIdGenerator()
    repo = InMemoryRepo() if settings.repo_mode == "memory" else _sql_repo(settings.db_url)
    use_cases = UseCases(
        repo, clock, ids, LocalFileStorage(settings.media_dir), verifier,
        auth_mode=settings.auth_mode, admin_emails=settings.admin_email_list,
        session_ttl_hours=settings.session_ttl_hours, anonymous_auth=settings.anonymous_auth,
        anonymous_ttl_days=settings.anonymous_ttl_days, vision=vision,
        osm=FileOsmSource(settings.osm_file), geocoder=build_geocoder(settings), osm_live=build_osm_live(settings),
        router=build_router(settings), recommender=build_recommender(settings),
    )
    seed_or_continue(use_cases)
    return use_cases


def seed_or_continue(use_cases: UseCases) -> None:
    """Empty database → seed; persisted data → keep it, continue id sequences.
    Several workers booting on an empty database: the first seed wins, the others take its data (F29)."""
    repo = use_cases.repo
    if repo.is_empty():
        use_cases.load_seed()
        try:
            repo.commit()
            return
        except StaleData:
            log.info("another worker seeded the database first → using its data")
    use_cases.sync(force=True)


def _sql_repo(url: str):
    from app.adapters.outbound.sql import SqlRepo
    return SqlRepo(url)
