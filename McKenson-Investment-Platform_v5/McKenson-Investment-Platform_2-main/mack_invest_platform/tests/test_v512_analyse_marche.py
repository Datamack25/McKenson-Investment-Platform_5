"""v5.12 — Analyse Marché : fin des faux « +0,0 % », paramètres admin, scénarios, couvertures, intraday (sans réseau)."""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from utils import core_params as CP
from utils import market_drivers as MD
from utils import prices as P
from utils import scenarios as SC


@pytest.fixture(autouse=True)
def _fresh_params(monkeypatch):
    """Paramètres en mémoire uniquement (aucune base) et remis à zéro pour chaque test."""
    import utils.alerts as AL
    monkeypatch.setattr(AL, "get_state", lambda k: None)
    monkeypatch.setattr(AL, "set_state", lambda k, v: False)
    CP._LOCAL.clear()
    CP.clear_cache()
    yield
    CP._LOCAL.clear()
    CP.clear_cache()


def _mixed_calendar_px(drop=-0.05):
    """Reproduit la situation réelle : la dernière ligne (aujourd'hui) existe parce que le pétrole et le dollar
    cotent déjà, mais le Nasdaq, les ETF et les géants n'ont pas encore coté (NaN). La veille : séance à −5 %."""
    rng = np.random.default_rng(11)
    n = 600
    idx = pd.bdate_range("2024-07-01", periods=n)
    r = rng.normal(0.0004, 0.011, n)
    r[-1] = np.log1p(drop)                              # la vraie dernière séance du Nasdaq
    cols = {"^NDX": 20000 * np.exp(np.cumsum(r)), "^GSPC": 6000 * np.exp(np.cumsum(r * 0.75)),
            "^TNX": 4 + np.cumsum(rng.normal(0, 0.04, n)), "^VIX": 15 * np.exp(np.cumsum(rng.normal(0, 0.03, n))),
            "DX-Y.NYB": 100 * np.exp(np.cumsum(rng.normal(0, 0.003, n))),
            "CL=F": 70 * np.exp(np.cumsum(rng.normal(0, 0.02, n))),
            "HYG": 78 * np.exp(np.cumsum(rng.normal(0, 0.002, n))), "IEF": 95 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))}
    cols["^VIX"][-1] = 32.0
    for i, t in enumerate(list(MD.SECTOR_ETFS) + list(MD.HEAT_ASSETS)):
        cols[t] = 100 * np.exp(np.cumsum(r * (0.4 + i / 12) + rng.normal(0, 0.004, n)))
    for t in MD.LEADERS["us"]:
        cols[t] = 300 * np.exp(np.cumsum(r * 1.3 + rng.normal(0, 0.01, n)))
    px = pd.DataFrame(cols, index=idx)
    today = idx[-1] + pd.offsets.BDay(1)
    extra = pd.DataFrame({c: [np.nan] for c in px.columns}, index=[today])
    extra["CL=F"], extra["DX-Y.NYB"] = px["CL=F"].iloc[-1] * 1.01, px["DX-Y.NYB"].iloc[-1]
    return pd.concat([px, extra])


# ── 1. Le bug et sa correction ────────────────────────────────────────────────
def test_old_ffill_reproduced_the_zero_bug():
    px = _mixed_calendar_px()
    old = px.ffill(limit=3)
    s = old["^NDX"]
    assert s.iloc[-1] / s.iloc[-2] - 1 == 0.0          # l'ancien calcul : « Nasdaq stable de +0,0 % »


def test_attribution_reads_the_real_session():
    px = _mixed_calendar_px(-0.05)
    att = MD.attribution(px, "Nasdaq 100", 1)
    assert att["ok"]
    assert att["move_pct"] == pytest.approx(-0.05, abs=1e-9)
    assert att["z"] < -3                                 # mouvement exceptionnel, pas « dans la norme »
    an = MD.analyse("Nasdaq 100", 1, px, [], [], [], "Aversion au risque", "Équilibré")
    assert "en baisse de -5.0%" in an["headline"] and "exceptionnel" in an["headline"]
    assert "+0.0%" not in an["headline"]
    txt = " ".join(a["texte"] for a in an["adapt"])
    assert "dans la norme" not in txt and "stress" in txt


def test_rotation_leaders_heatmap_not_zero():
    px = _mixed_calendar_px(-0.05)
    rot = MD.rotation(px, 1)
    lead = MD.leaders_moves(px, "Nasdaq 100", 1)
    assert len(rot) == len(MD.SECTOR_ETFS) and (rot["Rendement"].abs() > 1e-4).all()
    assert len(lead) == len(MD.LEADERS["us"]) and (lead["Rendement"] < 0).sum() >= 10
    heat = MD.heatmap_table(px)
    assert {"1 J", "1 S", "1 M", "Depuis 1er janv."} <= set(heat.columns)
    assert heat["1 J"].abs().min() > 1e-4


def test_missing_data_is_nan_not_zero():
    s = pd.Series([100.0, np.nan, np.nan], index=pd.bdate_range("2026-01-01", periods=3))
    assert not P.change(s, 1)["ok"] and np.isnan(P.change(s, 1)["ret"])
    assert P.fmt_pct(np.nan) == "indispo."
    px = _mixed_calendar_px().drop(columns=list(MD.SECTOR_ETFS))
    assert MD.rotation(px, 1).empty
    assert any("ETF sectoriels sans cours" in c for c in MD.data_checks(px, "Nasdaq 100"))


def test_extract_closes_formats():
    idx = pd.date_range("2026-01-01", periods=3)
    a = pd.DataFrame(np.arange(6.0).reshape(3, 2) + 1, index=idx,
                     columns=pd.MultiIndex.from_product([["Close"], ["AAA", "BBB"]]))
    b = pd.DataFrame(np.arange(6.0).reshape(3, 2) + 1, index=idx,
                     columns=pd.MultiIndex.from_tuples([("AAA", "Close"), ("BBB", "Close")]))
    c = pd.DataFrame({"Open": [1.0, 2, 3], "Close": [1.0, 2, 3]}, index=idx)
    assert list(P.extract_closes(a, ["AAA", "BBB"]).columns) == ["AAA", "BBB"]
    assert list(P.extract_closes(b, ["AAA", "BBB"]).columns) == ["AAA", "BBB"]
    assert list(P.extract_closes(c, ["AAA"]).columns) == ["AAA"]


def test_beta_sentence_uses_beta_times_move():
    px = _mixed_calendar_px(-0.05)
    att = MD.attribution(px, "Nasdaq 100", 1)
    out = MD.adaptation(att, MD.technical(px["^NDX"]), None, "Équilibré",
                        port=dict(ok=True, beta=0.23, impact=0.23 * att["move_pct"]))
    t = next(a["texte"] for a in out if "bêta de 0.23" in a["texte"])
    assert "-5.0%" in t and "-1.1%" in t and "+0.0%" not in t


# ── 2. Paramètres admin ───────────────────────────────────────────────────────
def test_params_bounds_and_cross_checks():
    assert CP.get("z_norme") == 1.2
    ok, errs = CP.set_values({"z_norme": 99})
    assert not ok and errs
    ok, errs = CP.set_values({"z_norme": 2.5})                 # > z_fort (2,0) : incohérent
    assert not ok and any("croissants" in e for e in errs)
    CP.set_values({"z_norme": 1.5, "rsi_survente": 25}, "jena")
    assert CP.get("z_norme") == 1.5 and CP.get("rsi_survente") == 25
    assert CP.is_custom() and "z-score" in CP.custom_note()
    assert CP.history()[0]["qui"] == "jena"
    CP.reset("all")
    assert CP.get("z_norme") == 1.2 and not CP.is_custom()


def test_formula_is_sandboxed():
    assert CP.check_expression("__import__('os').system('ls')") is not None
    assert CP.check_expression("open('x')") is not None
    assert CP.check_expression("momentum.__class__") is not None
    assert CP.check_expression("w_peur*peur + 2*tanh(catalyseurs)") is None
    ok, _ = CP.set_formula("score_scenario", "3*peur")
    assert ok and SC.score({"peur": -0.5}) == pytest.approx(-1.5)


def test_params_change_market_reading():
    px = _mixed_calendar_px(-0.05)
    ok, _ = CP.set_values({"z_exceptionnel": 6.0, "z_fort": 3.9, "z_norme": 2.9})
    assert ok
    an = MD.analyse("Nasdaq 100", 1, px, [], [], [], None, "Équilibré")
    assert "exceptionnel" not in an["headline"]


# ── 3. Scénarios ──────────────────────────────────────────────────────────────
def test_probabilities_sum_and_direction():
    p0, pneg, ppos = SC.probabilities(0.0), SC.probabilities(-2.0), SC.probabilities(2.0)
    for p in (p0, pneg, ppos):
        assert sum(p.values()) == pytest.approx(1.0)
    assert pneg["baissier"] > p0["baissier"] > ppos["baissier"]
    scs = CP.scenarios()
    scs[2]["prob_forcee"] = 0.5
    pf = SC.probabilities(0.0, scs)
    assert pf["baissier"] == pytest.approx(0.5) and sum(pf.values()) == pytest.approx(1.0)


def test_sensitivity_bearish_catalyst():
    sens = SC.sensitivity({k: 0.0 for k in CP.SCORE_VARS} | {"catalyseurs": SC.catalyst_score()})
    ia = next(r for r in sens if "financement de l'IA" in r["catalyseur"])
    assert ia["si_realise"]["baissier"] > 0 > ia["si_ecarte"]["baissier"]


def test_full_analysis_with_scenarios_and_pdf():
    px = _mixed_calendar_px(-0.05)
    an = MD.analyse("Nasdaq 100", 1, px, [], [], [], "Aversion au risque", "Équilibré")
    sc = an["scen"]
    assert sc["ok"] and sum(sc["probs"].values()) == pytest.approx(1.0)
    assert sc["probs"]["baissier"] > CP.scenarios()[2]["prior"]      # séance à −5 %, VIX 32
    assert len(sc["sectors"]) == len(CP.SECTORS)
    md = SC.note_markdown(an, sc)
    assert "Note de synthèse" in md and "remédiation" in md
    pdf = MD.build_pdf(an, px)
    assert pdf[:4] == b"%PDF" and len(pdf) > 5000


# ── 4. Couvertures et remédiation ─────────────────────────────────────────────
def _hist():
    idx = pd.bdate_range("2025-01-01", periods=300)
    rng = np.random.default_rng(3)
    base = np.cumsum(rng.normal(0, 0.01, 300))
    h = pd.DataFrame({"SPY": 600 * np.exp(base * 0.8), "QQQ": 500 * np.exp(base), "SOXX": 250 * np.exp(base * 1.6),
                      "NVDA": 180 * np.exp(base * 1.8)}, index=idx)
    h.iloc[-1] = h.iloc[-2] * np.array([0.956, 0.94, 0.88, 0.86])   # S&P −4,4 %, SOXX −12 %
    return h


def test_hedge_diagnostic_explains_poor_protection():
    h = _hist()
    spot = float(h["SPY"].iloc[-2])
    port = dict(options=[dict(ticker="SPY", type="put", action="BUY", strike=round(spot * 0.85), n_contracts=1,
                              contract_mult=100, sigma=0.2, maturity_days=60,
                              date=(datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M"))])
    vals = {"NVDA": 60000.0, "SOXX": 30000.0, "SPY": 10000.0}
    d = SC.hedge_effectiveness(port, vals, h, horizon=1)
    txt = " ".join(d["causes"])
    assert "hors de la monnaie" in txt and "insuffisant" in txt and "Mauvais sous-jacent" in txt
    assert d["equity_pnl"] < 0 and d["hedge_gain"] < -d["equity_pnl"]
    assert any("QQQ ou SOXX" in f for f in d["fixes"])


def test_personal_caps_drive_remediation():
    CP.set_values({"plafond_us": 0.5, "plafond_tech_ia": 0.3})
    expo = SC.exposure_profile({"NVDA": 60000.0, "SOXX": 30000.0, "VGK": 10000.0}, 0.0)
    assert expo["us"] == pytest.approx(0.9) and expo["tech"] == pytest.approx(0.9)
    rem = SC.remediation(SC.probabilities(-1.0), expo=expo, port_beta=1.4)
    txt = " ".join(rem["perso"])
    assert "plafond 50%" in txt and "plafond 30%" in txt and "Bêta 1.40" in txt


def test_big_loss_detection():
    nav = pd.Series([100.0, 101, 102, 101, 100, 99, 94.0], index=pd.bdate_range("2026-10-26", periods=7))
    bl = SC.big_loss(nav)
    assert bl["triggered"] and any("séance" in x for x in bl["hits"])
    assert not SC.big_loss(pd.Series([100.0, 100.5, 101, 101.2], index=pd.bdate_range("2026-10-26", periods=4)))["triggered"]


# ── 5. Intraday 1 h / 6 h ─────────────────────────────────────────────────────
def test_intraday_windows_and_sentiment():
    from utils import intraday as ID
    end = pd.Timestamp("2026-11-06 10:00")
    idx = pd.date_range(end - pd.Timedelta(hours=10), end, freq="5min")
    s = pd.Series(np.linspace(21000, 20500, len(idx)), index=idx)
    bars = pd.DataFrame({"NQ=F": s})
    news = [dict(title="Nasdaq tumbles as AI chip stocks plunge on funding fears", pubdate="Fri, 06 Nov 2026 09:30:00 GMT",
                 category="Marché"),
            dict(title="Nasdaq rallies strongly on record tech earnings", pubdate="Thu, 05 Nov 2026 12:00:00 GMT",
                 category="Marché")]
    it = ID.analyse_intraday("Nasdaq 100", bars, news, [], [], MD.MARKETS["Nasdaq 100"]["kw"], now=end)
    assert it["ok"] and it["ticker"] == "NQ=F"
    assert it["w6"]["ret"] < 0 and it["w1"]["ret"] < 0 and it["w6"]["ret"] < it["w1"]["ret"]
    assert it["sentiment"]["1 h"]["n"] == 1 and it["sentiment"]["24 h"]["n"] == 2
    assert any("6 h" in a for a in it["alerts"])


# ── 6. Rapport : grosse perte → analyse du comité + remédiation ───────────────
def test_big_loss_report_section():
    from utils import committee_report as CR
    px = _mixed_calendar_px(-0.05)
    h = _hist()
    nav = pd.Series(np.r_[np.linspace(100, 104, 20), [97.0]], index=pd.bdate_range("2026-10-08", periods=21))
    vals = {"NVDA": 60000.0, "SOXX": 30000.0}
    port = dict(name="Test", options=[], ips={"profil": "Dynamique"})
    gp = CR.loss_analysis(port, vals, 10000.0, nav, {}, px=px, hist=h)
    assert gp and gp["detection"]["triggered"] and gp["market"] == "Nasdaq 100"
    assert gp["scen"]["ok"] and gp["analyse"]["headline"]
    blocks = CR._loss_pdf_blocks(gp)
    assert blocks[0][1].startswith("⚠️ Grosse perte")
    html = CR._loss_html(gp)
    assert "Plans de remédiation" in html and "Aucune option" in html
    from utils.reporting import make_pdf
    assert make_pdf("t", "s", blocks)[:4] == b"%PDF"
    calm = pd.Series(np.linspace(100, 101, 21), index=nav.index)
    assert CR.loss_analysis(port, vals, 10000.0, calm, {}, px=px, hist=h) is None
