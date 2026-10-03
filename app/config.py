from datetime import datetime
from typing import Literal
from urllib.parse import quote

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration from env vars / .env (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # storage: sql (SQLite or Postgres via SQLAlchemy) | memory
    repo_mode: Literal["sql", "memory"] = "sql"
    db_engine: Literal["sqlite", "postgres"] = "sqlite"
    sqlite_path: str = "data/rampa.db"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "rampa"
    postgres_password: str = "rampa"  # secret in real deployments: set in .env
    postgres_db: str = "rampa"
    database_url: str = ""  # optional override: any SQLAlchemy URL, wins over db_engine/*
    auth_mode: Literal["demo", "google"] = "demo"
    google_client_id: str = ""
    admin_emails: str = ""  # comma-separated
    anonymous_auth: bool = True  # POST /auth/anonymous: device identity for the map front end (any auth mode)
    anonymous_ttl_days: int = 365  # anonymous session lifetime; the device keeps its votes this long
    media_dir: str = "media"
    demo_now: datetime | None = None  # set → FixedClock (deterministic demo)
    session_ttl_hours: int = 24
    ai_mode: Literal["mock", "onnx", "gemini"] = "mock"
    ai_model_path: str = "models/gpu/gpu-int4-rtn-block-32"
    ai_timeout_s: float = 60.0
    gemini_api_key: str = ""  # secret: only in .env (gitignored)
    gemini_model: str = "gemini-3.8-flash"
    gemini_api_url: str = "https://generativelanguage.googleapis.com/v1beta"
    osm_file: str = "data/osm_krakow_tauron.json"  # offline OSM snapshot
    # F27 live OSM: geocoder for the search box; Overpass for POST /admin/imports {"source": "overpass"}
    geocoder: Literal["local", "nominatim"] = "local"
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    osm_center_lat: float = 50.0647  # Rynek Główny
    osm_center_lon: float = 19.9450
    osm_radius_m: int = 1500
    external_timeout_s: float = 10.0
    http_user_agent: str = "RampaKrakowBezBarier/0.1 (HackYeah 2026)"  # OSM usage policy: identify the app
    public_api_keys: str = "demo-key"  # comma-separated X-Api-Key values for /public/v1
    public_rate_limit_per_min: int = 60

    @field_validator("demo_now", mode="before")
    @classmethod
    def _empty_is_none(cls, v):
        return None if v == "" else v  # "DEMO_NOW=" in .env / compose = not set

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.db_engine == "postgres":
            user, pwd = quote(self.postgres_user, safe=""), quote(self.postgres_password, safe="")
            return f"postgresql+psycopg://{user}:{pwd}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        return f"sqlite:///{self.sqlite_path}"

    @property
    def db_dialect(self) -> str:
        return self.db_url.split(":", 1)[0].split("+", 1)[0]  # sqlite | postgresql (no credentials)

    @property
    def public_api_key_list(self) -> list[str]:
        return [k.strip() for k in self.public_api_keys.split(",") if k.strip()]

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]
