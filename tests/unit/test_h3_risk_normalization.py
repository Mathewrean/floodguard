import math

from core.zoning.h3_intelligence import normalize_risk_score


def test_normalize_risk_score_accepts_fraction_and_legacy_percentages():
    assert normalize_risk_score(0.755) == 0.755
    assert normalize_risk_score(75.5) == 0.755
    assert normalize_risk_score(200) == 1.0


def test_normalize_risk_score_rejects_non_finite_values():
    assert normalize_risk_score(None) == 0.0
    assert normalize_risk_score(math.inf) == 0.0
