import pytest

from app.domain.enums import FeatureKey as F, ObservationValue as V
from app.domain.geo import haversine_m
from app.domain.model import GeoPoint
from app.domain.osm import OsmPoint, map_category, map_features


def point(wheelchair="yes", toilet="brak danych", category="cafe"):
    return OsmPoint("X", wheelchair, toilet, category, 50.0, 19.9)


@pytest.mark.parametrize("wheelchair, expected", [
    ("yes", [(F.STEP_FREE_ENTRANCE, V.YES)]),
    ("no", [(F.STEP_FREE_ENTRANCE, V.NO)]),
    ("limited", []),           # no partial in MVP
    ("brak informacji", []),
])
def test_wheelchair_tag(wheelchair, expected):
    assert map_features(point(wheelchair=wheelchair)) == expected


def test_toilet_tag():
    assert map_features(point(wheelchair="limited", toilet="yes")) == [(F.ACCESSIBLE_TOILET, V.YES)]
    assert map_features(point(wheelchair="limited", toilet="no")) == [(F.ACCESSIBLE_TOILET, V.NO)]


def test_category():
    assert map_category("inne") == "other"
    assert map_category("cafe") == "cafe"


def test_haversine():
    mnk, rynek = GeoPoint(50.0603, 19.9238), GeoPoint(50.0617, 19.9373)
    assert 950 < haversine_m(mnk, rynek) < 1000
    assert haversine_m(mnk, mnk) == 0
