"""Place search by name: no diacritics needed, Polish inflection tolerated (chat + search box)."""
import pytest

from app.domain.text import fold, name_matches


def test_fold():
    assert fold("Pływalnia ŻÓŁĆ Śląska") == "plywalnia zolc slaska"


@pytest.mark.parametrize("query, name", [
    ("Teatru Słowackiego", "Teatr im. Juliusza Słowackiego"),
    ("teatr slowackiego", "Teatr im. Juliusza Słowackiego"),
    ("plywalnia akf", "Pływalnia AKF"),
    ("Muzeum Narodowego", "Muzeum Narodowe w Krakowie"),
    ("camelot", "Cafe Camelot"),
    ("amelot", "Cafe Camelot"),  # a plain fragment still works
])
def test_matches(query, name):
    assert name_matches(query, name)


@pytest.mark.parametrize("query, name", [
    ("jakie miejsca znasz", "Teatr im. Juliusza Słowackiego"),
    ("plywalnia awf", "Pływalnia AKF"),
    ("teatr bagatela", "Teatr im. Juliusza Słowackiego"),
])
def test_no_match(query, name):
    assert not name_matches(query, name)


def test_search_places_uses_it():
    from tests.conftest import make_use_cases
    uc = make_use_cases()
    assert [p.id for p in uc.search_places(q="muzeum narodowego")] == ["plc_mnk"]
