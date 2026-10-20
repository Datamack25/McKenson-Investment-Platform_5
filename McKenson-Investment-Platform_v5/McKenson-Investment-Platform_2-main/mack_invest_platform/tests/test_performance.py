import numpy as np
import pandas as pd

from utils import advisor as A, performance as PF


def _px():
    idx = pd.bdate_range("2026-03-02", "2026-10-16")
    rng = np.random.default_rng(1)
    tk = {"AAPL", "TLT", "GLD", "QQQ"} | set(A.CLASS_PROXY.values())
    return pd.DataFrame({t: 100 * np.exp(np.cumsum(rng.normal(3e-4, 0.012, len(idx)))) for t in tk}, index=idx)


def _port(px):
    p = lambda t, d: float(px[t].loc[d])
    return dict(name="T", initial_cash=100_000.0, trades=[
        dict(date="2026-03-02 10:00", ticker="AAPL", action="BUY", qty=200, price=p("AAPL", "2026-03-02")),
        dict(date="2026-03-02 10:00", ticker="TLT", action="BUY", qty=300, price=p("TLT", "2026-03-02")),
        dict(date="2026-07-01 10:00", ticker="AAPL", action="SELL", qty=50, price=p("AAPL", "2026-07-01"))],
        options=[dict(date="2026-04-01 10:00", ticker="QQQ", type="put", action="BUY", strike=95, maturity_days=60,
                      sigma=22, n_contracts=2, contract_mult=100, premium=3.0, spot_at_entry=p("QQQ", "2026-04-01"))])


def test_nav_includes_option_premium_then_value():
    px = _px(); port = _port(px)
    det = PF.nav_detail(port, px)
    d0 = pd.Timestamp("2026-04-01")
    assert det.loc[d0, "OPTIONS"] > 0
    without = PF.reconstruct_nav(port, px, include_options=False)
    assert abs(without.loc["2026-03-31"] - PF.reconstruct_nav(port, px).loc["2026-03-31"]) < 1e-6


def test_option_value_frozen_after_expiry():
    px = _px(); port = _port(px)
    det = PF.nav_detail(port, px)
    after = det.loc["2026-06-15":, "OPTIONS"]
    assert after.nunique() == 1                     # valeur intrinsèque figée à l'échéance


def test_attribution_is_exactly_additive():
    px = _px(); port = _port(px)
    a = PF.attribution(port, px, profile="Équilibré")
    assert a["ok"]
    assert abs(a["ecart_explique"] - a["ecart"]) < 1e-9


def test_metrics_basic():
    nav = pd.Series([100, 101, 99, 102, 103, 104], index=pd.bdate_range("2026-01-05", periods=6))
    m = PF.metrics(nav, nav * 1.0)
    assert abs(m["Performance"] - 0.04) < 1e-12 and abs(m["Surperformance"]) < 1e-12 and abs(m["Bêta"] - 1) < 1e-9
