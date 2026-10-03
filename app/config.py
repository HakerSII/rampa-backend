from datetime import datetime
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration from env vars / .env (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    repo_mode: Literal["sql", "memory"] = "sql"
    database_url: str = "sqlite:///data/rampa.db"
    auth_mode: Literal["demo", "google"] = "demo"
    google_client_id: str = ""
    admin_emails: str = ""  # comma-separated
    media_dir: str = "media"
    demo_now: datetime | None = None  # set → FixedClock (deterministic demo)
    session_ttl_hours: int = 24
    ai_mode: Literal["mock", "onnx", "gemini"] = "mock"
    ai_model_path: str = "models/gpu/gpu-int4-rtn-block-32"
    ai_timeout_s: float = 60.0
    gemini_api_key: str = ""  # secret: only in .env (gitignored)
    gemini_model: str = "gemini-2.5-flash"
    gemini_api_url: str = "https://generativelanguage.googleapis.com/v1beta"
    osm_file: str = "data/osm_krakow_tauron.json"  # offline OSM snapshot
    public_api_keys: str = "demo-key"  # comma-separated X-Api-Key values for /public/v1
    public_rate_limit_per_min: int = 60

    @property
    def public_api_key_list(self) -> list[str]:
        return [k.strip() for k in self.public_api_keys.split(",") if k.strip()]

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]
