"""F49: build data/krakow_catalog.json from the Accessly place catalogue (its main branch's accessly/data/places.json).

    uv run python scripts/catalog_from_accessly.py [ACCESSLY_PLACES_JSON] [OUT]
    default: ../../Yannie-draft-acihy/accessly/data/places.json → data/krakow_catalog.json
City disabled-parking spaces (parking.json next to places.json) within 100 m add "disabled_parking": yes, as on main.

Then load it: POST /api/v1/admin/imports {"source": "catalog"} (admin; idempotent)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.domain.catalog import add_city_parking, from_accessly  # noqa: E402

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "../../Yannie-draft-acihy/accessly/data/places.json")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "data/krakow_catalog.json")

raw = json.loads(SRC.read_text(encoding="utf-8"))
entries = from_accessly(raw["items"] if isinstance(raw, dict) else raw)
parking_file = SRC.with_name("parking.json")
parking = json.loads(parking_file.read_text(encoding="utf-8"))["items"] if parking_file.exists() else []
print(f"city disabled parking within 100 m: {add_city_parking(entries, parking)} places ({len(parking)} spaces)")
OUT.write_text(json.dumps(entries, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"{len(entries)} places ({sum(1 for e in entries if e['features'])} with facts) -> {OUT}")
