import pandas as pd

from utils.execution_log import compare, follow_up


def test_statuses():
    rec = pd.DataFrame([dict(ticker="SPY", action="BUY", qty=10, price=500.0),
                        dict(ticker="BTC-USD", action="BUY", qty=1, price=60_000.0),
                        dict(ticker="TLT", action="SELL", qty=100, price=90.0)])
    ex = [dict(ticker="SPY", action="BUY", qty=10, price=500, total=5000),
          dict(ticker="TLT", action="SELL", qty=60, price=90, total=5400)]
    m = compare(rec, ex, ["BTC-USD bloqué — [C05] Plafond crypto-actifs"]).set_index("ticker")
    assert m.loc["SPY", "statut"] == "exécuté"
    assert m.loc["BTC-USD", "statut"] == "bloqué (conformité)"
    assert m.loc["TLT", "statut"] == "partiel"


def test_empty_plan():
    assert compare(None, [], []).empty


def test_follow_up_drift():
    e = dict(cible={"SPY": 0.5, "TLT": 0.5})
    port = dict(cash=0.0, holdings={"SPY": {"qty": 10, "avg_price": 100}, "TLT": {"qty": 10, "avg_price": 100}})
    df, drift = follow_up(e, port, {"SPY": (150.0, 0), "TLT": (50.0, 0)})
    assert abs(drift - 0.25) < 1e-9
