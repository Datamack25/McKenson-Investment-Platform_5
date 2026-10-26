from datetime import datetime, timedelta

from utils import hedging as H
from utils.options import book_option, consolidate_options


def _leg(action="BUY", n=2, K=100.0, prem=3.0, days=90, when=None):
    return dict(date=(when or datetime.now()).strftime("%Y-%m-%d %H:%M"), ticker="SPY", type="put", action=action,
                strike=K, maturity_days=days, sigma=20, n_contracts=n, contract_mult=100, premium=prem,
                total_premium=prem * n * 100, spot_at_entry=100)


def test_buy_twice_same_instrument_is_one_line():
    port = {}
    assert book_option(port, _leg(n=2, prem=3.0)) == "nouvelle ligne"
    assert book_option(port, _leg(n=3, prem=4.0)) == "renforcement"
    assert len(port["options"]) == 1
    o = port["options"][0]
    assert o["n_contracts"] == 5 and abs(o["premium"] - 3.6) < 1e-9


def test_sell_reduces_then_closes():
    port = {}
    book_option(port, _leg(n=5))
    assert book_option(port, _leg("SELL", n=2)) == "réduction" and port["options"][0]["n_contracts"] == 3
    assert book_option(port, _leg("SELL", n=3)) == "clôture" and port["options"] == []


def test_different_strike_or_expiry_stays_separate():
    port = {}
    book_option(port, _leg(K=100))
    book_option(port, _leg(K=95))
    book_option(port, _leg(K=100, days=200))
    assert len(port["options"]) == 3


def test_consolidate_existing_duplicates():
    port = {"options": [_leg(n=2), _leg(n=2), _leg(K=90)]}
    assert consolidate_options(port) == 1 and len(port["options"]) == 2


def _hedge(n, spot=100.0):
    return dict(cle="europe", panier="Actions européennes", sous_jacent="SPY", strategie="Put de protection",
                contrats=n, spot=spot, sigma=0.2, echeance=90, exposition=1e6, valeur_contrat=spot * 100,
                legs=[{"type": "put", "qty": n, "K": 95.0, "premium": 2.0}])


def test_hedge_reapplied_adjusts_instead_of_duplicating(monkeypatch):
    import utils.compliance as CP
    monkeypatch.setattr(CP, "pre_trade_options", lambda port, t, legs, **k: (
        CP.Decision("option"), {"net_premium": sum(l["qty"] * l["premium"] * 100 for l in legs)}))
    monkeypatch.setattr(CP, "log_decision", lambda *a, **k: None)
    port = {"cash": 1e6, "holdings": {"SPY": {"qty": 10000, "avg_price": 100}}, "options": [], "trades": []}
    assert H.execute_hedge(port, h := _hedge(5)) == "" and len(port["options"]) == 1
    cash = port["cash"]
    assert H.execute_hedge(port, h := _hedge(5)) == "" and "déjà" in h["ajustement"]
    assert len(port["options"]) == 1 and port["cash"] == cash          # aucun ordre en double
    assert H.execute_hedge(port, h := _hedge(8)) == ""
    assert len(port["options"]) == 1 and port["options"][0]["n_contracts"] == 8 and "renforcée" in h["ajustement"]
    assert port["cash"] < cash
    assert H.execute_hedge(port, h := _hedge(3)) == ""
    assert len(port["options"]) == 1 and port["options"][0]["n_contracts"] == 3 and "réduite" in h["ajustement"]
