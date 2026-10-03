"""Entry point. The HTTP app itself is an inbound adapter: app/adapters/inbound/http/main.py.

    uv run python main.py            # http://localhost:8000/docs
    uv run uvicorn main:app --reload
"""
import uvicorn

from app.adapters.inbound.http.main import app

__all__ = ["app"]

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
