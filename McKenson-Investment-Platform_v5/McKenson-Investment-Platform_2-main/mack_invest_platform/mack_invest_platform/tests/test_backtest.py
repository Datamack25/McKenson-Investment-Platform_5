from utils import backtest_desk as B


def test_backtest_runs_and_compares(px10):
    r = B.run(px10, [], "Équilibré", 0.5)
    assert r["ok"] and list(r["nav"].columns) == list(B.NAMES)
    assert r["nav"].iloc[0].eq(1.0).all()
    assert r["n_mois"] > 60
    assert r["stats"].loc["Desk complet", "Rotation moyenne / mois"] >= r["stats"].loc["Allocation stratégique", "Rotation moyenne / mois"]


def test_backtest_refuses_simulated(px10):
    assert not B.run(px10, ["SPY"])["ok"]
