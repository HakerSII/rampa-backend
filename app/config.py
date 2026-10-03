from datetime import datetime
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration from env vars / .env (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    auth_mode: Literal["demo", "google"] = "demo"
    google_client_id: str = ""
    admin_emails: str = ""  # comma-separated
    media_dir: str = "media"
    demo_now: datetime | None = None  # set → FixedClock (deterministic demo)
    session_ttl_hours: int = 24

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]
