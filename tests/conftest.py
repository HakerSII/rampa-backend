from datetime import datetime, timezone

import pytest

from app.adapters.outbound.memory import FixedClock, InMemoryRepo, SeqIdGenerator
from app.application.use_cases import UseCases
from app.domain.errors import Unauthorized
from app.domain.model import GoogleIdentity

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


class FakeStorage:
    def __init__(self):
        self.saved: dict[str, bytes] = {}

    async def save(self, chunks, name):
        data = b"".join([c async for c in chunks])
        self.saved[name] = data
        return f"mem/{name}", f"/media/{name}"


class FakeIdentityVerifier:
    """token → identity; unknown token → Unauthorized (no network)."""

    def __init__(self, identities: dict[str, GoogleIdentity] | None = None):
        self.identities = identities or {}

    async def verify(self, id_token: str) -> GoogleIdentity:
        if id_token not in self.identities:
            raise Unauthorized("invalid Google ID token")
        return self.identities[id_token]


def make_use_cases(auth_mode="demo", verifier=None, admin_emails=None, clock=None) -> UseCases:
    uc = UseCases(InMemoryRepo(), clock or FixedClock(NOW), SeqIdGenerator(), FakeStorage(),
                  verifier, auth_mode=auth_mode, admin_emails=admin_emails or [])
    uc.load_seed()
    return uc


@pytest.fixture
def uc() -> UseCases:
    return make_use_cases()
