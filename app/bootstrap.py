"""Composition root: settings → adapters → use cases."""
from app.adapters.outbound.files import LocalFileStorage
from app.adapters.outbound.osm_file import FileOsmSource
from app.adapters.outbound.vision_mock import FallbackVisionAnalyzer, MockVisionAnalyzer
from app.adapters.outbound.memory import FixedClock, InMemoryRepo, SeqIdGenerator, SystemClock
from app.application.ports import IdentityVerifier
from app.application.use_cases import UseCases
from app.config import Settings


def build_vision(settings: Settings):
    mock = MockVisionAnalyzer()
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
    use_cases = UseCases(
        InMemoryRepo(), clock, SeqIdGenerator(), LocalFileStorage(settings.media_dir), verifier,
        auth_mode=settings.auth_mode, admin_emails=settings.admin_email_list,
        session_ttl_hours=settings.session_ttl_hours, vision=vision,
        osm=FileOsmSource(settings.osm_file),
    )
    use_cases.load_seed()
    return use_cases
