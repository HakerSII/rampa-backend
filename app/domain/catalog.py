"""F49: the Accessly place catalogue (its main branch's data/places.json: named OSM places with address, contact and
OSM accessibility tags) → Rampa catalogue entries (data/krakow_catalog.json, imported by POST /admin/imports
{"source": "catalog"}). Pure mapping; the keys follow Accessly's rampa.js (ATTR_TO_RAMPA, CATEGORY_TO_RAMPA)."""
from app.domain.city import load_city

ATTR_TO_RAMPA = {
    "step_free": "step_free_entrance", "ramp": "ramp", "elevator": "elevator", "door_width": "wide_doors",
    "spacious": "spacious_interior", "accessible_toilet": "accessible_toilet", "changing_table": "baby_changing_table",
    "hearing_loop": "induction_loop", "contrast_marking": "high_contrast_markings",
    "digital_materials": "accessible_digital_materials", "dogs": "pets_allowed",
    "assistance_dogs": "assistance_dog_allowed", "pram_space": "stroller_space", "luggage": "luggage_storage",
    "rest_area": "rest_areas", "disabled_parking": "disabled_parking",
}
VALUE_TO_RAMPA = {"yes": "yes", "no": "no", "partial": "partial", "na": "not_applicable"}
CATEGORY_TO_RAMPA = {"gastronomia": "restaurant", "kultura": "culture", "uslugi": "office", "zakupy": "shop",
                     "zdrowie": "clinic", "noclegi": "hotel", "inne": "other"}
# kinds the UI maps back to the same Accessly category (rampa.js UI_CATEGORY_GROUPS + the city's groups)
UI_KINDS = {"pharmacy", "clinic", "hospital", "doctors", "dentist", "hotel", "hostel", "guest_house", "apartment", "motel"}


def known_kinds() -> set[str]:
    city = load_city(None)
    return UI_KINDS | {k for g in city.category_groups.values() for k in g.categories}


def from_accessly(items: list[dict], kinds: set[str] | None = None) -> list[dict]:
    kinds = known_kinds() if kinds is None else kinds
    out = []
    for i in items:
        name = (i.get("name") or "").strip()
        if not name or i.get("lat") is None or i.get("lng") is None:
            continue
        kind = i.get("kind") or ""
        features = {ATTR_TO_RAMPA[a]: VALUE_TO_RAMPA[v] for a, v in (i.get("attributes") or {}).items()
                    if a in ATTR_TO_RAMPA and v in VALUE_TO_RAMPA}
        entry = {"ref": f"osm:{i['ref']}" if i.get("ref") else f"osm:{i['lat']:.6f},{i['lng']:.6f}", "name": name,
                 "category": kind if kind in kinds else CATEGORY_TO_RAMPA.get(i.get("category"), "other"),
                 "lat": float(i["lat"]), "lon": float(i["lng"])}
        for key in ("address", "phone", "website"):
            if i.get(key):
                entry[key] = str(i[key])
        if kind:
            entry["kind"] = kind  # OSM subtype (theme_park, cafe …): the card's label, the category stays for filters
        if i.get("openingHours"):
            entry["opening_hours"] = str(i["openingHours"])  # OSM opening_hours text
        entry["features"] = features
        out.append(entry)
    return out
