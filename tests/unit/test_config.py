from app.config import Settings


def test_default_is_sqlite_file():
    s = Settings(_env_file=None, database_url="")
    assert (s.db_engine, s.db_url) == ("sqlite", "sqlite:///data/rampa.db")


def test_sqlite_path_is_configurable():
    assert Settings(_env_file=None, database_url="", sqlite_path="x/y.db").db_url == "sqlite:///x/y.db"


def test_postgres_url_built_from_parts_with_escaped_password():
    s = Settings(_env_file=None, database_url="", db_engine="postgres", postgres_host="db", postgres_port=5433,
                 postgres_user="rampa", postgres_password="p@ss:w/rd", postgres_db="rampa")
    assert s.db_url == "postgresql+psycopg://rampa:p%40ss%3Aw%2Frd@db:5433/rampa"


def test_database_url_override_wins():
    s = Settings(_env_file=None, db_engine="postgres", database_url="sqlite:///override.db")
    assert s.db_url == "sqlite:///override.db"


def test_db_choice_from_environment(monkeypatch):
    monkeypatch.setenv("DB_ENGINE", "postgres")
    monkeypatch.setenv("POSTGRES_HOST", "pg.example")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert Settings(_env_file=None).db_url == "postgresql+psycopg://rampa:rampa@pg.example:5432/rampa"
