"""Static checks of the container setup (no Docker daemon needed)."""
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]


def test_compose_has_postgres_and_api_wired_by_env():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    db, api = compose["services"]["db"], compose["services"]["api"]
    assert db["image"].startswith("postgres:") and "healthcheck" in db
    assert api["depends_on"]["db"]["condition"] == "service_healthy"
    env = api["environment"]
    assert (env["REPO_MODE"], env["DB_ENGINE"], env["POSTGRES_HOST"]) == ("sql", "postgres", "db")
    assert "GEMINI_API_KEY" in env and "AI_MODE" in env


def test_secrets_never_baked_into_image():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    assert {".env", ".venv", "models/", "data/*.db"} <= set(ignored)
    assert "COPY .env" not in (ROOT / "Dockerfile").read_text(encoding="utf-8")
