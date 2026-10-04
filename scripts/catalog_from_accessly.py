"""F49: build data/krakow_catalog.json from the Accessly place catalogue (its main branch's accessly/data/places.json).

    uv run python scripts/catalog_from_accessly.py [ACCESSLY_PLACES_JSON] [OUT]
    default: ../../Yannie-draft-acihy/accessly/data/places.json → data/krakow_catalog.json

Then load it: POST /api/v1/admin/imports {"source": "catalog"} (admin; idempotent)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.domain.catalog import from_accessly  # noqa: E402

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "../../Yannie-draft-acihy/accessly/data/places.json")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "data/krakow_catalog.json")

raw = json.loads(SRC.read_text(encoding="utf-8"))
entries = from_accessly(raw["items"] if isinstance(raw, dict) else raw)
OUT.write_text(json.dumps(entries, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"{len(entries)} places ({sum(1 for e in entries if e['features'])} with facts) → {OUT}")
