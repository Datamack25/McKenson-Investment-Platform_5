"""v5.6 — discipline de gestion, synthèse en langage simple, propositions du comité (sans réseau ni base)."""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from utils import advisor as A
from utils import committee as CM
from utils import compliance as CP
from utils import line_risk as LR
from utils import plain_summary as PS
from utils import themes as TH

LIVE = dict(price_source="live")


class _Macro:
    factors = dict(croissance=0, inflation=0, monetaire=0, credit=0, stress=0, dollar=0, geopolitique=0, energie=0)
    regime, regime_text, indicators = "Expansion désinflationniste", "", {}


@pytest.fixture(scope="module")
def ctx():
    px = A._simulated_prices(list(A.ALL_TICKERS), n=600, seed=3)
    return dict(macro=_Macro(), cov=A.class_covariance(px), data_sim=False)


@pytest.fixture
def synthetic():
    idx = pd.bdate_range("2026-06-01", "2026-10-28")
    rng = np.random.default_rng(1)
    px = pd.DataFrame({"AAPL": 100 * np.cumprod(1 + rng.normal(.001, .01, len(idx))),
                       "TSLA": 200 * np.cumprod(1 + rng.normal(-.002, .02, len(idx))),
                       "SPY": 400 * np.cumprod(1 + rng.normal(.0008, .008, len(idx)))}, index=idx)
    port = {"id": "PS", "name": "Synth", "initial_cash": 100_000.0, "cash": 0.0, "holdings": {}, "options": [],
            "trades": [
                {"date": "2026-06-01 10:00", "ticker": "AAPL", "action": "BUY", "qty": 300, "price": float(px.AAPL.iloc[0]),
                 "total": 300 * float(px.AAPL.iloc[0]), "source": "Trading Desk",
                 "these": {"pourquoi": "Résultats solides et marges en hausse", "risques": "Valorisation élevée",
                           "horizon": "3 à 12 mois", "date": "2026-06-01 09:59:00"}},
                {"date": "2026-06-01 10:00", "ticker": "TSLA", "action": "BUY", "qty": 150, "price": float(px.TSLA.iloc[0]),
                 "total": 150 * float(px.TSLA.iloc[0]), "source": "Hedge Fund Agent"},
                {"date": "2026-08-03 10:00", "ticker": "AAPL", "action": "SELL", "qty": 100,
                 "price": float(px.AAPL.loc["2026-08-03"]), "total": 0, "source": "Trading Desk"}]}
    from utils import performance as PF
    return port, px, PF.nav_detail(port, px)


# ── Thèmes ────────────────────────────────────────────────────────────────────
def test_theme_exposure_flags_common_driver():
    th = TH.theme_exposure({"NEE": 20, "ETN": 15, "TSM": 15, "SPY": 50}, 100)
    ai = next(t for t in th if t["theme"].startswith("Infrastructure de l'IA"))
    assert abs(ai["poids"] - 0.50) < 1e-9 and ai["alerte"] and ai["n_segments"] == 3
    assert TH.ticker_themes("NVDA") and not TH.ticker_themes("SPY")


def test_new_theme_assets_are_tradeable():
    assets = pd.read_csv("data/assets.csv")
    for t in ("ETN", "VRT", "SU.PA", "CEG", "FCX", "NUE", "TSM", "AMAT"):
        assert t in set(assets["ticker"])


# ── Thèse et fiches de risques ───────────────────────────────────────────────
def test_thesis_is_mandatory():
    ok, missing = LR.validate_thesis({"pourquoi": "court", "risques": "", "horizon": "x"})
    assert not ok and len(missing) == 3
    ok, _ = LR.validate_thesis({"pourquoi": "Croissance des commandes de transformateurs",
                                "risques": "Ralentissement des centres de données", "horizon": "1 à 3 mois"})
    assert ok


def test_risk_sheet_status():
    port = {"holdings": {"JPM": {"qty": 1}, "SPY": {"qty": 1}}}
    st_ = LR.sheets_status(port)
    assert st_["lignes"] == ["JPM"] and st_["manquantes"] == ["JPM"]
    sh = LR.blank_sheet("JPM")
    assert "taux" in sh["risques"]                      # banque : risque de taux pré-sélectionné
    sh["risques"]["taux"] = dict(niveau="Élevé", couverture="Non couvert", note="")
    LR.save_sheet(port, "JPM", sh)
    st_ = LR.sheets_status(port)
    assert not st_["manquantes"] and st_["alertes"] == ["JPM"]


# ── Dérogations de concentration ─────────────────────────────────────────────
JUST = "Position tactique avant la publication des résultats, ramenée sous le plafond la semaine prochaine"


def test_derogation_turns_c04_block_into_warning(port_basic):
    port_basic["ips"] = CM.default_ips("Prudent")           # plafond par ligne : 10 %
    prices = {"SPY": 500.0, "TLT": 90.0, "JPM": 200.0}
    d = CP.pre_trade_spot(port_basic, "JPM", "BUY", 60, 200.0, prices=prices, category="Equity", **LIVE)
    assert "C04" in [c.code for c in d.blocks]
    assert not CP.request_derogation(port_basic, "JPM", 0.14, 3, "trop court", category="Equity")[0]
    assert not CP.request_derogation(port_basic, "JPM", 0.14, 10, JUST, category="Equity")[0]   # > 7 jours
    assert not CP.request_derogation(port_basic, "JPM", 0.30, 3, JUST, category="Equity")[0]   # > plafond + 50 %
    ok, msg = CP.request_derogation(port_basic, "JPM", 0.14, 3, JUST, category="Equity")
    assert ok, msg
    d = CP.pre_trade_spot(port_basic, "JPM", "BUY", 60, 200.0, prices=prices, category="Equity", **LIVE)
    assert "C04" not in [c.code for c in d.blocks] and "C04" in [c.code for c in d.warnings]
    d = CP.pre_trade_spot(port_basic, "JPM", "BUY", 80, 200.0, prices=prices, category="Equity", **LIVE)
    assert "C04" in [c.code for c in d.blocks]                # au-delà du poids autorisé par la dérogation


def test_expired_derogation_is_reported(port_basic):
    port_basic["ips"] = CM.default_ips("Prudent")
    past = datetime.now() - timedelta(days=10)
    ok, _ = CP.request_derogation(port_basic, "JPM", 0.14, 2, JUST, category="Equity", now=past)
    assert ok
    assert CP.active_derogation(port_basic, "JPM") is None
    assert CP.derogation_status(port_basic, {"JPM": 0.13})[0]["etat"].startswith("échue")
    assert CP.derogation_status(port_basic, {"JPM": 0.05})[0]["etat"] == "régularisée"


# ── Synthèse en langage simple ───────────────────────────────────────────────
def test_contributions_add_up_to_performance(synthetic):
    port, px, det = synthetic
    lc = PS.line_contributions(port, det=det)
    assert abs(lc["lignes"]["contribution"].sum() - lc["perf"]) < 1e-9


def test_plain_summary_names_cause_and_strategy(synthetic):
    port, px, det = synthetic
    s = PS.plain_summary(port, det=det, bench=px["SPY"])
    assert s["verdict"] in ("mieux", "moins bien", "pareil")
    txt = " ".join(s["phrases"])
    assert "En une phrase" in s["phrases"][0] and "Par façon d'investir" in txt and "point" in txt
    assert set(s["par_strategie"].index) == {"Décisions manuelles (Trading Desk)", "Allocation du desk (Hedge Fund Agent)"}


def test_plain_summary_new_portfolio():
    s = PS.plain_summary({"name": "Vide", "trades": [], "options": []})
    assert not s["ok"] and "trop récent" in s["phrases"][0]


def test_summary_from_values(synthetic):
    _, px, _ = synthetic
    s = PS.plain_summary_from_values({"AAPL": 30_000, "TSLA": 20_000}, 50_000, px[["AAPL", "TSLA"]], px["SPY"])
    assert s["ok"] and s["hypothetique"] and any("simulation" in p for p in s["phrases"])


# ── Comité : thèmes, discipline, propositions après création ─────────────────
def test_review_reports_themes_and_discipline(ctx):
    tick = ["NEE", "ETN", "TSM", "FCX", "XOM", "SPY"]
    R = A._simulated_prices(tick, n=600, seed=5).pct_change().iloc[1:]
    vals = {"NEE": 15000, "ETN": 12000, "TSM": 12000, "FCX": 8000, "XOM": 5000, "SPY": 20000}
    port = {"name": "T", "holdings": {t: {"qty": 1, "avg_price": v} for t, v in vals.items()}, "cash": 28000,
            "trades": [{"date": "2026-10-01", "ticker": "NEE", "action": "BUY", "qty": 1, "price": 1, "total": 1,
                        "source": "Trading Desk"}]}
    rev = CM.review_portfolio(vals, 28000, CM.default_ips("Dynamique"), ctx, R=R, port=port, label="T")
    cio = next(a for a in rev["avis"] if a["id"] == "cio")
    cpm = next(a for a in rev["avis"] if a["id"] == "cpm")
    assert rev["themes"] and any("Infrastructure de l'IA" in p for p in cio["points"])
    assert any("Fiches de risques" in p for p in cpm["points"])


def test_improvement_proposals_for_new_portfolio(ctx, monkeypatch):
    uni = sorted(set(A.CLASS_PROXY.values()) | set(CM.UCITS_PROXY.values()))
    R = A._simulated_prices(uni, n=600, seed=9).pct_change().iloc[1:]
    monkeypatch.setattr(CM, "line_returns", lambda tickers, years=2.2: R[sorted({t for t in tickers if t in R.columns})])
    live = {t: (100.0, 0) for t in uni}
    opt = CM.committee_optimize({}, 100_000, CM.default_ips("Équilibré"), ctx, live)
    props = CM.improvement_proposals(opt, {}, 100_000)
    assert props and all(p["action"] == "BUY" and p["pourquoi"] for p in props)
    btc = [p for p in props if p["ticker"] == "BTC-USD"]
    assert not btc or "ETF" not in btc[0]["pourquoi"]


# ── Rapports ─────────────────────────────────────────────────────────────────
def test_investor_report_pdf(synthetic):
    from utils import investor_report as IR
    port, px, det = synthetic
    out = IR.build(port, "2026-08", det=det, bench=px["SPY"])
    assert out["pdf"][:4] == b"%PDF" and out["journal"] and "En bref" in out["html"]


def test_committee_png_with_plain_summary(ctx, synthetic):
    from utils.committee_report import committee_png, committee_pdf
    port, px, det = synthetic
    R = A._simulated_prices(["AAPL", "TSLA"], n=600, seed=5).pct_change().iloc[1:]
    rev = CM.review_portfolio({"AAPL": 20000, "TSLA": 10000}, 70000, CM.default_ips("Équilibré"), ctx, R=R,
                              port=port, label="Synth")
    rev["synthese_simple"] = PS.plain_summary(port, det=det, bench=px["SPY"])
    nav = det.sum(axis=1)
    assert committee_png(rev, "Synth", nav, px["SPY"])[:4] == b"\x89PNG"
    assert committee_pdf(rev, "Synth", nav, px["SPY"])[:4] == b"%PDF"
