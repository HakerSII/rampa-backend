"""Write docs/openapi.json from the running app definition.

    uv run python scripts/export_openapi.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("REPO_MODE", "memory")  # don't touch the real DB while exporting
sys.path.insert(0, str(ROOT))

from app.adapters.inbound.http.main import create_app  # noqa: E402
from app.config import Settings  # noqa: E402

OUT = ROOT / "docs" / "openapi.json"


def build_spec() -> dict:
    return create_app(Settings(repo_mode="memory", ai_mode="mock", media_dir=tempfile.mkdtemp())).openapi()


if __name__ == "__main__":
    OUT.write_text(json.dumps(build_spec(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
