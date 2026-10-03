"""Composition root: settings → adapters → use cases."""
from app.adapters.outbound.files import LocalFileStorage
from app.adapters.outbound.memory import FixedClock, InMemoryRepo, SeqIdGenerator, SystemClock
from app.application.ports import IdentityVerifier
from app.application.use_cases import UseCases
from app.config import Settings


def build_use_cases(settings: Settings, verifier: IdentityVerifier | None = None) -> UseCases:
    clock = FixedClock(settings.demo_now) if settings.demo_now else SystemClock()
    if verifier is None and settings.auth_mode == "google":
        from app.adapters.outbound.google_auth import GoogleIdentityVerifier
        verifier = GoogleIdentityVerifier(settings.google_client_id)
    use_cases = UseCases(
        InMemoryRepo(), clock, SeqIdGenerator(), LocalFileStorage(settings.media_dir), verifier,
        auth_mode=settings.auth_mode, admin_emails=settings.admin_email_list,
        session_ttl_hours=settings.session_ttl_hours,
    )
    use_cases.load_seed()
    return use_cases
