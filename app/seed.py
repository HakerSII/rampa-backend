"""Deterministic demo data. Initial observations are 60 days old, i.e. outside
the 30-day conflict window, so the first fresh report never conflicts with seed."""
from dataclasses import replace
from datetime import timedelta

from app.application.ports import Clock, IdGenerator, Repo
from app.domain.enums import FeatureKey as F, ObservationSource, ObservationValue, Role
from app.domain.model import GeoPoint, Observation, Place, User

SEED_AUTHOR_ID = "usr_seed"
OSM_AUTHOR_ID = "usr_osm"

DEMO_USERS = [
    ("anna", "Anna Kowalska", Role.USER),
    ("jan", "Jan Nowak", Role.USER),
    ("ola", "Ola Wiśniewska", Role.USER),
    ("piotr", "Piotr Zieliński", Role.USER),
    ("marek", "Marek Kowalski", Role.USER),
    ("ewa", "Ewa Nowak", Role.OWNER),  # owner of OWNED_BY_EWA
    ("admin", "Administrator", Role.ADMIN),
]

OWNED_BY_EWA = {"plc_mnk", "plc_camelot"}

PLACES = [
    (Place("plc_mnk", "Muzeum Narodowe w Krakowie", "museum", GeoPoint(50.0603, 19.9238),
           "Gmach Główny przy al. 3 Maja, dostosowany do potrzeb osób z niepełnosprawnościami.",
           "al. 3 Maja 1, 30-062 Kraków"),
     {F.STEP_FREE_ENTRANCE: "yes", F.RAMP: "yes", F.ELEVATOR: "yes",
      F.ACCESSIBLE_TOILET: "yes", F.INDUCTION_LOOP: "yes"}),
    (Place("plc_camelot", "Cafe Camelot", "cafe", GeoPoint(50.0628, 19.9383),
           "Kawiarnia na Starym Mieście.", "ul. Św. Tomasza 17, Kraków"),
     {F.RAMP: "yes"}),
    (Place("plc_ice", "Centrum Kongresowe ICE Kraków", "culture", GeoPoint(50.0472, 19.9286),
           "Centrum kongresowe nad Wisłą.", "ul. Marii Konopnickiej 17, Kraków"),
     {F.STEP_FREE_ENTRANCE: "yes", F.ELEVATOR: "no"}),
    (Place("plc_urzad", "Urząd Dzielnicy I", "office", GeoPoint(50.0650, 19.9450),
           "Urząd dzielnicy.", "Kraków"),
     {F.STEP_FREE_ENTRANCE: "no", F.RAMP: "no", F.INDUCTION_LOOP: "yes"}),
]


def load_seed(repo: Repo, clock: Clock, ids: IdGenerator, recompute) -> None:
    """recompute(place_id, feature) — use case hook, so states are always computed."""
    repo.add_user(User(SEED_AUTHOR_ID, "Dane startowe", Role.USER))
    repo.add_user(User(OSM_AUTHOR_ID, "OpenStreetMap", Role.USER))  # system author of open_data
    for username, name, role in DEMO_USERS:
        repo.add_user(User(f"usr_{username}", name, role, username=username))

    created = clock.now() - timedelta(days=60)
    for template, features in PLACES:
        place = replace(template, owner_id="usr_ewa" if template.id in OWNED_BY_EWA else None)  # copy: no shared state
        repo.add_place(place)
        for feature, value in features.items():
            repo.add_observation(Observation(
                id=ids.new("obs"), place_id=place.id, feature=feature,
                value=ObservationValue(value), source=ObservationSource.COMMUNITY,
                author_id=SEED_AUTHOR_ID, created_at=created,
            ))
            recompute(place.id, feature)
