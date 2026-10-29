"""v5.8 — devises, coûts de transaction, dividendes, intérêts monétaires, flux externes et TWR (GIPS)."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from utils import costs as CO
from utils import fx as FX
from utils import income as IN
from utils import ledger as LG
from utils import performance as PF
from utils import plain_summary as PS


# ── Devises ───────────────────────────────────────────────────────────────────
def test_quote_currencies():
    assert FX.quote_currency("AAPL") == "USD"
    assert FX.quote_currency("MC.PA") == "EUR"
    assert FX.quote_currency("HSBA.L") == "GBp"          # pence
    assert FX.quote_currency("CSPX.L") == "USD"          # ETF londonien coté en dollars
    assert FX.quote_currency("005930.KS") == "KRW"
    assert FX.quote_currency("^FCHI") == "USD" and FX.quote_currency("BTC-USD") == "USD"


def test_conversion_to_usd():
    FX.set_rates({"EUR": 1.10, "GBP": 1.25, "KRW": 0.0007})
    assert FX.to_usd("MC.PA", 100) == pytest.approx(110)
    assert FX.to_usd("HSBA.L", 700) == pytest.approx(700 * 0.01 * 1.25)   # 700 pence
    assert FX.to_usd("005930.KS", 70_000) == pytest.approx(49)            # et non 70 000 $
    px = pd.DataFrame({"MC.PA": [100.0, 101.0], "AAPL": [200.0, 201.0]}, index=pd.bdate_range("2026-10-01", periods=2))
    out = FX.convert_history(px)
    assert out["MC.PA"].iloc[0] == pytest.approx(110) and out["AAPL"].iloc[1] == 201


# ── Coûts ─────────────────────────────────────────────────────────────────────
def test_costs_schedule():
    c = CO.spot_costs("AAPL", "BUY", 10, 100.0)
    assert c["prix"] > 100 and c["frais"] == pytest.approx(1.0)          # minimum 1 $
    c = CO.spot_costs("TTE.PA", "BUY", 1000, 60.0)
    assert c["taxe"] == pytest.approx(1000 * c["prix"] * CO.TTF_RATE)
    assert CO.spot_costs("TTE.PA", "SELL", 1000, 60.0)["taxe"] == 0       # TTF à l'achat seulement
    assert CO.spot_costs("BP.L", "BUY", 100, 5.0)["taxe"] > 0
    q = CO.affordable_qty("AAPL", 10_000, 100.0, 100)
    assert q < 100 and CO.total_cost("AAPL", "BUY", q, 100.0) <= 10_000 + 1e-6


def test_apply_trade_records_fees_and_cost_basis():
    from utils.data import apply_trade
    port = {"cash": 10_000.0, "holdings": {}, "trades": []}
    e = apply_trade(port, "AAPL", "BUY", 10, 100.0)
    assert e["frais"] == pytest.approx(1.0) and e["price"] > 100
    assert port["cash"] == pytest.approx(10_000 - 10 * e["price"] - 1.0)
    assert port["holdings"]["AAPL"]["avg_price"] == pytest.approx((10 * e["price"] + 1.0) / 10)
    assert isinstance(apply_trade(port, "AAPL", "BUY", 1000, 100.0), str)  # fonds insuffisants


def test_execute_orders_shrinks_buy_to_fit_fees(port_basic):
    from utils.auto_portfolio import execute_orders
    from utils import compliance as CP
    from utils import committee as CM
    port_basic["cash"] = 5_000.0
    port_basic["ips"] = CM.default_ips("Agressif")            # pas de réserve de liquidités imposée
    orders = pd.DataFrame([dict(ticker="AAPL", action="BUY", qty=50.0, price=100.0, montant=5_000.0)])
    orig = CP._price_source
    CP._price_source = lambda t: "live"
    try:
        errs = execute_orders(port_basic, orders, tag="test")
    finally:
        CP._price_source = orig
    assert not errs and port_basic["cash"] >= -1e-6 and port_basic["holdings"]["AAPL"]["qty"] < 50


def test_c07_includes_fees(port_basic):
    from utils import compliance as CP
    port_basic["cash"] = 1_000.0
    d = CP.pre_trade_spot(port_basic, "AAPL", "BUY", 10, 100.0, profile={"risque": "Agressif", "defini": True},
                          prices={"SPY": 500.0, "TLT": 90.0, "AAPL": 100.0}, price_source="live")
    assert "C07" in [c.code for c in d.blocks]


# ── Flux externes et TWR ─────────────────────────────────────────────────────
def test_twr_ignores_external_flows():
    idx = pd.bdate_range("2026-10-01", periods=4)
    nav = pd.Series([100.0, 110.0, 220.0, 231.0], index=idx)    # +10 %, apport de 100, +0 %, +5 %
    flows = pd.Series([0.0, 0.0, 110.0, 0.0], index=idx)
    r = LG.twr_returns(nav, flows)
    assert r.tolist() == pytest.approx([0.10, 0.0, 0.05])
    idx_ = LG.twr_index(nav, flows)
    assert idx_.iloc[-1] / idx_.iloc[0] - 1 == pytest.approx(1.1 * 1.05 - 1)
    assert LG.annualize(0.1, 200) is None and LG.annualize(0.1, 365) == pytest.approx(0.1, abs=1e-3)


def test_admin_deposit_does_not_change_performance():
    port = {"cash": 1000.0, "initial_cash": 1000.0, "trades": [], "mouvements": []}
    ok, _ = LG.external_flow(port, 500)
    assert ok and port["cash"] == 1500 and LG.net_external(port) == 500
    assert not LG.external_flow(port, -5000)[0]                 # retrait > liquidités


@pytest.fixture
def realistic():
    """Achat AAPL frais compris, dividende, intérêts, puis apport de l'administrateur."""
    idx = pd.bdate_range("2026-09-01", "2026-09-30")
    px = pd.DataFrame({"AAPL": np.linspace(100, 110, len(idx))}, index=idx)
    port = {"id": "R", "name": "Réaliste", "initial_cash": 100_000.0, "cash": 0.0, "holdings": {}, "options": [],
            "trades": [{"date": "2026-09-01 10:00", "ticker": "AAPL", "action": "BUY", "qty": 500, "price": 100.05,
                        "total": 50_025.0, "frais": 25.0, "source": "Trading Desk"}],
            "mouvements": [
                {"date": "2026-09-10 09:00", "type": "dividende", "ticker": "AAPL", "montant": 100.0},
                {"date": "2026-09-15 23:59", "type": "interet", "montant": 6.0},
                {"date": "2026-09-20 10:00", "type": "apport", "montant": 50_000.0}]}
    return port, px


def test_nav_includes_fees_income_and_flows(realistic):
    port, px = realistic
    det = PF.nav_detail(port, px)
    last = det.iloc[-1]
    assert last["CASH"] == pytest.approx(100_000 - 50_025 - 25 + 100 + 6 + 50_000)
    assert last["AAPL"] == pytest.approx(500 * 110)


def test_contributions_sum_to_twr_with_flows(realistic):
    port, px = realistic
    det = PF.nav_detail(port, px)
    lc = PS.line_contributions(port, det=det)
    twr = LG.twr_index(det.sum(axis=1), PF.external_flows(port, det.index))
    assert lc["perf"] == pytest.approx(float(twr.iloc[-1] / twr.iloc[0] - 1))
    assert lc["lignes"]["contribution"].sum() == pytest.approx(lc["perf"], abs=1e-9)
    names = set(lc["lignes"]["ligne"])
    assert {"AAPL", PS.CASH_LABEL} <= names and lc["apports"] == pytest.approx(50_000)


def test_plain_summary_mentions_gips_and_flows(realistic):
    port, px = realistic
    det = PF.nav_detail(port, px)
    s = PS.plain_summary(port, det=det, bench=px["AAPL"] * 0 + np.linspace(400, 404, len(px)))
    txt = " ".join(s["phrases"])
    assert "GIPS" in txt and "Apports de liquidités" in txt and "intérêts" in txt


# ── Revenus ──────────────────────────────────────────────────────────────────
def test_interest_accrual_uses_market_rate_and_weekends():
    port = {"initial_cash": 100_000.0, "cash": 100_000.0, "trades": [],
            "mouvements": [{"date": "2026-10-01 00:00", "type": "apport", "montant": 0.0}], "options": []}
    port["mouvements"] = []
    port["created"] = "2026-10-01"
    rates = pd.Series(0.036, index=pd.bdate_range("2026-09-25", "2026-10-09"))
    made = IN.accrue_interest(port, date(2026, 10, 6), rates=rates)  # 1er (jeu) → 5 (lun)
    days = [m["date"][:10] for m in made]
    assert days == ["2026-10-01", "2026-10-02", "2026-10-05"]
    fri = next(m for m in made if m["date"].startswith("2026-10-02"))
    assert fri["montant"] == pytest.approx(100_000 * 0.036 * 3 / 360, rel=1e-3)   # vendredi : 3 jours
    assert IN.accrue_interest(port, date(2026, 10, 6), rates=rates) == []          # pas de double comptage
    assert IN.accrue_interest({"created": "2026-10-01", "cash": 1.0, "trades": []}, date(2026, 10, 6),
                              rates=pd.Series(dtype=float)) == []                   # pas de taux : rien


def test_dividends_credited_net_of_withholding():
    port = {"cash": 0.0, "initial_cash": 10_000.0, "options": [],
            "trades": [{"date": "2026-08-01 10:00", "ticker": "AAPL", "action": "BUY", "qty": 100, "price": 100.0},
                       {"date": "2026-09-05 10:00", "ticker": "AAPL", "action": "SELL", "qty": 40, "price": 100.0}]}
    fake = lambda t: pd.Series([0.25, 0.26], index=pd.to_datetime(["2026-08-10", "2026-09-10"]))
    made = IN.accrue_dividends(port, date(2026, 10, 1), fetch=fake)
    assert [m["montant"] for m in made] == pytest.approx([100 * 0.25 * 0.85, 60 * 0.26 * 0.85])
    assert IN.accrue_dividends(port, date(2026, 10, 1), fetch=fake) == []
    assert IN.withholding("TTE.PA") == 0.0 and IN.withholding("AAPL") == 0.15


def test_since_inception_uses_twr_when_flows(realistic):
    port, px = realistic
    r, how = PF.since_inception({"initial_cash": 100.0, "trades": []}, 110.0)
    assert r == pytest.approx(0.10) and "aucun flux" in how
