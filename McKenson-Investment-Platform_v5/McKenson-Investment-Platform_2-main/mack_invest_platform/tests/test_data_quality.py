import numpy as np
import pandas as pd

from utils import data_quality as DQ


def _px():
    idx = pd.bdate_range("2026-01-01", periods=300)
    rng = np.random.default_rng(2)
    return pd.DataFrame({t: 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx)))) for t in ("SPY", "TLT", "GLD", "HYG")},
                        index=idx)


def test_clean_data_ok():
    rep = DQ.run_checks(_px(), [], {"a": dict(label="A", count=3)}, False, ["SPY", "TLT", "GLD", "HYG"])
    assert rep["gravite_max"] <= 1


def test_detects_simulated_stale_jump_and_flat():
    px = _px()
    px.loc[px.index[-3], "GLD"] = px["GLD"].iloc[-4] * 2.0           # saut de +100 %
    px.loc[px.index[-8]:, "TLT"] = np.nan                            # cotation ancienne
    px.loc[px.index[-5]:, "HYG"] = px["HYG"].iloc[-6]                # cours figé
    rep = DQ.run_checks(px, ["SPY"], {}, True, ["SPY", "TLT", "GLD", "HYG"])
    probs = {(i["serie"], i["probleme"]) for i in rep["problemes"]}
    assert ("SPY", "Source indisponible (repli simulé)") in probs
    assert ("TLT", "Cotation ancienne") in probs
    assert ("GLD", "Saut suspect") in probs
    assert ("HYG", "Cours figé") in probs
    assert ("Actualité", "Veille simulée") in probs
    assert rep["statut"] == "PROBLÈME" and DQ.to_alert(rep)["gravite"] == "critique"
