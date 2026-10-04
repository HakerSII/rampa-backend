from app.domain.enums import FEATURE_GROUP, LABELS_PL, FeatureGroupKey, FeatureKey as F
from app.domain.text_parse import parse_text
from tests.application.test_observations import user


def test_full_model_features_and_groups():
    assert len(F) == 52 and F.ESCALATOR == "escalator"  # 35 (F25) + 4 (F32) + 13 (F53)
    assert FEATURE_GROUP[F.ESCALATOR] == FeatureGroupKey.INSIDE
    assert FEATURE_GROUP[F.DISABLED_PARKING] == FeatureGroupKey.PARKING
    assert LABELS_PL[F.ESCALATOR] == "Schody ruchome" and LABELS_PL[FeatureGroupKey.PARKING] == "Parking"
    assert "partially_inaccessible_exhibition" not in {f.value for f in F}  # inverted meaning, left out


async def test_new_features_work_end_to_end(uc):
    uc.add_observation(user(uc, "anna"), "plc_mnk", feature="escalator", value="no", temporary=True)
    uc.add_observation(user(uc, "anna"), "plc_ice", feature="disabled_parking", value="yes")
    states = uc.get_accessibility("plc_mnk")
    assert len(states) == 52 and states[F.ESCALATOR].state == "no"
    assert [p.id for p in uc.search_places(features=[F.DISABLED_PARKING])] == ["plc_ice"]


def test_escalator_text_is_not_stairs():
    assert [(s.feature, s.value) for s in parse_text("Schody ruchome nie działają")] == [(F.ESCALATOR, "no")]
    assert [(s.feature, s.value) for s in parse_text("escalator is broken")] == [(F.ESCALATOR, "no")]
