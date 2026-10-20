import numpy as np
import pandas as pd

from utils import advisor as A, calibration as C


def test_refuses_simulated_data(px10):
    assert not C.estimate_sensitivity(px10, list(px10.columns))["ok"]
    assert (C.calibrate_strategy_vols(px10, list(px10.columns))["source"] != "historique").all()
    assert not C.calibrate_alerts(px10, list(px10.columns))["ok"]


def test_sensitivity_estimation_shapes(px10):
    r = C.estimate_sensitivity(px10, [])
    assert r["ok"] and r["estimee"].shape == A.SENSITIVITY.shape
    assert r["estimee"]["geopolitique"].isna().all()           # pas d'historique d'actualité
    assert r["estimee"].abs().max().max() <= 1.0 + 1e-9


def test_blend_keeps_expert_where_not_estimated(px10):
    r = C.estimate_sensitivity(px10, [])
    m = C.blend(r["estimee"], 0.5)
    assert m["geopolitique"].equals(A.SENSITIVITY["geopolitique"])
    assert C.blend(r["estimee"], 0.0).equals(A.SENSITIVITY)


def test_factor_series_match_compute_macro(px10):
    F = C.market_factor_series(px10)
    news = {k: dict(label=v["label"], intensity=30.0) for k, v in A.NEWS_THEMES.items()}
    m = A.compute_macro(px10, news).factors
    for k in ("stress", "dollar"):
        assert abs(F[k].iloc[-1] - m[k]) < 1e-9


def test_alert_thresholds_ordered(px10):
    s = C.calibrate_alerts(px10, [])["seuils"]
    assert s["z_info"] < s["z_important"] < s["z_critique"]


def test_hedge_ratio_rule():
    c = dict(predictif=True, logit_a=-2.0, logit_b=1.0, frequence=0.12, seuil_reco=0.0)
    lo, _ = C.hedge_ratio_from_calibration(c, -2.0)
    hi, reco = C.hedge_ratio_from_calibration(c, 1.5)
    assert lo == 0.25 and 0.25 < hi <= 0.75 and reco
    assert C.hedge_ratio_from_calibration(dict(predictif=False), 2.0) == (0.25, False)


def test_without_calibration_engines_use_expert():
    C._CACHE.update(t=1e18, v={})          # aucune calibration active
    assert A.sensitivity().equals(A.SENSITIVITY)
    assert C.active_alert_thresholds() == C.EXPERT_ALERTS
    C.clear_cache()
