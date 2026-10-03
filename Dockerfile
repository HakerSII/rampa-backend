# rampa-backend — FastAPI + Postgres-ready image (see docker-compose.yml)
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# dependencies first (cached layer); postgres extra = psycopg driver
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra postgres --no-install-project

# app code (.env, .venv, models/, media/, *.db excluded by .dockerignore)
COPY . .

ENV PATH="/app/.venv/bin:$PATH" \
    REPO_MODE=sql \
    DB_ENGINE=postgres

EXPOSE 8000
# single worker: SqlRepo is a write-behind cache (single process)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
