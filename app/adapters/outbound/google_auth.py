"""Google ID token verification — the only network code in the MVP (AUTH_MODE=google only)."""
import asyncio

import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from app.domain.errors import Unauthorized
from app.domain.model import GoogleIdentity

GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GoogleIdentityVerifier:
    def __init__(self, client_id: str):
        if not client_id:
            raise ValueError("GOOGLE_CLIENT_ID is required when AUTH_MODE=google")
        self.client_id = client_id
        # one session for all calls → connection reuse for Google's public-key fetches
        self._request = Request(session=requests.Session())

    async def verify(self, token: str) -> GoogleIdentity:
        try:
            # sync + network → run off the event loop
            claims = await asyncio.to_thread(
                id_token.verify_oauth2_token, token, self._request, self.client_id, clock_skew_in_seconds=10
            )
        except ValueError as e:  # bad signature / audience / expiry / malformed
            raise Unauthorized(f"invalid Google ID token: {e}") from e
        if claims.get("iss") not in GOOGLE_ISSUERS:
            raise Unauthorized("invalid token issuer")
        return GoogleIdentity(
            sub=claims["sub"],
            email=claims.get("email", ""),
            email_verified=bool(claims.get("email_verified")),
            name=claims.get("name", ""),
        )
