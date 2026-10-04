"""F53: the features of the Accessly main branch catalogue (hotel rooms, opening hours, languages, quiet) and its two
report types (information sign, other barrier) exist in Rampa, so the app's forms match main."""
import pytest

from app.domain.catalog import from_accessly
from app.domain.enums import FEATURE_GROUP, LABELS_PL, FeatureKey as F
from tests.application.test_observations import user

NEW = {
    "quiet_space": "Ciche miejsce",
    "accessible_room": "Pokój dostosowany dla osób z niepełnosprawnościami",
    "roll_in_shower": "Prysznic bez progu",
    "grab_bars": "Uchwyty w łazience",
    "reception_24h": "Recepcja całodobowa",
    "medical_equipment_allowed": "Można przywieźć sprzęt medyczny (wózek, balkonik)",
    "kitchenette": "Aneks kuchenny",
    "open_24h": "Czynne całą dobę",
    "staff_english": "Obsługa po angielsku",
    "staff_german": "Obsługa po niemiecku",
    "staff_ukrainian": "Obsługa po ukraińsku",
    "information_sign": "Tablica, komunikat",
    "other_barrier": "Inna bariera",
}


@pytest.mark.parametrize("key, label", NEW.items())
def test_feature_exists_with_label_and_group(key, label):
    f = F(key)
    assert LABELS_PL[f] == label and f in FEATURE_GROUP


def test_count():
    assert len(F) == 52  # 39 + 13 (F53)


def test_observations_on_new_features(uc):
    uc.add_observation(user(uc, "anna"), "plc_mnk", feature="open_24h", value="yes")
    uc.add_observation(user(uc, "anna"), "plc_mnk", feature="information_sign", value="no", temporary=True)
    states = uc.get_accessibility("plc_mnk")
    assert states[F.OPEN_24H].state == "yes" and states[F.INFORMATION_SIGN].state == "no"


def test_catalogue_brings_the_new_facts():
    e = from_accessly([{"ref": "node/1", "name": "Hotel", "category": "noclegi", "kind": "hotel", "lat": 50.0, "lng": 19.9,
                        "attributes": {"reception_24h": "yes", "open_24h": "yes", "lang_en": "yes", "quiet": "no",
                                       "accessible_room": "yes", "roll_in_shower": "na", "grab_bars": "yes",
                                       "medical_equipment": "yes", "kitchenette": "no", "lang_de": "yes", "lang_uk": "no"}}])
    assert e[0]["features"] == {"reception_24h": "yes", "open_24h": "yes", "staff_english": "yes", "quiet_space": "no",
                                "accessible_room": "yes", "roll_in_shower": "not_applicable", "grab_bars": "yes",
                                "medical_equipment_allowed": "yes", "kitchenette": "no", "staff_german": "yes",
                                "staff_ukrainian": "no"}


def test_report_with_the_new_types(uc):
    r = uc.create_report(user(uc, "anna"), place_id="plc_mnk", element="information_sign", current_state="not_working",
                         severity="obstacle", nature="temporary", description="Tablica nie działa.")
    assert r.element == F.INFORMATION_SIGN
