"""v5.11 — Analyse de marché du comité : décomposition par facteurs, technique, social, rapport (sans réseau)."""
import numpy as np
import pandas as pd
import pytest

from utils import market_drivers as MD


@pytest.fixture(scope="module")
def px():
    rng = np.random.default_rng(5)
    n = 600
    idx = pd.bdate_range("2024-01-01", periods=n)
    d_rates = rng.normal(0, 0.05, n)                  # variations du 10 ans (points)
    r_vix = rng.normal(0, 0.05, n)
    r_usd = rng.normal(0, 0.004, n)
    r_oil = rng.normal(0, 0.02, n)
    r_cred = rng.normal(0, 0.002, n)
    d_rates[-5:] = 0.06                                # semaine de forte hausse des taux
    r_ndx = -0.08 * d_rates - 0.10 * r_vix + 0.3 * r_cred + rng.normal(0.0004, 0.006, n)
    cols = {"^NDX": 15000 * np.exp(np.cumsum(r_ndx)), "^TNX": 4 + np.cumsum(d_rates),
            "^VIX": 16 * np.exp(np.cumsum(r_vix) * 0.3), "DX-Y.NYB": 104 * np.exp(np.cumsum(r_usd)),
            "CL=F": 75 * np.exp(np.cumsum(r_oil)), "HYG": 78 * np.exp(np.cumsum(r_cred)), "IEF": np.full(n, 95.0),
            "^GSPC": 5000 * np.exp(np.cumsum(r_ndx * 0.8))}
    for i, t in enumerate(MD.SECTOR_ETFS):
        cols[t] = 100 * np.exp(np.cumsum(r_ndx * (0.5 + i / 10) + rng.normal(0, 0.004, n)))
    for t in MD.LEADERS["us"]:
        cols[t] = 200 * np.exp(np.cumsum(r_ndx * 1.2 + rng.normal(0, 0.01, n)))
    return pd.DataFrame(cols, index=idx)


def test_attribution_finds_rates(px):
    att = MD.attribution(px, "Nasdaq 100", 5)
    assert att["ok"] and att["move"] < 0
    assert att["factors"][0]["key"] == "rates" and att["factors"][0]["contrib"] < 0
    assert 0 < att["r2"] < 1
    assert att["explained"] + att["residual"] == pytest.approx(att["move"])


def test_full_analysis_and_pdf(px):
    news = [{"title": "Nasdaq falls as Treasury yields jump on hawkish Fed", "source": "x"},
            {"title": "Nvidia chip stocks slump", "source": "y"}]
    reddit = [{"sub": "stocks", "title": "Nasdaq crash, $NVDA down again, fear everywhere", "score": 500, "comments": 200},
              {"sub": "wallstreetbets", "title": "Buying the dip on QQQ", "score": 100, "comments": 50}]
    twits = [{"sentiment": "Bearish"}] * 7 + [{"sentiment": "Bullish"}] * 3
    rets = px[["AAPL", "MSFT"]].pct_change().dropna()
    pi = MD.portfolio_impact(rets, {"AAPL": 0.5, "MSFT": 0.3}, px["^NDX"].pct_change(), -0.03)
    assert pi["ok"] and pi["beta"] > 0.5
    an = MD.analyse("Nasdaq 100", 5, px, news, reddit, twits, "Stagflation", "Équilibré", pi)
    assert an["ok"] and "baisse" in an["headline"]
    assert an["why"] and an["impact"] and an["adapt"]
    assert {v["id"] for v in an["voices"]} == {"eco", "quant", "cio", "cro", "cpm"}
    assert an["social"]["stocktwits"]["bear"] == 7 and an["social"]["score"] < 0
    assert any("NVDA" == t for t, _ in an["social"]["mentions"])
    assert an["technique"]["ok"]
    pdf = MD.build_pdf(an, px, "Texte de test")
    assert pdf[:4] == b"%PDF"
    assert "Pourquoi" in MD.llm_prompt(an)


def test_needed_tickers():
    t = MD.needed_tickers("CAC 40")
    assert "^FCHI" in t and "EURUSD=X" in t and "MC.PA" in t
