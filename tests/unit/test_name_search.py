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
    ("teatru na slowackiego", "Teatr im. Juliusza Słowackiego"),  # linking words are ignored
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


@pytest.mark.parametrize("query, expected", [
    ("Tauron Areny", "Tauron Arena"),
    ("Teatru Bagatela", "Teatr Bagatela"),
    ("Opery Krakowskiej", "Opera Krakowska"),
    ("ulicy Lea 120", "Lea 120"),
    ("Galerii Krakowskiej", "Galeria Krakowska"),
    ("Wawel", "Wawel"),
])
def test_nominative_variant_for_the_geocoder(query, expected):
    from app.domain.text import nominative
    assert nominative(query) == expected


async def test_geocode_retries_with_the_nominative():
    from app.domain.model import GeocodeHit, GeoPoint
    from tests.conftest import make_use_cases

    class Geo:
        def __init__(self):
            self.queries = []

        async def search(self, q):
            self.queries.append(q)
            return [GeocodeHit("TAURON Arena Kraków, Lema 7", None, GeoPoint(50.0679, 19.9914))] if q == "Tauron Arena" else []

    geo = Geo()
    uc = make_use_cases(geocoder=geo)
    hits = await uc.geocode_live("Tauron Areny")
    assert geo.queries == ["Tauron Areny", "Tauron Arena"] and hits[0].label.startswith("TAURON Arena")


async def test_an_address_next_to_a_known_place_is_still_found():
    """F51: a geocoder hit is dropped only as a duplicate of a listed local hit, not of any place nearby."""
    from app.domain.model import GeocodeHit, GeoPoint
    from tests.conftest import make_use_cases

    class Geo:
        async def search(self, q):
            return [GeocodeHit("3 Maja 1, Kraków", None, GeoPoint(50.0603, 19.9239))]  # next to plc_mnk

    uc = make_use_cases(geocoder=Geo())
    hits = await uc.geocode_live("3 Maja 1")
    assert [h.label for h in hits] == ["3 Maja 1, Kraków"]
