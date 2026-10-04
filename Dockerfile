# rampa-backend — FastAPI + Postgres-ready image (see docker-compose.yml)
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# dependencies first (cached layer); postgres extra = psycopg driver; ai extra = onnxruntime-genai + huggingface_hub
# (the local model itself is downloaded at start when a setting uses it, F48 — not baked into the image)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra postgres --extra ai --no-install-project

# app code (.env, .venv, models/, media/, *.db excluded by .dockerignore)
COPY . .

ENV PATH="/app/.venv/bin:$PATH" \
    REPO_MODE=sql \
    DB_ENGINE=postgres

EXPOSE 8000
# single worker: SqlRepo is a write-behind cache (single process)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
