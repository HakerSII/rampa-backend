"""Composition root: settings → adapters → use cases."""
import logging

from app.adapters.outbound.files import LocalFileStorage
from app.adapters.outbound.osm_file import FileOsmSource
from app.adapters.outbound.vision_mock import FallbackVisionAnalyzer, MockVisionAnalyzer
from app.adapters.outbound.memory import FixedClock, InMemoryRepo, SeqIdGenerator, SystemClock
from app.application.ports import IdentityVerifier, StaleData
from app.application.use_cases import UseCases
from app.config import Settings
from app.domain.city import City, load_city


log = logging.getLogger(__name__)


def build_vision(settings: Settings):
    mock = MockVisionAnalyzer()
    if settings.ai_mode == "gemini":
        from app.adapters.outbound.vision_gemini import GeminiVisionAnalyzer
        if not settings.gemini_api_key:
            log.warning("AI_MODE=gemini but GEMINI_API_KEY is empty → every call falls back to mock")
        gemini = GeminiVisionAnalyzer(settings.gemini_api_key, settings.gemini_model, settings.gemini_api_url,
                                      timeout_s=settings.ai_timeout_s)
        return FallbackVisionAnalyzer(gemini, _gemini_fallback(settings, mock), settings.ai_timeout_s)
    if settings.ai_mode == "onnx":
        from app.adapters.outbound.vision_onnx import OnnxPhiVisionAnalyzer
        return FallbackVisionAnalyzer(OnnxPhiVisionAnalyzer(settings.ai_model_path), mock, settings.ai_timeout_s)
    return mock


def _gemini_fallback(settings: Settings, mock):
    """F44: Gemini failed → local ONNX model when it can run here, else mock."""
    if settings.ai_vision_fallback != "onnx":
        return mock
    from app.adapters.outbound import vision_onnx
    if not vision_onnx.onnx_available(settings.ai_model_path):
        log.warning("AI_VISION_FALLBACK=onnx but onnxruntime-genai or model %s is missing → mock",
                    settings.ai_model_path)
        return mock
    return FallbackVisionAnalyzer(vision_onnx.OnnxPhiVisionAnalyzer(settings.ai_model_path), mock,
                                  settings.ai_onnx_timeout_s)


def build_onnx_text_model(settings: Settings, timeout_s: float | None = None):
    """Local Phi-3.5 for text (chat F46, recommender F47); the weights are loaded once per folder (phi_onnx)."""
    from app.adapters.outbound.chat_onnx import OnnxPhiChatModel
    return OnnxPhiChatModel(settings.chat_model_path or settings.ai_model_path, timeout_s or settings.chat_timeout_s)


def build_chat_model(settings: Settings):
    """F46: None = rules answers (CHAT_MODE=rules|off); onnx → local Phi-3.5 (loading starts in create_app)."""
    return build_onnx_text_model(settings) if settings.chat_mode == "onnx" else None


def build_geocoder(settings: Settings, city: City):
    if settings.geocoder != "nominatim":
        return None
    from app.adapters.outbound.osm_live import NominatimGeocoder
    return NominatimGeocoder(settings.nominatim_url, settings.http_user_agent, timeout_s=settings.external_timeout_s,
                             viewbox=city.viewbox_param)


def build_mailer(settings: Settings):
    from app.adapters.outbound.mailer import ConsoleMailer, SmtpMailer
    if settings.mailer == "smtp":
        return SmtpMailer(settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password,
                          settings.mail_from)
    return ConsoleMailer()


def build_recommender(settings: Settings, city: City):
    if settings.ai_recommender == "onnx":  # F47: local Phi-3.5, weights shared with chat / photo analysis
        from app.adapters.outbound.recommender_onnx import OnnxQueryInterpreter
        llm = build_onnx_text_model(settings, settings.ai_timeout_s)  # /ai/recommend is not streamed: shorter wait
        if settings.chat_preload:
            llm.start_loading()
        return OnnxQueryInterpreter(llm, city)
    if settings.ai_recommender == "gemini":
        if not settings.gemini_api_key:
            log.warning("AI_RECOMMENDER=gemini but GEMINI_API_KEY is empty → rules")
            return None
        from app.adapters.outbound.recommender_gemini import GeminiQueryInterpreter
        return GeminiQueryInterpreter(settings.gemini_api_key, settings.gemini_model, settings.gemini_api_url,
                                      timeout_s=settings.ai_timeout_s, city=city)
    if settings.ai_recommender != "claude":
        return None
    if not settings.anthropic_api_key:
        log.warning("AI_RECOMMENDER=claude but ANTHROPIC_API_KEY is empty → rules")
        return None
    from app.adapters.outbound.recommender_claude import ClaudeQueryInterpreter
    return ClaudeQueryInterpreter(settings.anthropic_api_key, settings.claude_model, timeout_s=settings.ai_timeout_s,
                                  city=city)


def build_router(settings: Settings):
    if settings.router != "osrm":
        return None
    from app.adapters.outbound.osrm import OsrmRouter
    return OsrmRouter(settings.osrm_url, settings.http_user_agent, timeout_s=settings.external_timeout_s)


def build_osm_live(settings: Settings, city: City):
    """Only used on explicit admin import {"source": "overpass"}; falls back to the snapshot."""
    from app.adapters.outbound.osm_live import FallbackOsmSource, OverpassOsmSource
    lat = settings.osm_center_lat if settings.osm_center_lat is not None else city.center.lat
    lon = settings.osm_center_lon if settings.osm_center_lon is not None else city.center.lon
    live = OverpassOsmSource(settings.overpass_url, lat, lon, settings.osm_radius_m or city.osm_radius_m,
                             settings.http_user_agent, timeout_s=max(settings.external_timeout_s, 25))
    return FallbackOsmSource(live, FileOsmSource(settings.osm_file))


def build_use_cases(settings: Settings, verifier: IdentityVerifier | None = None) -> UseCases:
    clock = FixedClock(settings.demo_now) if settings.demo_now else SystemClock()
    if verifier is None and settings.auth_mode == "google":
        from app.adapters.outbound.google_auth import GoogleIdentityVerifier
        verifier = GoogleIdentityVerifier(settings.google_client_id)
    vision = build_vision(settings)
    city = load_city(settings.city_config or None)  # F37: invalid file → error at start
    ids = SeqIdGenerator()
    repo = InMemoryRepo() if settings.repo_mode == "memory" else _sql_repo(settings.db_url)
    use_cases = UseCases(
        repo, clock, ids, LocalFileStorage(settings.media_dir), verifier,
        auth_mode=settings.auth_mode, admin_emails=settings.admin_email_list,
        session_ttl_hours=settings.session_ttl_hours, anonymous_auth=settings.anonymous_auth,
        anonymous_ttl_days=settings.anonymous_ttl_days, vision=vision,
        osm=FileOsmSource(settings.osm_file), geocoder=build_geocoder(settings, city), osm_live=build_osm_live(settings, city),
        router=build_router(settings), recommender=build_recommender(settings, city), city=city,
        mailer=build_mailer(settings), email_login=settings.email_login,
        email_dev_token=settings.auth_mode == "demo" and settings.mailer == "console",
        email_link_url=settings.email_link_url,
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
